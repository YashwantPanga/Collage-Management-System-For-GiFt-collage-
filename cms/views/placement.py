import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.utils import audit, notify

from .. import models as m
from ..forms import JobForm, PlacementProfileForm, StageForm
from ..permissions import FULL, level, module_required


def _student(request):
    s = getattr(request.user, "student", None)
    if s is None:
        messages.warning(request, "Placement is available after enrollment.")
    return s


@module_required("placement", "register")
def placement_profile(request):
    student = _student(request)
    if not student:
        return redirect("cms:dashboard")
    profile, _ = m.PlacementProfile.objects.get_or_create(student=student)
    form = PlacementProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request, "placement.profile_update", profile)
        messages.success(request, "Placement profile saved.")
        return redirect("cms:placement_profile")
    return render(request, "portal/placement/profile.html", {"form": form, "student": student, "profile": profile,
                                                            "cgpa": student.cgpa(), "backlogs": len(student.backlogs()),
                                                            "attendance": student.attendance_percentage()})


@module_required("placement", FULL, "view", "register", "jobs")
def jobs(request):
    lvl = level(request.user, "placement")
    qs = m.JobPosting.objects.select_related("company").annotate(n=Count("applications"))
    if lvl == "jobs":
        qs = qs.filter(company__recruiters=request.user)
    elif lvl == "register":
        qs = qs.filter(is_open=True, company__is_approved=True)
    rows = []
    student = getattr(request.user, "student", None) if lvl == "register" else None
    applied = set(student.job_applications.values_list("job_id", flat=True)) if student else set()
    for j in qs:
        elig = j.eligibility_for(student) if student else (None, [])
        rows.append({"j": j, "eligible": elig[0], "reasons": elig[1], "applied": j.pk in applied})
    return render(request, "portal/placement/jobs.html", {"rows": rows, "lvl": lvl, "can_post": lvl in (FULL, "jobs"), "today": timezone.localdate()})


@module_required("placement", FULL, "jobs")
def job_form(request, pk=None):
    job = get_object_or_404(m.JobPosting, pk=pk) if pk else None
    if job and level(request.user, "placement") == "jobs" and not job.company.recruiters.filter(pk=request.user.pk).exists():
        raise PermissionDenied
    form = JobForm(request.user, request.POST or None, instance=job)
    if request.method == "POST" and form.is_valid():
        created = job is None
        job = form.save(commit=False)
        job.posted_by = job.posted_by or request.user
        job.save()
        form.save_m2m()
        audit(request, "placement.job_" + ("create" if created else "update"), job)
        if created and job.company.is_approved:
            from django.contrib.auth import get_user_model
            regd = get_user_model().objects.filter(student__placement_profile__is_registered=True)
            notify(regd, "New placement opportunity", f"{job.company.name} is hiring: {job.title} ({job.package_lpa} LPA). Apply by {job.deadline:%d %b}.",
                   reverse("cms:jobs"))
        messages.success(request, "Job posting saved.")
        return redirect("cms:job_detail", job.pk)
    return render(request, "portal/placement/job_form.html", {"form": form, "job": job})


@module_required("placement", FULL, "view", "register", "jobs")
def job_detail(request, pk):
    job = get_object_or_404(m.JobPosting.objects.select_related("company"), pk=pk)
    lvl = level(request.user, "placement")
    if lvl == "jobs" and not job.company.recruiters.filter(pk=request.user.pk).exists():
        raise PermissionDenied
    ctx = {"job": job, "lvl": lvl, "drives": job.drives.all()}
    if lvl == "register":
        student = _student(request)
        if not student:
            return redirect("cms:dashboard")
        eligible, reasons = job.eligibility_for(student)
        app = job.applications.filter(student=student).first()
        if request.method == "POST" and "apply" in request.POST:
            profile = getattr(student, "placement_profile", None)
            if not profile or not profile.is_registered:
                messages.error(request, "Register for placements in your Placement Profile first.")
            elif not eligible:
                messages.error(request, "You are not eligible: " + "; ".join(reasons))
            elif app:
                messages.info(request, "You have already applied.")
            elif not job.is_open or job.deadline < timezone.localdate():
                messages.error(request, "Applications are closed.")
            else:
                app = m.PlacementApplication.objects.create(job=job, student=student)
                audit(request, "placement.apply", app)
                notify(job.company.recruiters.all(), "New applicant", f"{student.user.display_name} applied for {job.title}.",
                       reverse("cms:job_detail", args=[job.pk]))
                messages.success(request, "Application submitted.")
            return redirect("cms:job_detail", pk)
        ctx.update({"eligible": eligible, "reasons": reasons, "app": app})
    else:
        stage = request.GET.get("stage", "")
        apps = job.applications.select_related("student__user", "student__course")
        if stage:
            apps = apps.filter(stage=stage)
        ctx.update({"apps": apps, "stage": stage, "stages": m.PlacementApplication.Stage.choices,
                    "funnel": dict(job.applications.values_list("stage").annotate(c=Count("id"))),
                    "can_manage": lvl in (FULL, "jobs")})
    return render(request, "portal/placement/job_detail.html", ctx)


@module_required("placement", FULL, "jobs")
def application_stage(request, pk):
    app = get_object_or_404(m.PlacementApplication.objects.select_related("job__company", "student__user"), pk=pk)
    if level(request.user, "placement") == "jobs" and not app.job.company.recruiters.filter(pk=request.user.pk).exists():
        raise PermissionDenied
    form = StageForm(request.POST or None, request.FILES or None, instance=app)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request, "placement.stage", app, app.stage)
        msg = f"{app.job.company.name} – {app.job.title}: you are now '{app.get_stage_display()}'."
        if app.interview_at:
            msg += f" Interview: {timezone.localtime(app.interview_at):%d %b %Y %H:%M}."
        notify(app.student.user, "Placement update", msg, reverse("cms:my_job_applications"),
               "success" if app.stage == "selected" else "info", email=True)
        messages.success(request, "Candidate updated.")
        return redirect("cms:job_detail", app.job_id)
    return render(request, "portal/placement/stage_form.html", {"form": form, "app": app})


@module_required("placement", "register")
def my_job_applications(request):
    student = _student(request)
    if not student:
        return redirect("cms:dashboard")
    return render(request, "portal/placement/my_applications.html", {"apps": student.job_applications.select_related("job__company")})


@module_required("placement", FULL, "view")
def placement_stats(request):
    selected = m.PlacementApplication.objects.filter(stage="selected")
    registered = m.PlacementProfile.objects.filter(is_registered=True).count()
    placed = selected.values("student").distinct().count()
    by_company = list(selected.values("job__company__name").annotate(n=Count("id"), top=Max("offered_package")).order_by("-n")[:10])
    by_course = []
    for c in m.Course.objects.all():
        reg = m.PlacementProfile.objects.filter(is_registered=True, student__course=c).count()
        pl = selected.filter(student__course=c).values("student").distinct().count()
        if reg:
            by_course.append({"c": c, "reg": reg, "placed": pl, "pct": round(pl * 100 / reg, 1)})
    pkg = selected.aggregate(avg=Avg("offered_package"), mx=Max("offered_package"))
    return render(request, "portal/placement/stats.html", {
        "registered": registered, "placed": placed, "pct": round(placed * 100 / registered, 1) if registered else 0,
        "companies": m.Company.objects.filter(is_approved=True).count(), "jobs": m.JobPosting.objects.count(),
        "avg_pkg": pkg["avg"], "max_pkg": pkg["mx"], "by_company": by_company, "by_course": by_course,
        "chart": json.dumps({"companies": {"labels": [r["job__company__name"] for r in by_company], "data": [r["n"] for r in by_company]},
                             "courses": {"labels": [r["c"].code for r in by_course], "data": [r["pct"] for r in by_course]}}),
    })
