import calendar
from datetime import date
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.utils import audit, notify

from .. import models as m
from ..forms import LeaveForm
from ..permissions import FULL, level, module_required

User = get_user_model()


def _faculty_scope(user):
    qs = m.FacultyProfile.objects.select_related("user", "department")
    if level(user, "faculty") == "dept":
        qs = qs.filter(department_id=user.department_id)
    return qs


class OwnProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    phone = forms.CharField(max_length=20, required=False)

    class Meta:
        model = m.FacultyProfile
        fields = ["qualification", "specialization", "experience_years", "bio"]


@module_required("faculty", "own", "dept")
def my_faculty(request):
    prof = getattr(request.user, "faculty_profile", None)
    if prof is None:
        messages.warning(request, "Your faculty record has not been created yet. Please contact the administrator.")
        return redirect("cms:dashboard")
    form = OwnProfileForm(request.POST or None, instance=prof, initial={
        "first_name": request.user.first_name, "last_name": request.user.last_name, "phone": request.user.phone})
    if request.method == "POST" and form.is_valid():
        form.save()
        u = request.user
        u.first_name, u.last_name, u.phone = form.cleaned_data["first_name"], form.cleaned_data["last_name"], form.cleaned_data["phone"]
        u.save()
        messages.success(request, "Profile updated.")
        return redirect("cms:my_faculty")
    month_start = timezone.localdate().replace(day=1)
    return render(request, "portal/faculty/my_profile.html", {
        "prof": prof, "form": form,
        "subjects": m.Subject.objects.filter(faculty=request.user).select_related("course"),
        "attendance": prof.attendance.filter(date__gte=month_start),
        "reviews": prof.reviews.all(),
    })


@module_required("faculty", FULL, "approve", "dept", "own")
def leaves(request):
    user = request.user
    lvl = level(user, "faculty")
    prof = getattr(user, "faculty_profile", None)
    form = LeaveForm(request.POST or None) if prof else None
    if request.method == "POST" and "apply" in request.POST:
        if not prof:
            raise PermissionDenied
        if form.is_valid():
            leave = form.save(commit=False)
            leave.faculty = prof
            leave.save()
            audit(request, "leave.apply", leave)
            approvers = User.objects.filter(Q(role=Role.HOD, department_id=prof.department_id) | Q(role=Role.PRINCIPAL))
            if user.role == Role.HOD:
                approvers = User.objects.filter(role=Role.PRINCIPAL)
            notify(approvers, "Leave request", f"{user.display_name} requested {leave.get_leave_type_display()} ({leave.days} days).",
                   reverse("cms:leaves"))
            messages.success(request, "Leave request submitted.")
            return redirect("cms:leaves")
    mine = prof.leaves.all() if prof else []
    to_approve = m.LeaveRequest.objects.none()
    if lvl in (FULL, "approve"):
        to_approve = m.LeaveRequest.objects.select_related("faculty__user", "faculty__department")
    elif lvl == "dept":
        to_approve = m.LeaveRequest.objects.filter(faculty__department_id=user.department_id).exclude(faculty__user=user).select_related("faculty__user")
    status = request.GET.get("status", "pending")
    if status:
        to_approve = to_approve.filter(status=status)
    return render(request, "portal/faculty/leaves.html", {"form": form, "mine": mine, "to_approve": to_approve[:100], "status": status, "can_approve": lvl in (FULL, "approve", "dept")})


@module_required("faculty", FULL, "approve", "dept")
def leave_decide(request, pk, decision):
    leave = get_object_or_404(m.LeaveRequest.objects.select_related("faculty__user"), pk=pk)
    lvl = level(request.user, "faculty")
    if lvl == "dept" and (leave.faculty.department_id != request.user.department_id or leave.faculty.user_id == request.user.id):
        raise PermissionDenied
    if request.method == "POST" and decision in ("approved", "rejected") and leave.status == "pending":
        leave.status = decision
        leave.approved_by = request.user
        leave.remarks = request.POST.get("remarks", "")[:200]
        leave.save()
        if decision == "approved":  # feed faculty attendance -> payroll
            d = leave.from_date
            while d <= leave.to_date:
                m.FacultyAttendance.objects.update_or_create(faculty=leave.faculty, date=d, defaults={"status": "L"})
                d += timezone.timedelta(days=1)
        audit(request, f"leave.{decision}", leave)
        notify(leave.faculty.user, f"Leave {decision}", f"Your {leave.get_leave_type_display()} from {leave.from_date} to {leave.to_date} was {decision}.",
               reverse("cms:leaves"), "success" if decision == "approved" else "danger", email=True)
        messages.success(request, f"Leave {decision}.")
    return redirect("cms:leaves")


@module_required("faculty", FULL, "dept")
def faculty_attendance(request):
    day = request.POST.get("date") or request.GET.get("date") or timezone.localdate().isoformat()
    day = date.fromisoformat(day)
    profiles = _faculty_scope(request.user)
    if request.method == "POST":
        for p in profiles:
            status = request.POST.get(f"s_{p.pk}")
            if status in dict(m.FacultyAttendance.STATUS):
                m.FacultyAttendance.objects.update_or_create(faculty=p, date=day, defaults={
                    "status": status, "check_in": request.POST.get(f"in_{p.pk}") or None, "check_out": request.POST.get(f"out_{p.pk}") or None})
        audit(request, "faculty_attendance.mark", day)
        messages.success(request, f"Faculty attendance saved for {day:%d %b %Y}.")
        return redirect(f"{reverse('cms:faculty_attendance')}?date={day.isoformat()}")
    existing = {a.faculty_id: a for a in m.FacultyAttendance.objects.filter(date=day, faculty__in=profiles)}
    rows = [{"p": p, "a": existing.get(p.pk)} for p in profiles]
    return render(request, "portal/faculty/attendance.html", {"rows": rows, "day": day, "statuses": m.FacultyAttendance.STATUS})


@module_required("faculty", FULL, "approve", "dept", "own")
def timetable(request):
    user = request.user
    lvl = level(user, "faculty")
    batches = m.Batch.objects.select_related("course")
    if lvl == "dept":
        batches = batches.filter(course__department_id=user.department_id)
    batch_id = request.GET.get("batch")
    if lvl == "own":
        slots = m.TimetableSlot.objects.filter(faculty=user)
        title = "My Timetable"
    else:
        batch = batches.filter(pk=batch_id).first() if batch_id else batches.first()
        slots = m.TimetableSlot.objects.filter(batch=batch) if batch else m.TimetableSlot.objects.none()
        title = f"Timetable — {batch}" if batch else "Timetable"
    slots = slots.select_related("subject", "faculty", "batch")
    periods = sorted({s.period for s in slots}) or [1, 2, 3, 4, 5, 6]
    grid = []
    for d, dname in m.TimetableSlot.DAYS:
        grid.append({"day": dname, "cells": [[s for s in slots if s.day == d and s.period == p] for p in periods]})
    return render(request, "portal/faculty/timetable.html", {
        "grid": grid, "periods": periods, "title": title, "batches": batches if lvl != "own" else None,
        "batch_id": batch_id, "can_edit": lvl in (FULL, "dept"),
    })


@module_required("attendance", "own", "ward")
def class_timetable(request):
    from ..helpers import pick_student

    student, wards = pick_student(request)
    slots = m.TimetableSlot.objects.filter(batch=student.batch).select_related("subject", "faculty", "batch") if student else []
    periods = sorted({s.period for s in slots}) or [1, 2, 3, 4, 5, 6]
    grid = [{"day": dname, "cells": [[s for s in slots if s.day == d and s.period == p] for p in periods]}
            for d, dname in m.TimetableSlot.DAYS]
    return render(request, "portal/faculty/timetable.html", {
        "grid": grid, "periods": periods, "title": f"Class Timetable — {student.batch}" if student else "Class Timetable",
        "batches": None, "student_view": True, "wards": wards, "student": student,
    })


@module_required("faculty", FULL, "approve", "dept")
def workload(request):
    rows = []
    for p in _faculty_scope(request.user).annotate(slots=Count("user__timetable_slots", distinct=True), subj=Count("user__subjects", distinct=True)):
        hours = m.Subject.objects.filter(faculty=p.user).aggregate(h=Sum("hours_per_week"))["h"] or 0
        rows.append({"p": p, "slots": p.slots, "subjects": p.subj, "hours": hours,
                     "status": "Overloaded" if hours > 18 else ("Under-utilised" if hours < 8 else "Balanced")})
    return render(request, "portal/faculty/workload.html", {"rows": rows})


def _compute_payroll(profile, month):
    days_in_month = calendar.monthrange(month.year, month.month)[1]
    end = month.replace(day=days_in_month)
    att = profile.attendance.filter(date__range=(month, end))
    working_days = sum(1 for d in range(1, days_in_month + 1) if date(month.year, month.month, d).weekday() != 6)
    present = Decimal(att.filter(status="P").count()) + Decimal(att.filter(status="H").count()) / 2
    approved_days = Decimal("0")
    lop = Decimal("0")
    for lv in profile.leaves.filter(status="approved", from_date__lte=end, to_date__gte=month):
        days = Decimal((min(lv.to_date, end) - max(lv.from_date, month)).days + 1)
        if lv.leave_type == "LOP":
            lop += days
        else:
            approved_days += days
    absent = Decimal(att.filter(status="A").count()) + Decimal(att.filter(status="H").count()) / 2
    lop += absent
    basic = profile.basic_salary
    allowances = (basic * Decimal("0.40")).quantize(Decimal("0.01"))  # DA + HRA
    per_day = (basic + allowances) / Decimal(working_days)
    deductions = (per_day * lop + basic * Decimal("0.12")).quantize(Decimal("0.01"))  # LOP + PF
    net = (basic + allowances - deductions).quantize(Decimal("0.01"))
    return dict(working_days=working_days, days_present=present, paid_leave_days=approved_days, lop_days=lop,
                basic=basic, allowances=allowances, deductions=deductions, net_pay=max(net, Decimal("0")))


@module_required("faculty", FULL, "payroll", "approve", "own")
def payroll(request):
    lvl = level(request.user, "faculty")
    month_str = request.POST.get("month") or request.GET.get("month") or timezone.localdate().strftime("%Y-%m")
    month = date.fromisoformat(month_str + "-01")
    if request.method == "POST" and lvl in (FULL, "payroll"):
        if "generate" in request.POST:
            n = 0
            for p in m.FacultyProfile.objects.all():
                pr = m.Payroll.objects.filter(faculty=p, month=month).first()
                if pr and pr.is_paid:
                    continue
                m.Payroll.objects.update_or_create(faculty=p, month=month, defaults=_compute_payroll(p, month))
                n += 1
            audit(request, "payroll.generate", month_str, f"{n} records")
            messages.success(request, f"Payroll generated for {n} faculty for {month:%B %Y} from attendance and leave data.")
        elif "pay" in request.POST:
            ids = request.POST.getlist("ids")
            m.Payroll.objects.filter(pk__in=ids, month=month).update(is_paid=True)
            audit(request, "payroll.mark_paid", month_str, f"{len(ids)} records")
            messages.success(request, "Selected payroll records marked as paid.")
        return redirect(f"{reverse('cms:payroll')}?month={month_str}")
    qs = m.Payroll.objects.filter(month=month).select_related("faculty__user", "faculty__department")
    if lvl == "own":
        qs = m.Payroll.objects.filter(faculty__user=request.user).select_related("faculty__user")
    total = qs.aggregate(s=Sum("net_pay"))["s"] or 0
    return render(request, "portal/faculty/payroll.html", {"rows": qs, "month": month_str, "total": total, "lvl": lvl, "can_run": lvl in (FULL, "payroll")})


@module_required("faculty", FULL, "payroll", "approve", "own")
def payslip(request, pk):
    pr = get_object_or_404(m.Payroll.objects.select_related("faculty__user", "faculty__department"), pk=pk)
    if level(request.user, "faculty") == "own" and pr.faculty.user_id != request.user.id:
        raise PermissionDenied
    return render(request, "portal/faculty/payslip.html", {"pr": pr})
