"""
Role-Based Access Control (section 4 of the requirements document).

ACCESS[role][module] -> access level. Missing module = no access.
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from accounts.models import Role

FULL = "full"

MODULES = ["admission", "faculty", "attendance", "fees", "exams", "placement", "reports", "masters", "users", "website", "audit"]

ACCESS = {
    Role.SUPERADMIN: {m: FULL for m in MODULES},
    Role.PRINCIPAL: {
        "admission": "approve", "faculty": "approve", "attendance": "view", "fees": "view",
        "exams": "view", "placement": "view", "reports": FULL, "masters": "view", "website": FULL, "audit": "view",
    },
    Role.HOD: {
        "admission": "view", "faculty": "dept", "attendance": "dept", "exams": "dept",
        "placement": "view", "reports": "dept", "masters": "dept",
    },
    Role.ADMISSION: {"admission": FULL, "reports": "admission"},
    Role.FACULTY: {"faculty": "own", "attendance": "mark", "exams": "marks"},
    Role.ACCOUNTANT: {"fees": FULL, "reports": "fees", "faculty": "payroll"},
    Role.EXAM: {"exams": FULL, "reports": "exams"},
    Role.PLACEMENT: {"placement": FULL, "reports": "placement"},
    Role.STUDENT: {"admission": "apply", "attendance": "own", "fees": "pay", "exams": "own", "placement": "register"},
    Role.PARENT: {"attendance": "ward", "fees": "pay", "exams": "ward"},
    Role.RECRUITER: {"placement": "jobs"},
}


def level(user, module):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return FULL
    return ACCESS.get(user.role, {}).get(module)


def can(user, module, *levels):
    """True if the user can access `module` at one of `levels` (any level when none given). FULL always passes."""
    lvl = level(user, module)
    if lvl is None:
        return False
    return not levels or lvl == FULL or lvl in levels


def module_required(module, *levels):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not can(request.user, module, *levels):
                raise PermissionDenied("You do not have access to this section.")
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not request.user.has_role(*roles):
                raise PermissionDenied("You do not have access to this section.")
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


# Sidebar menu: (group, label, icon, url, module, levels)
MENU = [
    ("Main", "Dashboard", "fa-gauge-high", "cms:dashboard", None, ()),
    ("Main", "Notifications", "fa-bell", "cms:notifications", None, ()),

    ("Admission", "My Application", "fa-file-signature", "cms:my_applications", "admission", ("apply",)),
    ("Admission", "Applications", "fa-file-lines", "cms:applications", "admission", (FULL, "approve", "view")),
    ("Admission", "Students", "fa-user-graduate", "cms:students", "admission", (FULL, "approve", "view")),
    ("Admission", "Batches", "fa-layer-group", "cms:resource_list:batch", "admission", (FULL,)),

    ("Faculty", "My Profile", "fa-id-badge", "cms:my_faculty", "faculty", ("own", "dept")),
    ("Faculty", "Faculty", "fa-chalkboard-user", "cms:resource_list:faculty", "faculty", (FULL, "approve", "dept")),
    ("Faculty", "Leave", "fa-plane-departure", "cms:leaves", "faculty", (FULL, "approve", "dept", "own")),
    ("Faculty", "Faculty Attendance", "fa-user-check", "cms:faculty_attendance", "faculty", (FULL, "dept")),
    ("Faculty", "Timetable", "fa-calendar-week", "cms:timetable", "faculty", (FULL, "approve", "dept", "own")),
    ("Faculty", "Workload", "fa-scale-balanced", "cms:workload", "faculty", (FULL, "approve", "dept")),
    ("Faculty", "Performance", "fa-star-half-stroke", "cms:resource_list:review", "faculty", (FULL, "approve", "dept")),
    ("Faculty", "Payroll", "fa-money-check-dollar", "cms:payroll", "faculty", (FULL, "payroll", "approve", "own")),

    ("Attendance", "Take Attendance", "fa-clipboard-check", "cms:take_attendance", "attendance", (FULL, "mark", "dept")),
    ("Attendance", "My Attendance", "fa-calendar-check", "cms:my_attendance", "attendance", ("own", "ward")),
    ("Attendance", "Class Timetable", "fa-calendar-week", "cms:class_timetable", "attendance", ("own", "ward")),
    ("Attendance", "Attendance Reports", "fa-chart-column", "cms:attendance_report", "attendance", (FULL, "view", "dept", "mark")),

    ("Fees", "My Fees", "fa-wallet", "cms:my_fees", "fees", ("pay",)),
    ("Fees", "Invoices", "fa-file-invoice-dollar", "cms:invoices", "fees", (FULL, "view")),
    ("Fees", "Fee Structures", "fa-sitemap", "cms:resource_list:feestructure", "fees", (FULL, "view")),
    ("Fees", "Scholarships", "fa-hand-holding-heart", "cms:resource_list:scholarship", "fees", (FULL,)),
    ("Fees", "Payments", "fa-receipt", "cms:payments", "fees", (FULL, "view")),
    ("Fees", "Refunds", "fa-rotate-left", "cms:refunds", "fees", (FULL,)),
    ("Fees", "Defaulters & Summary", "fa-triangle-exclamation", "cms:fee_reports", "fees", (FULL, "view")),

    ("Examination", "My Results", "fa-award", "cms:my_results", "exams", ("own", "ward")),
    ("Examination", "Exams", "fa-file-pen", "cms:resource_list:exam", "exams", (FULL, "view", "dept")),
    ("Examination", "Exam Schedule", "fa-calendar-days", "cms:exam_schedule", "exams", (FULL, "view", "dept", "own", "ward")),
    ("Examination", "Marks Entry", "fa-pen-to-square", "cms:marks_entry", "exams", (FULL, "marks")),
    ("Examination", "Results & Publish", "fa-bullhorn", "cms:results_admin", "exams", (FULL, "view", "dept")),
    ("Examination", "Revaluation", "fa-magnifying-glass-chart", "cms:revaluations", "exams", (FULL, "own")),

    ("Placement", "Placement Profile", "fa-id-card", "cms:placement_profile", "placement", ("register",)),
    ("Placement", "Job Board", "fa-briefcase", "cms:jobs", "placement", (FULL, "view", "register", "jobs")),
    ("Placement", "My Applications", "fa-list-check", "cms:my_job_applications", "placement", ("register",)),
    ("Placement", "Companies", "fa-building", "cms:resource_list:company", "placement", (FULL, "view", "jobs")),
    ("Placement", "Drives", "fa-bus", "cms:resource_list:drive", "placement", (FULL, "view", "jobs")),
    ("Placement", "Statistics", "fa-chart-pie", "cms:placement_stats", "placement", (FULL, "view")),

    ("Administration", "Users", "fa-users-gear", "cms:resource_list:user", "users", (FULL,)),
    ("Administration", "Departments", "fa-building-columns", "cms:resource_list:department", "masters", (FULL, "view")),
    ("Administration", "Courses", "fa-graduation-cap", "cms:resource_list:course", "masters", (FULL, "view", "dept")),
    ("Administration", "Subjects", "fa-book", "cms:resource_list:subject", "masters", (FULL, "view", "dept")),
    ("Administration", "Events", "fa-calendar-star", "cms:resource_list:event", "website", (FULL,)),
    ("Administration", "Notices & News", "fa-newspaper", "cms:resource_list:notice", "website", (FULL,)),
    ("Administration", "FAQs", "fa-circle-question", "cms:resource_list:faq", "website", (FULL,)),
    ("Administration", "Enquiries", "fa-envelope-open-text", "cms:resource_list:contact", "website", (FULL,)),
    ("Administration", "Audit Log", "fa-shield-halved", "cms:audit_log", "audit", (FULL, "view")),
]


PERSONAL_LEVELS = {"apply", "own", "ward", "pay", "register"}


def menu_for(user, current_path=""):
    from django.urls import reverse

    groups = {}
    for group, label, icon, url, module, levels in MENU:
        # "My ..." pages are for the person's own records: hide them from full-access administrators
        if module and levels and set(levels) <= PERSONAL_LEVELS and level(user, module) == FULL:
            continue
        if url == "cms:my_faculty" and not hasattr(user, "faculty_profile"):
            continue
        if module is None or can(user, module, *levels):
            if url.startswith("cms:resource_list:"):
                href = reverse("cms:resource_list", args=[url.rsplit(":", 1)[1]])
            else:
                href = reverse(url)
            is_active = current_path == href or (href != reverse("cms:dashboard") and current_path.startswith(href))
            groups.setdefault(group, []).append({"label": label, "icon": icon, "href": href, "active": is_active})
    return list(groups.items())
