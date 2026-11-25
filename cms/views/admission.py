import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.models import Role
from accounts.utils import audit, notify

from .. import models as m
from ..forms import ApplicationForm, DocumentForm, EnrollForm, current_academic_year
from ..helpers import ensure_student_access
from ..permissions import FULL, can, level, module_required

User = get_user_model()

# Allowed workflow transitions: action -> (from statuses, to status, required level)
TRANSITIONS = {
    "review": ({"submitted"}, "review", (FULL,)),
    "verify": ({"submitted", "review"}, "verified", (FULL,)),
    "approve": ({"verified", "review"}, "approved", (FULL, "approve")),
    "reject": ({"submitted", "review", "verified", "approved"}, "rejected", (FULL, "approve")),
}


STEP_LABELS = [("submitted", "Submitted"), ("review", "Under Review"), ("verified", "Documents Verified"),
               ("approved", "Approved"), ("enrolled", "Enrolled")]


def _steps(app):
    keys = [k for k, _ in STEP_LABELS]
    idx = keys.index(app.status) if app.status in keys else 0
    steps = [{"label": label, "done": i <= idx} for i, (_, label) in enumerate(STEP_LABELS)]
    if app.status == "rejected":
        steps[-1] = {"label": "Rejected", "done": False, "bad": True}
    return steps


# ------------------------------------------------------------------ applicant side
@module_required("admission", "apply")
def my_applications(request):
    apps = m.Application.objects.filter(applicant=request.user).select_related("course").prefetch_related("documents")
    return render(request, "portal/admission/my_applications.html", {"apps": apps})


@login_required
def apply(request):
    if not can(request.user, "admission", "apply"):
        messages.info(request, "Online applications are submitted from a student account.")
        return redirect("cms:dashboard")
    initial = {"full_name": request.user.display_name, "email": request.user.email, "phone": request.user.phone}
    if request.GET.get("course"):
        initial["course"] = request.GET["course"]
    form = ApplicationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        app = form.save(commit=False)
        app.applicant = request.user
        app.academic_year = current_academic_year()
        app.save()
        audit(request, "admission.apply", app)
        notify(request.user, "Application submitted", f"Your application {app.application_no} for {app.course.name} was received.",
               reverse("cms:application_detail", args=[app.pk]), "success", email=True)
        notify(User.objects.filter(role=Role.ADMISSION), "New admission application",
               f"{app.full_name} applied for {app.course.name}.", reverse("cms:application_detail", args=[app.pk]))
        messages.success(request, f"Application {app.application_no} submitted. Now upload your documents.")
        return redirect("cms:application_detail", app.pk)
    return render(request, "portal/admission/apply.html", {"form": form})


# ------------------------------------------------------------------ officer side
@module_required("admission", FULL, "approve", "view")
def applications(request):
    qs = m.Application.objects.select_related("course", "course__department")
    if level(request.user, "admission") == "view" and request.user.role == Role.HOD:
        qs = qs.filter(course__department_id=request.user.department_id)
    status, course, q = request.GET.get("status", ""), request.GET.get("course", ""), request.GET.get("q", "").strip()
    if status:
        qs = qs.filter(status=status)
    if course:
        qs = qs.filter(course_id=course)
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(application_no__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q))
    counts = dict(m.Application.objects.values_list("status").annotate(n=Count("id")))
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "portal/admission/applications.html", {
        "page": page, "statuses": m.Application.Status.choices, "courses": m.Course.objects.all(),
        "status": status, "course": course, "q": q,
        "status_tabs": [(c, l, counts.get(c, 0)) for c, l in m.Application.Status.choices],
    })


@login_required
def application_detail(request, pk):
    app = get_object_or_404(m.Application.objects.select_related("course", "applicant", "student"), pk=pk)
    lvl = level(request.user, "admission")
    is_owner = app.applicant_id == request.user.id
    if not is_owner and lvl not in (FULL, "approve", "view"):
        raise PermissionDenied
    doc_form = DocumentForm()
    if request.method == "POST" and "upload" in request.POST:
        if not (is_owner or lvl == FULL) or app.status in ("rejected", "enrolled"):
            raise PermissionDenied
        doc_form = DocumentForm(request.POST, request.FILES)
        if doc_form.is_valid():
            doc = doc_form.save(commit=False)
            doc.application = app
            doc.save()
            audit(request, "admission.document_upload", doc)
            messages.success(request, "Document uploaded.")
            return redirect("cms:application_detail", pk)
    enroll_form = EnrollForm(app) if app.status == "approved" and lvl == FULL else None
    return render(request, "portal/admission/application_detail.html", {
        "app": app, "doc_form": doc_form, "is_owner": is_owner, "lvl": lvl, "enroll_form": enroll_form,
        "actions": [a for a, (src, _, lv) in TRANSITIONS.items() if app.status in src and (lvl in lv or lvl == FULL)],
        "steps": _steps(app),
    })


@module_required("admission", FULL)
def verify_document(request, pk):
    doc = get_object_or_404(m.ApplicationDocument, pk=pk)
    if request.method == "POST":
        doc.is_verified = request.POST.get("verified") == "1"
        doc.note = request.POST.get("note", "")[:200]
        doc.verified_by = request.user
        doc.save()
        audit(request, "admission.document_verify", doc, f"verified={doc.is_verified}")
        messages.success(request, f"{doc.get_doc_type_display()} marked {'verified' if doc.is_verified else 'not verified'}.")
    return redirect("cms:application_detail", doc.application_id)


@module_required("admission", FULL, "approve")
def application_action(request, pk, action):
    app = get_object_or_404(m.Application, pk=pk)
    if request.method != "POST" or action not in TRANSITIONS:
        return redirect("cms:application_detail", pk)
    src, dst, levels = TRANSITIONS[action]
    lvl = level(request.user, "admission")
    if app.status not in src or not (lvl == FULL or lvl in levels):
        messages.error(request, "That action is not allowed at this stage.")
        return redirect("cms:application_detail", pk)
    app.status = dst
    app.remarks = request.POST.get("remarks", app.remarks)
    app.reviewed_by = request.user
    app.save()
    audit(request, f"admission.{action}", app, app.remarks)
    if app.applicant:
        notify(app.applicant, f"Application {app.get_status_display()}",
               f"Your application {app.application_no} is now: {app.get_status_display()}. {app.remarks}",
               reverse("cms:application_detail", args=[app.pk]), "danger" if dst == "rejected" else "info", email=True)
    messages.success(request, f"Application moved to '{app.get_status_display()}'.")
    return redirect("cms:application_detail", pk)


@module_required("admission", FULL)
@transaction.atomic
def enroll(request, pk):
    app = get_object_or_404(m.Application, pk=pk, status="approved")
    form = EnrollForm(app, request.POST or None)
    if request.method != "POST" or not form.is_valid():
        messages.error(request, "Choose a batch to enroll the student." if request.method == "POST" else "")
        return redirect("cms:application_detail", pk)
    user = app.applicant
    if user is None:
        if User.objects.filter(username=form.cleaned_data["username"]).exists():
            messages.error(request, "That username is taken.")
            return redirect("cms:application_detail", pk)
        first, _, last = app.full_name.partition(" ")
        user = User(username=form.cleaned_data["username"], first_name=first, last_name=last, email=app.email,
                    phone=app.phone, role=Role.STUDENT)
        user.set_password(form.cleaned_data["password"])
        user.save()
    user.role = Role.STUDENT
    user.save(update_fields=["role"])
    batch = form.cleaned_data["batch"]
    student = m.Student.objects.create(
        user=user, course=app.course, batch=batch, category=app.category, date_of_birth=app.date_of_birth,
        gender=app.gender, address=app.address,
    )
    app.student = student
    app.status = "enrolled"
    app.save()
    # Admission -> Fees integration: assign the fee structure of the current semester.
    fs = m.FeeStructure.objects.filter(course=app.course, semester=batch.current_semester, category=app.category).order_by("-academic_year").first() \
        or m.FeeStructure.objects.filter(course=app.course, semester=batch.current_semester).order_by("-academic_year").first()
    if fs:
        m.Invoice.objects.create(student=student, fee_structure=fs, semester=fs.semester, tuition_fee=fs.tuition_fee,
                                 exam_fee=fs.exam_fee, other_fee=fs.development_fee + fs.other_fee, due_date=fs.due_date)
    m.PlacementProfile.objects.get_or_create(student=student)
    audit(request, "admission.enroll", student)
    notify(user, "Welcome to GIFT Autonomous!", f"You are enrolled in {app.course.name}. Your roll number is {student.roll_no}.",
           reverse("cms:dashboard"), "success", email=True)
    messages.success(request, f"Enrolled. Roll number generated: {student.roll_no}")
    return redirect("cms:student_detail", student.pk)


@module_required("admission", FULL, "approve", "view")
def students(request):
    qs = m.Student.objects.select_related("user", "course", "batch")
    if request.user.role == Role.HOD:
        qs = qs.filter(course__department_id=request.user.department_id)
    q, course, batch = request.GET.get("q", "").strip(), request.GET.get("course", ""), request.GET.get("batch", "")
    if q:
        qs = qs.filter(Q(roll_no__icontains=q) | Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(user__email__icontains=q))
    if course:
        qs = qs.filter(course_id=course)
    if batch:
        qs = qs.filter(batch_id=batch)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "portal/admission/students.html", {
        "page": page, "q": q, "course": course, "batch": batch, "courses": m.Course.objects.all(), "batches": m.Batch.objects.select_related("course"),
    })


@login_required
def student_detail(request, pk):
    student = get_object_or_404(m.Student.objects.select_related("user", "course", "batch", "parent"), pk=pk)
    staff_ok = any(can(request.user, mod, FULL, "approve", "view", "dept", "mark") for mod in ["admission", "attendance", "fees", "exams"])
    if request.user.role in (Role.STUDENT, Role.PARENT) or not staff_ok:
        ensure_student_access(request.user, student)
    if request.user.role == Role.HOD and student.course.department_id != request.user.department_id and not request.user.is_superuser:
        raise PermissionDenied
    if request.method == "POST" and can(request.user, "admission", FULL) and "parent" in request.POST:
        parent = User.objects.filter(pk=request.POST.get("parent") or 0, role=Role.PARENT).first()
        student.parent = parent
        student.save(update_fields=["parent"])
        audit(request, "student.link_parent", student, str(parent))
        messages.success(request, "Parent link updated.")
        return redirect("cms:student_detail", pk)
    subjects = m.Subject.objects.filter(course=student.course, semester=student.semester)
    return render(request, "portal/admission/student_detail.html", {
        "s": student,
        "attendance": student.attendance_percentage(),
        "subject_att": [(sub, student.attendance_percentage(sub)) for sub in subjects],
        "invoices": student.invoices.all(),
        "cgpa": student.cgpa(),
        "backlogs": student.backlogs(),
        "parents": User.objects.filter(role=Role.PARENT) if can(request.user, "admission", FULL) else None,
        "can_edit": can(request.user, "admission", FULL),
    })


@module_required("reports")
def admission_report(request):
    rows = m.Course.objects.annotate(
        total=Count("applications"),
        approved=Count("applications", filter=Q(applications__status__in=["approved", "enrolled"])),
        rejected=Count("applications", filter=Q(applications__status="rejected")),
        enrolled=Count("students", filter=Q(students__is_active=True), distinct=True),
    ).select_related("department")
    data = [{"c": c, "util": round(c.enrolled * 100 / c.seats, 1) if c.seats else 0} for c in rows]
    chart = json.dumps({"labels": [d["c"].code for d in data], "apps": [d["c"].total for d in data], "enrolled": [d["c"].enrolled for d in data]})
    return render(request, "portal/admission/report.html", {"rows": data, "chart": chart})
