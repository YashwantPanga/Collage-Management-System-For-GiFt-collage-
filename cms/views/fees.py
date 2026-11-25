import base64
import hashlib
import hmac
import json
import urllib.request
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.utils import audit, notify

from .. import models as m
from ..forms import InvoiceEditForm, InvoiceGenerateForm, OfflinePaymentForm, RefundForm
from ..helpers import pick_student, students_for
from ..permissions import FULL, can, module_required


def _invoice_for_payer(user, pk):
    inv = get_object_or_404(m.Invoice.objects.select_related("student__user", "student__course"), pk=pk)
    if can(user, "fees", FULL):
        return inv
    if not students_for(user).filter(pk=inv.student_id).exists():
        raise PermissionDenied
    return inv


@module_required("fees", "pay")
def my_fees(request):
    student, wards = pick_student(request)
    invoices = student.invoices.prefetch_related("payments") if student else []
    payments = m.Payment.objects.filter(invoice__student=student, status="success") if student else []
    return render(request, "portal/fees/mine.html", {"student": student, "wards": wards, "invoices": invoices, "payments": payments,
                                                     "due": student.fee_due() if student else 0})


@module_required("fees", "pay", FULL)
def pay_invoice(request, pk):
    inv = _invoice_for_payer(request.user, pk)
    if inv.balance <= 0:
        messages.info(request, "This invoice is already fully paid.")
        return redirect("cms:my_fees")
    amount = inv.balance
    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", inv.balance)).quantize(Decimal("0.01"))
        except InvalidOperation:
            amount = inv.balance
        amount = min(max(amount, Decimal("1")), inv.balance)
        payment = m.Payment.objects.create(invoice=inv, amount=amount, method="online", paid_by=request.user)
        if settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET:
            order = _razorpay_order(payment)
            payment.gateway_order_id = order["id"]
            payment.save(update_fields=["gateway_order_id"])
            return render(request, "portal/fees/razorpay.html", {"payment": payment, "inv": inv, "key": settings.RAZORPAY_KEY_ID,
                                                                 "amount_paise": int(amount * 100)})
        payment.gateway_order_id = f"DEMO-{payment.pk}-{int(timezone.now().timestamp())}"
        payment.save(update_fields=["gateway_order_id"])
        return render(request, "portal/fees/demo_gateway.html", {"payment": payment, "inv": inv})
    return render(request, "portal/fees/pay.html", {"inv": inv, "amount": amount})


def _razorpay_order(payment):
    auth = base64.b64encode(f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()).decode()
    body = json.dumps({"amount": int(payment.amount * 100), "currency": "INR", "receipt": f"pay_{payment.pk}"}).encode()
    req = urllib.request.Request("https://api.razorpay.com/v1/orders", data=body, method="POST",
                                 headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


@login_required
@require_POST
@transaction.atomic
def payment_callback(request, pk):
    payment = get_object_or_404(m.Payment.objects.select_for_update().select_related("invoice__student__user", "invoice__student__parent"), pk=pk)
    _invoice_for_payer(request.user, payment.invoice_id)
    if payment.status == "success":
        return redirect("cms:receipt", payment.pk)
    ok = False
    if settings.RAZORPAY_KEY_SECRET:
        order_id = request.POST.get("razorpay_order_id", "")
        pay_id = request.POST.get("razorpay_payment_id", "")
        sig = request.POST.get("razorpay_signature", "")
        expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), f"{order_id}|{pay_id}".encode(), hashlib.sha256).hexdigest()
        ok = order_id == payment.gateway_order_id and hmac.compare_digest(expected, sig)
        txn = pay_id
    else:
        ok = request.POST.get("result") == "success" and request.POST.get("order") == payment.gateway_order_id
        txn = f"DEMOTXN{payment.pk:06d}{int(timezone.now().timestamp()) % 100000}"
    if not ok:
        payment.status = "failed"
        payment.save(update_fields=["status"])
        audit(request, "fees.payment_failed", payment)
        messages.error(request, "Payment failed or was cancelled. No money was deducted. You can try again.")
        return redirect("cms:my_fees" if not can(request.user, "fees", FULL) else "cms:invoices")
    payment.mark_success(txn)
    audit(request, "fees.payment_success", payment, f"₹{payment.amount} {txn}")
    s = payment.invoice.student
    notify([s.user, s.parent], "Fee payment received", f"₹{payment.amount} received for {payment.invoice.invoice_no}. Receipt {payment.receipt_no}.",
           reverse("cms:receipt", args=[payment.pk]), "success", email=True)
    messages.success(request, f"Payment successful. Receipt {payment.receipt_no} generated.")
    return redirect("cms:receipt", payment.pk)


@login_required
def receipt(request, pk):
    payment = get_object_or_404(m.Payment.objects.select_related("invoice__student__user", "invoice__student__course", "collected_by"), pk=pk, status="success")
    if not can(request.user, "fees", FULL, "view"):
        _invoice_for_payer(request.user, payment.invoice_id)
    return render(request, "portal/fees/receipt.html", {"p": payment, "inv": payment.invoice})


@module_required("fees", FULL, "view")
def invoices(request):
    qs = m.Invoice.objects.select_related("student__user", "student__course", "student__batch").prefetch_related("payments", "refunds")
    q, course, batch, status = (request.GET.get(k, "") for k in ("q", "course", "batch", "status"))
    if q:
        qs = qs.filter(Q(invoice_no__icontains=q) | Q(student__roll_no__icontains=q) | Q(student__user__first_name__icontains=q))
    if course:
        qs = qs.filter(student__course_id=course)
    if batch:
        qs = qs.filter(student__batch_id=batch)
    items = list(qs)
    if status:
        items = [i for i in items if i.status == status]
    page = Paginator(items, 25).get_page(request.GET.get("page"))
    gen_form = InvoiceGenerateForm()
    return render(request, "portal/fees/invoices.html", {
        "page": page, "q": q, "course": course, "batch": batch, "status": status, "gen_form": gen_form,
        "courses": m.Course.objects.all(), "batches": m.Batch.objects.select_related("course"),
        "can_edit": can(request.user, "fees", FULL),
    })


@module_required("fees", FULL)
def generate_invoices(request):
    form = InvoiceGenerateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        batch, sem, year = form.cleaned_data["batch"], form.cleaned_data["semester"], form.cleaned_data["academic_year"]
        created = skipped = 0
        for s in batch.students.filter(is_active=True):
            if s.invoices.filter(semester=sem).exists():
                skipped += 1
                continue
            fs = (m.FeeStructure.objects.filter(course=batch.course, semester=sem, academic_year=year, category=s.category).first()
                  or m.FeeStructure.objects.filter(course=batch.course, semester=sem, academic_year=year, category="GEN").first())
            if not fs:
                skipped += 1
                continue
            inv = m.Invoice.objects.create(student=s, fee_structure=fs, semester=sem, tuition_fee=fs.tuition_fee, exam_fee=fs.exam_fee,
                                           other_fee=fs.development_fee + fs.other_fee, due_date=fs.due_date)
            notify([s.user, s.parent], "New fee invoice", f"{inv.invoice_no}: ₹{inv.net} due on {inv.due_date:%d %b %Y}.", reverse("cms:my_fees"))
            created += 1
        audit(request, "fees.generate_invoices", batch, f"sem {sem}: {created} created, {skipped} skipped")
        messages.success(request, f"{created} invoice(s) generated, {skipped} skipped (already invoiced or no fee structure).")
    else:
        messages.error(request, "Please choose batch, semester and academic year.")
    return redirect("cms:invoices")


@module_required("fees", FULL, "view")
def invoice_detail(request, pk):
    inv = get_object_or_404(m.Invoice.objects.select_related("student__user", "student__course", "scholarship"), pk=pk)
    edit_form = InvoiceEditForm(instance=inv)
    pay_form = OfflinePaymentForm(initial={"amount": inv.balance, "method": "cash"})
    if request.method == "POST" and can(request.user, "fees", FULL):
        if "edit" in request.POST:
            edit_form = InvoiceEditForm(request.POST, instance=inv)
            if edit_form.is_valid():
                obj = edit_form.save(commit=False)
                if obj.scholarship and not request.POST.get("concession"):
                    obj.concession = obj.scholarship.amount_for(obj.gross)
                obj.save()
                audit(request, "fees.invoice_update", inv, f"concession ₹{obj.concession}")
                messages.success(request, "Invoice updated.")
                return redirect("cms:invoice_detail", pk)
        elif "collect" in request.POST:
            pay_form = OfflinePaymentForm(request.POST)
            if pay_form.is_valid():
                p = pay_form.save(commit=False)
                if p.amount > inv.balance:
                    messages.error(request, f"Amount exceeds the balance of ₹{inv.balance}.")
                    return redirect("cms:invoice_detail", pk)
                p.invoice, p.collected_by = inv, request.user
                p.save()
                p.mark_success(p.transaction_id)
                audit(request, "fees.collect", p, f"₹{p.amount} {p.method}")
                notify([inv.student.user, inv.student.parent], "Fee payment received", f"₹{p.amount} received. Receipt {p.receipt_no}.",
                       reverse("cms:receipt", args=[p.pk]), "success")
                messages.success(request, f"Payment recorded. Receipt {p.receipt_no}.")
                return redirect("cms:receipt", p.pk)
    return render(request, "portal/fees/invoice_detail.html", {"inv": inv, "edit_form": edit_form, "pay_form": pay_form,
                                                               "can_edit": can(request.user, "fees", FULL)})


@module_required("fees", FULL, "view")
def payments(request):
    qs = m.Payment.objects.select_related("invoice__student__user", "collected_by").exclude(status="created")
    q = request.GET.get("q", "")
    if q:
        qs = qs.filter(Q(receipt_no__icontains=q) | Q(transaction_id__icontains=q) | Q(invoice__student__roll_no__icontains=q))
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "portal/fees/payments.html", {"page": page, "q": q})


@module_required("fees", FULL)
def refunds(request):
    form = RefundForm(request.POST or None)
    if request.method == "POST":
        if "decide" in request.POST:
            r = get_object_or_404(m.Refund, pk=request.POST.get("id"), status="requested")
            r.status = "processed" if request.POST["decide"] == "processed" else "rejected"
            r.processed_by = request.user
            r.save()
            audit(request, f"fees.refund_{r.status}", r)
            notify([r.invoice.student.user, r.invoice.student.parent], f"Refund {r.status}", f"Refund of ₹{r.amount} for {r.invoice.invoice_no} {r.status}.",
                   reverse("cms:my_fees"))
            messages.success(request, f"Refund {r.status}.")
            return redirect("cms:refunds")
        if form.is_valid():
            r = form.save(commit=False)
            if r.amount > r.invoice.paid:
                messages.error(request, "Refund cannot exceed the amount paid on the invoice.")
            else:
                r.save()
                audit(request, "fees.refund_request", r)
                messages.success(request, "Refund recorded.")
                return redirect("cms:refunds")
    return render(request, "portal/fees/refunds.html", {"form": form, "rows": m.Refund.objects.select_related("invoice__student__user", "processed_by")})


@module_required("fees", FULL, "view")
def fee_reports(request):
    today = timezone.localdate()
    invs = list(m.Invoice.objects.select_related("student__user", "student__course", "student__parent").prefetch_related("payments", "refunds"))
    defaulters = sorted([i for i in invs if i.balance > 0 and i.due_date < today], key=lambda i: i.due_date)
    by_course = {}
    for i in invs:
        c = by_course.setdefault(i.student.course.code, {"expected": Decimal("0"), "collected": Decimal("0")})
        c["expected"] += i.net
        c["collected"] += i.paid
    heads = m.Invoice.objects.aggregate(t=Sum("tuition_fee"), e=Sum("exam_fee"), o=Sum("other_fee"), c=Sum("concession"))
    by_method = list(m.Payment.objects.filter(status="success").values("method").annotate(s=Sum("amount")))
    if request.method == "POST" and "remind" in request.POST and can(request.user, "fees", FULL):
        for i in defaulters:
            notify([i.student.user, i.student.parent], "Fee overdue", f"{i.invoice_no}: ₹{i.balance} was due on {i.due_date:%d %b %Y}. Please pay immediately.",
                   reverse("cms:my_fees"), "danger", email=True)
        audit(request, "fees.defaulter_reminders", f"{len(defaulters)} students")
        messages.success(request, f"Reminders sent to {len(defaulters)} defaulter(s) and their parents.")
        return redirect("cms:fee_reports")
    return render(request, "portal/fees/reports.html", {
        "defaulters": defaulters, "by_course": by_course, "heads": heads,
        "total_expected": sum((v["expected"] for v in by_course.values()), Decimal("0")),
        "total_collected": sum((v["collected"] for v in by_course.values()), Decimal("0")),
        "chart": json.dumps({"labels": list(by_course), "expected": [float(v["expected"]) for v in by_course.values()],
                             "collected": [float(v["collected"]) for v in by_course.values()],
                             "methods": {"labels": [dict(m.Payment.METHODS)[r["method"]] for r in by_method], "data": [float(r["s"]) for r in by_method]}}),
        "can_edit": can(request.user, "fees", FULL),
    })
