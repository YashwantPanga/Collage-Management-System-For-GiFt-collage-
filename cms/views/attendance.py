import base64
import io
import json
from datetime import date

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.utils import audit, notify

from .. import models as m
from ..forms import SessionForm
from ..helpers import pick_student
from ..permissions import FULL, level, module_required


def _can_mark(user, session):
    lvl = level(user, "attendance")
    if lvl == FULL:
        return True
    if lvl == "dept":
        return session.subject.course.department_id == user.department_id
    if lvl == "mark":
        return session.subject.faculty_id == user.id
    return False


@module_required("attendance", FULL, "mark", "dept")
def take_attendance(request):
    form = SessionForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        session, _ = m.AttendanceSession.objects.get_or_create(
            subject=form.cleaned_data["subject"], batch=form.cleaned_data["batch"],
            date=form.cleaned_data["date"], period=form.cleaned_data["period"],
            defaults={"faculty": request.user},
        )
        return redirect("cms:attendance_session", session.pk)
    sessions = m.AttendanceSession.objects.select_related("subject", "batch").annotate(
        total=Count("records"), present=Count("records", filter=Q(records__status__in=["P", "L"])))
    if level(request.user, "attendance") == "mark":
        sessions = sessions.filter(subject__faculty=request.user)
    elif level(request.user, "attendance") == "dept":
        sessions = sessions.filter(subject__course__department_id=request.user.department_id)
    return render(request, "portal/attendance/take.html", {"form": form, "sessions": sessions[:20]})


@module_required("attendance", FULL, "mark", "dept")
def attendance_session(request, pk):
    session = get_object_or_404(m.AttendanceSession.objects.select_related("subject__course", "batch"), pk=pk)
    if not _can_mark(request.user, session):
        raise PermissionDenied
    students = m.Student.objects.filter(batch=session.batch, is_active=True).select_related("user")
    if request.method == "POST":
        if "open_qr" in request.POST:
            session.open_qr(settings.QR_ATTENDANCE_MINUTES)
            messages.success(request, f"QR code is live for {settings.QR_ATTENDANCE_MINUTES} minutes.")
            return redirect("cms:attendance_session", pk)
        if "close_qr" in request.POST:
            session.qr_expires_at = timezone.now()
            session.save(update_fields=["qr_expires_at"])
            return redirect("cms:attendance_session", pk)
        for s in students:
            status = request.POST.get(f"st_{s.pk}", "A")
            rec, created = m.AttendanceRecord.objects.get_or_create(session=session, student=s, defaults={"status": status})
            if not created and rec.method != "qr" and rec.status != status:
                rec.status = status
                rec.method = "manual"
                rec.save()
            elif not created and rec.method == "qr" and status != "P":
                rec.status, rec.method = status, "manual"
                rec.save()
        audit(request, "attendance.mark", session)
        alerts = _shortage_alerts(students, session.subject)
        messages.success(request, f"Attendance saved for {students.count()} students." + (f" {alerts} shortage alert(s) sent." if alerts else ""))
        return redirect("cms:attendance_session", pk)
    records = {r.student_id: r for r in session.records.all()}
    rows = [{"s": s, "r": records.get(s.pk), "pct": s.attendance_percentage(session.subject)} for s in students]
    qr_img = None
    if session.qr_active:
        url = request.build_absolute_uri(reverse("cms:qr_mark", args=[session.qr_token]))
        buf = io.BytesIO()
        qrcode.make(url, box_size=8, border=2).save(buf, format="PNG")
        qr_img = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return render(request, "portal/attendance/session.html", {"session": session, "rows": rows, "qr_img": qr_img})


def _shortage_alerts(students, subject=None, min_classes=5):
    """Notify students & parents whose attendance fell below the threshold (once per day per student)."""
    threshold = settings.ATTENDANCE_THRESHOLD
    sent = 0
    today = timezone.localdate()
    for s in students:
        qs = s.attendance_records.all()
        if qs.count() < min_classes:
            continue
        pct = s.attendance_percentage()
        if pct is not None and pct < threshold:
            if s.user.notifications.filter(title__startswith="Attendance shortage", created_at__date=today).exists():
                continue
            msg = f"{s.user.display_name} ({s.roll_no}) attendance is {pct}% — below the required {threshold:.0f}%."
            notify([s.user, s.parent], "Attendance shortage", msg, reverse("cms:my_attendance"), "warning", email=True)
            sent += 1
    return sent


@login_required
def qr_mark(request, token):
    session = m.AttendanceSession.objects.filter(qr_token=token).select_related("subject", "batch").first()
    if request.user.role != Role.STUDENT or not hasattr(request.user, "student"):
        messages.error(request, "Only students can mark attendance by QR.")
        return redirect("cms:dashboard")
    if session is None or not session.qr_active:
        messages.error(request, "This QR code has expired. Ask your faculty to show a new one.")
        return redirect("cms:my_attendance")
    student = request.user.student
    if student.batch_id != session.batch_id:
        messages.error(request, "You are not part of this class.")
        return redirect("cms:my_attendance")
    m.AttendanceRecord.objects.update_or_create(session=session, student=student, defaults={"status": "P", "method": "qr"})
    audit(request, "attendance.qr", session)
    messages.success(request, f"Marked present for {session.subject.name} ({session.date:%d %b}, period {session.period}).")
    return redirect("cms:my_attendance")


@module_required("attendance", "own", "ward")
def my_attendance(request):
    student, wards = pick_student(request)
    ctx = {"student": student, "wards": wards}
    if student:
        subjects = m.Subject.objects.filter(course=student.course, semester=student.semester)
        rows = []
        for sub in subjects:
            recs = student.attendance_records.filter(session__subject=sub)
            total = recs.count()
            present = recs.filter(status__in=["P", "L"]).count()
            rows.append({"sub": sub, "total": total, "present": present, "pct": round(present * 100 / total, 1) if total else None})
        ctx.update({
            "rows": rows, "overall": student.attendance_percentage(),
            "recent": student.attendance_records.select_related("session__subject").order_by("-session__date", "-session__period")[:30],
            "chart": json.dumps({"labels": [r["sub"].code for r in rows], "data": [r["pct"] or 0 for r in rows]}),
        })
    return render(request, "portal/attendance/mine.html", ctx)


@module_required("attendance", FULL, "view", "dept", "mark")
def attendance_report(request):
    lvl = level(request.user, "attendance")
    batches = m.Batch.objects.select_related("course")
    if lvl == "dept":
        batches = batches.filter(course__department_id=request.user.department_id)
    elif lvl == "mark":
        batches = batches.filter(course__subjects__faculty=request.user).distinct()
    batch = batches.filter(pk=request.GET.get("batch") or 0).first() or batches.first()
    month = request.GET.get("month") or timezone.localdate().strftime("%Y-%m")
    start = date.fromisoformat(month + "-01")
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    rows, subjects = [], []
    if batch:
        subjects = list(m.Subject.objects.filter(course=batch.course, semester=batch.current_semester))
        for s in m.Student.objects.filter(batch=batch).select_related("user"):
            recs = s.attendance_records.filter(session__date__gte=start, session__date__lt=end)
            per = []
            for sub in subjects:
                r = recs.filter(session__subject=sub)
                t = r.count()
                per.append(round(r.filter(status__in=["P", "L"]).count() * 100 / t, 1) if t else None)
            t = recs.count()
            overall = round(recs.filter(status__in=["P", "L"]).count() * 100 / t, 1) if t else None
            rows.append({"s": s, "per": per, "overall": overall, "total": t})
    if request.method == "POST" and batch and "alerts" in request.POST:
        n = _shortage_alerts(m.Student.objects.filter(batch=batch).select_related("user", "parent"), min_classes=1)
        audit(request, "attendance.shortage_alerts", batch, f"{n} alerts")
        messages.success(request, f"{n} shortage notification(s) sent to students and parents.")
        return redirect(f"{reverse('cms:attendance_report')}?batch={batch.pk}&month={month}")
    return render(request, "portal/attendance/report.html", {
        "batches": batches, "batch": batch, "month": month, "rows": rows, "subjects": subjects,
        "threshold": settings.ATTENDANCE_THRESHOLD,
    })
