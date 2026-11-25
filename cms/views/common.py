import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import AuditLog, Notification, Role
from website.models import Notice

from .. import models as m
from ..helpers import students_for
from ..permissions import can, module_required


def _institution_stats(user):
    """Institution-wide analytics (section 3.7). HODs get department-scoped numbers."""
    dept = user.department_id if user.role == Role.HOD else None
    students = m.Student.objects.filter(is_active=True)
    faculty = m.FacultyProfile.objects.all()
    apps = m.Application.objects.all()
    invoices = m.Invoice.objects.all()
    records = m.AttendanceRecord.objects.all()
    marks = m.Mark.objects.filter(exam__is_published=True)
    placements = m.PlacementApplication.objects.all()
    if dept:
        students = students.filter(course__department_id=dept)
        faculty = faculty.filter(department_id=dept)
        apps = apps.filter(course__department_id=dept)
        invoices = invoices.filter(student__course__department_id=dept)
        records = records.filter(student__course__department_id=dept)
        marks = marks.filter(student__course__department_id=dept)
        placements = placements.filter(student__course__department_id=dept)

    dept_students = list(students.values("course__department__code").annotate(n=Count("id")).order_by("course__department__code"))
    dept_faculty = list(faculty.values("department__code").annotate(n=Count("id")).order_by("department__code"))

    total_rec = records.count()
    present = records.filter(status__in=["P", "L"]).count()
    dept_att = []
    for row in records.values("student__course__department__code").annotate(
        total=Count("id"), present=Count("id", filter=Q(status__in=["P", "L"]))
    ):
        dept_att.append({"dept": row["student__course__department__code"], "pct": round(row["present"] * 100 / row["total"], 1)})

    expected = sum((i.net for i in invoices), Decimal("0"))
    collected = m.Payment.objects.filter(invoice__in=invoices, status="success").aggregate(s=Sum("amount"))["s"] or Decimal("0")
    pending = max(expected - collected, Decimal("0"))
    monthly_fee = list(
        m.Payment.objects.filter(invoice__in=invoices, status="success", paid_at__isnull=False)
        .annotate(mo=TruncMonth("paid_at")).values("mo").annotate(s=Sum("amount")).order_by("mo")
    )

    total_marks = marks.count()
    passed = marks.exclude(grade="F").count()
    pass_by_exam = []
    for row in marks.values("exam__name").annotate(t=Count("id"), p=Count("id", filter=~Q(grade="F"))).order_by("exam__name")[:8]:
        pass_by_exam.append({"exam": row["exam__name"], "pct": round(row["p"] * 100 / row["t"], 1)})

    placed_students = placements.filter(stage="selected").values("student").distinct().count()
    registered = m.PlacementProfile.objects.filter(is_registered=True)
    if dept:
        registered = registered.filter(student__course__department_id=dept)
    registered = registered.count()
    status_counts = {s: 0 for s, _ in m.Application.Status.choices}
    for row in apps.values("status").annotate(n=Count("id")):
        status_counts[row["status"]] = row["n"]
    app_trend = list(apps.annotate(mo=TruncMonth("created_at")).values("mo").annotate(n=Count("id")).order_by("mo"))

    return {
        "total_students": students.count(),
        "total_faculty": faculty.count(),
        "total_courses": m.Course.objects.filter(department_id=dept).count() if dept else m.Course.objects.count(),
        "attendance_pct": round(present * 100 / total_rec, 1) if total_rec else None,
        "fee_expected": expected, "fee_collected": collected, "fee_pending": pending,
        "fee_pct": round(collected * 100 / expected, 1) if expected else None,
        "pass_pct": round(passed * 100 / total_marks, 1) if total_marks else None,
        "placed": placed_students, "registered_for_placement": registered,
        "placement_pct": round(placed_students * 100 / registered, 1) if registered else None,
        "companies": m.Company.objects.filter(is_approved=True).count(),
        "highest_package": placements.filter(stage="selected").order_by("-offered_package").values_list("offered_package", flat=True).first(),
        "app_status": status_counts,
        "applications_total": apps.count(),
        "pending_leaves": m.LeaveRequest.objects.filter(status="pending", **({"faculty__department_id": dept} if dept else {})).count(),
        "charts": json.dumps({
            "deptStudents": {"labels": [r["course__department__code"] for r in dept_students], "data": [r["n"] for r in dept_students]},
            "deptFaculty": {"labels": [r["department__code"] for r in dept_faculty], "data": [r["n"] for r in dept_faculty]},
            "deptAttendance": {"labels": [r["dept"] for r in dept_att], "data": [r["pct"] for r in dept_att]},
            "fee": {"labels": [r["mo"].strftime("%b %y") for r in monthly_fee], "data": [float(r["s"]) for r in monthly_fee]},
            "feeSplit": {"labels": ["Collected", "Pending"], "data": [float(collected), float(pending)]},
            "passByExam": {"labels": [r["exam"] for r in pass_by_exam], "data": [r["pct"] for r in pass_by_exam]},
            "appStatus": {"labels": [str(l) for _, l in m.Application.Status.choices], "data": list(status_counts.values())},
            "appTrend": {"labels": [r["mo"].strftime("%b %y") for r in app_trend], "data": [r["n"] for r in app_trend]},
        }),
    }


def _student_summary(student):
    today = timezone.localdate()
    exams = m.ExamSchedule.objects.filter(exam__course=student.course, exam__semester=student.semester, date__gte=today)[:5]
    subjects = m.Subject.objects.filter(course=student.course, semester=student.semester)
    subject_att = []
    for s in subjects:
        pct = student.attendance_percentage(s)
        subject_att.append({"subject": s, "pct": pct})
    return {
        "student": student,
        "attendance": student.attendance_percentage(),
        "subject_att": subject_att,
        "cgpa": student.cgpa(),
        "backlogs": len(student.backlogs()),
        "fee_due": student.fee_due(),
        "upcoming_exams": exams,
        "today_classes": m.TimetableSlot.objects.filter(batch=student.batch, day=today.weekday()).select_related("subject", "faculty"),
        "job_apps": student.job_applications.select_related("job__company")[:5],
        "charts": json.dumps({
            "subjects": {"labels": [a["subject"].code for a in subject_att], "data": [a["pct"] or 0 for a in subject_att]},
        }),
    }


@login_required
def dashboard(request):
    user = request.user
    ctx = {"today": timezone.localdate()}
    if user.role in (Role.STUDENT, Role.PARENT):
        students = list(students_for(user).select_related("user", "course", "batch"))
        ctx["summaries"] = [_student_summary(s) for s in students]
        if user.role == Role.STUDENT:
            ctx["applications"] = m.Application.objects.filter(applicant=user)
            ctx["open_jobs"] = m.JobPosting.objects.filter(is_open=True, deadline__gte=timezone.localdate()).count()
        ctx["notices"] = Notice.objects.filter(is_published=True)[:5]
        return render(request, "portal/dashboard_student.html", ctx)
    if user.role == Role.FACULTY:
        prof = getattr(user, "faculty_profile", None)
        today = timezone.localdate()
        ctx.update({
            "profile": prof,
            "subjects": m.Subject.objects.filter(faculty=user).select_related("course"),
            "today_classes": m.TimetableSlot.objects.filter(faculty=user, day=today.weekday()).select_related("subject", "batch"),
            "recent_sessions": m.AttendanceSession.objects.filter(faculty=user)[:6],
            "leaves": prof.leaves.all()[:5] if prof else [],
            "open_exams": m.Exam.objects.filter(marks_locked=False, is_published=False, course__subjects__faculty=user).distinct()[:5],
        })
        return render(request, "portal/dashboard_faculty.html", ctx)
    if user.role == Role.RECRUITER:
        companies = m.Company.objects.filter(recruiters=user)
        jobs = m.JobPosting.objects.filter(company__in=companies).annotate(n=Count("applications"))
        ctx.update({"companies": companies, "jobs": jobs,
                    "applicants": m.PlacementApplication.objects.filter(job__in=jobs).count(),
                    "selected": m.PlacementApplication.objects.filter(job__in=jobs, stage="selected").count()})
        return render(request, "portal/dashboard_recruiter.html", ctx)
    ctx.update(_institution_stats(user))
    ctx["show"] = {mod: can(user, mod) for mod in ["admission", "faculty", "attendance", "fees", "exams", "placement"]}
    ctx["recent_apps"] = m.Application.objects.select_related("course")[:6] if ctx["show"]["admission"] else []
    ctx["recent_payments"] = m.Payment.objects.filter(status="success").select_related("invoice__student__user")[:6] if ctx["show"]["fees"] else []
    ctx["recent_audit"] = AuditLog.objects.select_related("user")[:8] if can(user, "audit") else []
    return render(request, "portal/dashboard_admin.html", ctx)


@login_required
def notifications(request):
    qs = request.user.notifications.all()
    if request.method == "POST":
        qs.filter(is_read=False).update(is_read=True)
        return redirect("cms:notifications")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "portal/notifications.html", {"page": page})


@login_required
def notification_open(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.is_read = True
    n.save(update_fields=["is_read"])
    return redirect(n.link or "cms:notifications")


@login_required
def notification_feed(request):
    """Polled by the portal header for live notification updates."""
    since = request.GET.get("since")
    qs = request.user.notifications.all()
    latest = list(qs.filter(is_read=False).values("id", "title", "level", "created_at")[:5])
    return JsonResponse({
        "unread": qs.filter(is_read=False).count(),
        "latest": [{**n, "created_at": timezone.localtime(n["created_at"]).strftime("%d %b %H:%M")} for n in latest],
        "since": since,
    })


@module_required("audit")
def audit_log(request):
    qs = AuditLog.objects.select_related("user")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(action__icontains=q) | Q(target__icontains=q) | Q(user__username__icontains=q))
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "portal/audit_log.html", {"page": page, "q": q})
