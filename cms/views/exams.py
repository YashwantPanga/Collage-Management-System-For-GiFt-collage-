import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.utils import audit, notify

from .. import models as m
from ..forms import MarksSelectForm, RevaluationForm
from ..helpers import ensure_student_access, pick_student
from ..permissions import FULL, level, module_required


@module_required("exams", FULL, "view", "dept", "own", "ward")
def exam_schedule(request):
    lvl = level(request.user, "exams")
    qs = m.ExamSchedule.objects.select_related("exam__course", "subject").filter(exam__end_date__gte=timezone.localdate() - timezone.timedelta(days=60))
    student = None
    if lvl in ("own", "ward"):
        student, _ = pick_student(request)
        qs = qs.filter(exam__course=student.course, exam__semester=student.semester) if student else qs.none()
    elif lvl == "dept":
        qs = qs.filter(exam__course__department_id=request.user.department_id)
    return render(request, "portal/exams/schedule.html", {"rows": qs, "student": student, "can_edit": lvl == FULL})


@module_required("exams", FULL, "marks")
def marks_entry(request):
    form = MarksSelectForm(request.user, request.GET or None)
    ctx = {"form": form}
    if form.is_valid():
        exam, subject = form.cleaned_data["exam"], form.cleaned_data["subject"]
        if level(request.user, "exams") == "marks" and subject.faculty_id != request.user.id:
            raise PermissionDenied
        students = m.Student.objects.filter(course=exam.course, batch__current_semester=exam.semester, is_active=True).select_related("user")
        existing = {mk.student_id: mk for mk in m.Mark.objects.filter(exam=exam, subject=subject)}
        if request.method == "POST":
            if exam.marks_locked:
                messages.error(request, "Marks are locked for this exam.")
                return redirect(request.get_full_path())
            errors, saved = [], 0
            for s in students:
                raw = request.POST.get(f"m_{s.pk}", "").strip()
                absent = request.POST.get(f"ab_{s.pk}") == "1"
                if raw == "" and not absent:
                    continue
                try:
                    val = Decimal(raw or "0")
                except InvalidOperation:
                    errors.append(s.roll_no)
                    continue
                if val < 0 or val > exam.max_marks:
                    errors.append(s.roll_no)
                    continue
                mk = existing.get(s.pk)
                if mk and (mk.marks_obtained != val or mk.is_absent != absent):
                    audit(request, "marks.change", mk, f"{mk.marks_obtained} -> {val}")
                mk = mk or m.Mark(exam=exam, subject=subject, student=s)
                mk.marks_obtained, mk.is_absent, mk.entered_by = val, absent, request.user
                mk.save()
                saved += 1
            audit(request, "marks.submit", f"{exam} / {subject.code}", f"{saved} students")
            if errors:
                messages.warning(request, f"Invalid marks (0–{exam.max_marks}) for: {', '.join(errors)}")
            messages.success(request, f"Marks saved for {saved} student(s).")
            return redirect(request.get_full_path())
        ctx.update({"exam": exam, "subject": subject,
                    "rows": [{"s": s, "mk": existing.get(s.pk)} for s in students]})
    return render(request, "portal/exams/marks_entry.html", ctx)


@module_required("exams", FULL, "view", "dept")
def results_admin(request):
    lvl = level(request.user, "exams")
    exams = m.Exam.objects.select_related("course").annotate(entries=Count("marks"))
    if lvl == "dept":
        exams = exams.filter(course__department_id=request.user.department_id)
    if request.method == "POST" and lvl == FULL:
        exam = get_object_or_404(m.Exam, pk=request.POST.get("exam"))
        action = request.POST.get("action")
        if action == "publish":
            exam.is_published, exam.marks_locked, exam.published_at = True, True, timezone.now()
            exam.save()
            students = m.Student.objects.filter(marks__exam=exam).distinct().select_related("user", "parent")
            for s in students:
                notify([s.user, s.parent], "Results published", f"{exam.name} results are out.", reverse("cms:my_results"), "success", email=True)
            audit(request, "exam.publish", exam)
            messages.success(request, f"Results published and {students.count()} students notified.")
        elif action == "unpublish":
            exam.is_published = False
            exam.save()
            audit(request, "exam.unpublish", exam)
            messages.success(request, "Results withdrawn.")
        elif action in ("lock", "unlock"):
            exam.marks_locked = action == "lock"
            exam.save()
            audit(request, f"exam.{action}", exam)
            messages.success(request, f"Marks {action}ed.")
        return redirect("cms:results_admin")
    analytics = None
    exam_id = request.GET.get("exam")
    if exam_id:
        exam = get_object_or_404(exams, pk=exam_id)
        subj = m.Mark.objects.filter(exam=exam).values("subject__code", "subject__name").annotate(
            n=Count("id"), passed=Count("id", filter=~Q(grade="F")), avg=Avg("marks_obtained"), top=Max("marks_obtained"))
        grades = dict(m.Mark.objects.filter(exam=exam).values_list("grade").annotate(c=Count("id")))
        analytics = {
            "exam": exam, "subjects": [{**r, "pct": round(r["passed"] * 100 / r["n"], 1) if r["n"] else 0} for r in subj],
            "chart": json.dumps({"labels": [r["subject__code"] for r in subj], "pass": [round(r["passed"] * 100 / r["n"], 1) if r["n"] else 0 for r in subj],
                                 "avg": [float(r["avg"] or 0) for r in subj],
                                 "grades": {"labels": [g for _, g, _ in m.GRADE_SCALE], "data": [grades.get(g, 0) for _, g, _ in m.GRADE_SCALE]}}),
        }
    return render(request, "portal/exams/results_admin.html", {"exams": exams, "analytics": analytics, "can_publish": lvl == FULL})


def _result_sheets(student):
    sheets = []
    for exam in m.Exam.objects.filter(marks__student=student, is_published=True).distinct().order_by("start_date"):
        marks = m.Mark.objects.filter(exam=exam, student=student).select_related("subject")
        sheets.append({"exam": exam, "marks": marks, "sgpa": m.compute_gpa(marks) if exam.exam_type != "INT" else None,
                       "credits": sum(mk.subject.credits for mk in marks)})
    return sheets


@module_required("exams", "own", "ward")
def my_results(request):
    student, wards = pick_student(request)
    sheets = _result_sheets(student) if student else []
    return render(request, "portal/exams/my_results.html", {
        "student": student, "wards": wards, "sheets": sheets,
        "cgpa": student.cgpa() if student else None, "backlogs": student.backlogs() if student else [],
        "chart": json.dumps({"labels": [s["exam"].name for s in sheets if s["sgpa"] is not None],
                             "data": [float(s["sgpa"]) for s in sheets if s["sgpa"] is not None]}),
    })


@module_required("exams", FULL, "view", "dept", "own", "ward")
def marksheet(request, exam_pk, student_pk):
    student = get_object_or_404(m.Student.objects.select_related("user", "course", "batch"), pk=student_pk)
    ensure_student_access(request.user, student)
    exam = get_object_or_404(m.Exam, pk=exam_pk, is_published=True)
    marks = m.Mark.objects.filter(exam=exam, student=student).select_related("subject")
    return render(request, "portal/exams/marksheet.html", {"s": student, "exam": exam, "marks": marks, "sgpa": m.compute_gpa(marks), "cgpa": student.cgpa()})


@module_required("exams", "own", "ward")
def hall_ticket(request, exam_pk):
    student, _ = pick_student(request)
    if student is None:
        raise PermissionDenied
    exam = get_object_or_404(m.Exam, pk=exam_pk, course=student.course)
    issues = []
    att = student.attendance_percentage()
    if att is not None and att < exam.min_attendance:
        issues.append(f"Attendance {att}% is below the required {exam.min_attendance}% (Attendance → Examination eligibility).")
    if exam.require_fee_clearance and student.invoices.filter(semester__lte=exam.semester).exists():
        due = sum((i.balance for i in student.invoices.filter(semester__lte=exam.semester)), Decimal("0"))
        if due > 0:
            issues.append(f"Fee dues of ₹{due} pending (Fees → Examination clearance).")
    return render(request, "portal/exams/hall_ticket.html", {"s": student, "exam": exam, "issues": issues,
                                                            "schedule": exam.schedule.select_related("subject")})


@module_required("exams", FULL, "own")
def revaluations(request):
    lvl = level(request.user, "exams")
    if request.method == "POST":
        if lvl == "own":
            mark = get_object_or_404(m.Mark, pk=request.POST.get("mark"), student__user=request.user, exam__is_published=True)
            form = RevaluationForm(request.POST)
            if form.is_valid() and not mark.revaluations.filter(status__in=["requested", "in_progress"]).exists():
                rv = form.save(commit=False)
                rv.mark, rv.old_marks = mark, mark.marks_obtained
                rv.save()
                audit(request, "revaluation.request", rv)
                messages.success(request, "Revaluation request submitted.")
            else:
                messages.error(request, "A revaluation for this subject is already in progress.")
        else:
            rv = get_object_or_404(m.Revaluation.objects.select_related("mark__exam", "mark__student__user"), pk=request.POST.get("id"))
            status = request.POST.get("status")
            if status in dict(m.Revaluation.STATUS):
                rv.status, rv.handled_by = status, request.user
                new = request.POST.get("new_marks")
                if status == "completed" and new:
                    try:
                        val = Decimal(new)
                    except InvalidOperation:
                        val = None
                    if val is not None and 0 <= val <= rv.mark.exam.max_marks:
                        rv.new_marks = val
                        audit(request, "marks.revaluation_change", rv.mark, f"{rv.mark.marks_obtained} -> {val}")
                        rv.mark.marks_obtained = val
                        rv.mark.save()
                rv.save()
                notify(rv.mark.student.user, f"Revaluation {rv.get_status_display()}", f"{rv.mark.subject}: {rv.get_status_display()}"
                       + (f", marks {rv.old_marks} → {rv.new_marks}" if rv.new_marks is not None else ""), reverse("cms:my_results"))
                messages.success(request, "Revaluation updated.")
        return redirect("cms:revaluations")
    if lvl == "own":
        rows = m.Revaluation.objects.filter(mark__student__user=request.user)
    else:
        rows = m.Revaluation.objects.all()
    return render(request, "portal/exams/revaluations.html", {"rows": rows.select_related("mark__subject", "mark__exam", "mark__student__user"), "lvl": lvl})
