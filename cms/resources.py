"""
Declarative CRUD resources for master data and simple records.

Every resource is rendered by the generic list / form / delete views in views/crud.py
and is protected by the RBAC matrix in permissions.py.
"""
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from accounts.models import Role
from website.models import FAQ, ContactMessage, Event, Notice

from . import models as m
from .permissions import FULL, level

User = get_user_model()


def html5_widgets(field, **kwargs):
    """Use native date / time pickers in auto-generated forms."""
    from django.db import models as dj

    if isinstance(field, dj.DateTimeField):
        kwargs["widget"] = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
    elif isinstance(field, dj.DateField):
        kwargs["widget"] = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    elif isinstance(field, dj.TimeField):
        kwargs["widget"] = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
    return field.formfield(**kwargs)


class UserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=False), required=False,
        help_text="Required for new users. Leave blank to keep the current password.", min_length=8,
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "phone", "role", "department", "is_active", "password"]

    def clean(self):
        data = super().clean()
        if not self.instance.pk and not data.get("password"):
            self.add_error("password", "Password is required for a new user.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class FacultyForm(forms.ModelForm):
    class Meta:
        model = m.FacultyProfile
        fields = ["user", "employee_id", "department", "designation", "qualification", "specialization",
                  "experience_years", "date_of_joining", "basic_salary", "photo", "bio", "is_public"]
        widgets = {"date_of_joining": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = User.objects.filter(role__in=[Role.FACULTY, Role.HOD, Role.PRINCIPAL])


def dept_of(user):
    return user.department_id


class Resource:
    slug = ""
    model = None
    title = ""
    icon = "fa-table"
    fields = "__all__"
    form_class = None
    columns = []           # [(label, attr or callable)]
    search = []
    filters = []           # model field names offered as dropdown filters
    module = "masters"
    view_levels = (FULL,)
    edit_levels = (FULL,)
    order = None

    def queryset(self, user):
        qs = self.model.objects.all()
        if self.order:
            qs = qs.order_by(*self.order)
        return self.scope(qs, user)

    def scope(self, qs, user):
        return qs

    def can_view(self, user):
        lvl = level(user, self.module)
        return lvl is not None and (lvl == FULL or lvl in self.view_levels)

    def can_edit(self, user):
        lvl = level(user, self.module)
        return lvl is not None and (lvl == FULL or lvl in self.edit_levels)

    def get_form_class(self, user):
        if self.form_class:
            return self.form_class
        return forms.modelform_factory(self.model, fields=self.fields, formfield_callback=html5_widgets)

    def before_save(self, obj, user, created):
        pass


class DepartmentRes(Resource):
    slug, model, title, icon = "department", m.Department, "Departments", "fa-building-columns"
    fields = ["name", "code", "hod", "description", "image"]
    columns = [("Code", "code"), ("Name", "name"), ("HOD", "hod"), ("Courses", lambda o: o.courses.count()), ("Faculty", lambda o: o.faculty.count())]
    search = ["name", "code"]
    view_levels = ("view",)


class CourseRes(Resource):
    slug, model, title, icon = "course", m.Course, "Courses / Programs", "fa-graduation-cap"
    fields = ["name", "code", "department", "level", "duration_years", "total_semesters", "seats", "eligibility",
              "short_description", "description", "image", "is_active"]
    columns = [("Code", "code"), ("Program", "name"), ("Department", "department"), ("Level", "get_level_display"),
               ("Seats", "seats"), ("Students", lambda o: o.students.count()), ("Active", "is_active")]
    search = ["name", "code"]
    filters = ["department", "level"]
    view_levels = ("view", "dept")

    def scope(self, qs, user):
        if level(user, "masters") == "dept":
            return qs.filter(department_id=dept_of(user))
        return qs


class BatchRes(Resource):
    slug, model, title, icon = "batch", m.Batch, "Batches & Academic Years", "fa-layer-group"
    module = "admission"
    fields = ["course", "academic_year", "start_year", "section", "current_semester"]
    columns = [("Batch", str), ("Course", "course"), ("Academic Year", "academic_year"), ("Semester", "current_semester"),
               ("Students", lambda o: o.students.count())]
    search = ["course__name", "course__code", "academic_year"]
    filters = ["course"]
    view_levels = ("approve", "view")


class SubjectRes(Resource):
    slug, model, title, icon = "subject", m.Subject, "Subjects & Allocation", "fa-book"
    fields = ["course", "semester", "code", "name", "credits", "hours_per_week", "faculty"]
    columns = [("Code", "code"), ("Subject", "name"), ("Course", "course"), ("Sem", "semester"), ("Credits", "credits"), ("Faculty", "faculty")]
    search = ["code", "name"]
    filters = ["course", "semester"]
    view_levels = ("view", "dept")
    edit_levels = ("dept",)

    def scope(self, qs, user):
        if level(user, "masters") == "dept":
            return qs.filter(course__department_id=dept_of(user))
        return qs


class UserRes(Resource):
    slug, model, title, icon = "user", User, "Users & Roles", "fa-users-gear"
    module = "users"
    form_class = UserForm
    columns = [("Username", "username"), ("Name", "display_name"), ("Email", "email"), ("Role", "get_role_display"),
               ("Department", "department"), ("Active", "is_active"), ("Last login", "last_login")]
    search = ["username", "first_name", "last_name", "email"]
    filters = ["role", "is_active"]


class FacultyRes(Resource):
    slug, model, title, icon = "faculty", m.FacultyProfile, "Faculty Records", "fa-chalkboard-user"
    module = "faculty"
    form_class = FacultyForm
    columns = [("Emp ID", "employee_id"), ("Name", lambda o: o.user.display_name), ("Department", "department"),
               ("Designation", "designation"), ("Experience", lambda o: f"{o.experience_years} yrs"),
               ("Weekly Hrs", "weekly_hours")]
    search = ["employee_id", "user__first_name", "user__last_name", "designation"]
    filters = ["department"]
    view_levels = ("approve", "dept")
    edit_levels = ("dept",)

    def scope(self, qs, user):
        if level(user, "faculty") == "dept":
            return qs.filter(department_id=dept_of(user))
        return qs.select_related("user", "department")


class ReviewRes(Resource):
    slug, model, title, icon = "review", m.PerformanceReview, "Performance Evaluation", "fa-star-half-stroke"
    module = "faculty"
    fields = ["faculty", "period", "teaching", "research", "student_feedback", "administration", "comments"]
    columns = [("Faculty", "faculty"), ("Period", "period"), ("Teaching", "teaching"), ("Research", "research"),
               ("Feedback", "student_feedback"), ("Admin", "administration"), ("Overall /10", "overall")]
    view_levels = ("approve", "dept")
    edit_levels = ("approve", "dept")

    def scope(self, qs, user):
        if level(user, "faculty") == "dept":
            return qs.filter(faculty__department_id=dept_of(user))
        return qs

    def before_save(self, obj, user, created):
        obj.reviewer = user
        obj.save(update_fields=["reviewer"])


class FeeStructureRes(Resource):
    slug, model, title, icon = "feestructure", m.FeeStructure, "Fee Structures", "fa-sitemap"
    module = "fees"
    fields = ["course", "academic_year", "semester", "category", "tuition_fee", "exam_fee", "development_fee", "other_fee", "due_date"]
    columns = [("Course", "course"), ("Year", "academic_year"), ("Sem", "semester"), ("Category", "category"),
               ("Tuition", "tuition_fee"), ("Exam", "exam_fee"), ("Total", "total"), ("Due", "due_date")]
    filters = ["course", "semester", "category"]
    view_levels = ("view",)


class ScholarshipRes(Resource):
    slug, model, title, icon = "scholarship", m.Scholarship, "Scholarships & Concessions", "fa-hand-holding-heart"
    module = "fees"
    fields = ["name", "kind", "value", "description"]
    columns = [("Name", "name"), ("Type", "get_kind_display"), ("Value", "value"), ("Description", "description")]


class ExamRes(Resource):
    slug, model, title, icon = "exam", m.Exam, "Examinations", "fa-file-pen"
    module = "exams"
    fields = ["name", "exam_type", "course", "semester", "academic_year", "max_marks", "pass_marks", "start_date",
              "end_date", "min_attendance", "require_fee_clearance", "marks_locked"]
    columns = [("Exam", "name"), ("Type", "get_exam_type_display"), ("Course", "course"), ("Sem", "semester"),
               ("Dates", lambda o: f"{o.start_date:%d %b} – {o.end_date:%d %b %Y}"), ("Locked", "marks_locked"), ("Published", "is_published")]
    filters = ["course", "exam_type", "is_published"]
    view_levels = ("view", "dept")

    def scope(self, qs, user):
        if level(user, "exams") == "dept":
            return qs.filter(course__department_id=dept_of(user))
        return qs


class ScheduleRes(Resource):
    slug, model, title, icon = "schedule", m.ExamSchedule, "Exam Timetable", "fa-calendar-days"
    module = "exams"
    fields = ["exam", "subject", "date", "start_time", "end_time", "venue"]
    columns = [("Exam", "exam"), ("Subject", "subject"), ("Date", "date"), ("Time", lambda o: f"{o.start_time:%H:%M}-{o.end_time:%H:%M}"), ("Venue", "venue")]
    filters = ["exam"]
    view_levels = ("view", "dept")


class TimetableRes(Resource):
    slug, model, title, icon = "timetable", m.TimetableSlot, "Timetable Slots", "fa-calendar-week"
    module = "faculty"
    fields = ["batch", "subject", "faculty", "day", "period", "start_time", "end_time", "room"]
    columns = [("Batch", "batch"), ("Day", "get_day_display"), ("Period", "period"), ("Time", lambda o: f"{o.start_time:%H:%M}-{o.end_time:%H:%M}"),
               ("Subject", "subject"), ("Faculty", "faculty"), ("Room", "room")]
    filters = ["batch", "day"]
    view_levels = ("approve", "dept")
    edit_levels = ("dept",)

    def scope(self, qs, user):
        if level(user, "faculty") == "dept":
            return qs.filter(batch__course__department_id=dept_of(user))
        return qs


class CompanyRes(Resource):
    slug, model, title, icon = "company", m.Company, "Companies & Recruiters", "fa-building"
    module = "placement"
    fields = ["name", "industry", "website", "contact_person", "contact_email", "contact_phone", "logo", "recruiters", "is_approved"]
    columns = [("Company", "name"), ("Industry", "industry"), ("Contact", "contact_person"), ("Email", "contact_email"),
               ("Jobs", lambda o: o.jobs.count()), ("Approved", "is_approved")]
    search = ["name", "industry"]
    view_levels = ("view", "jobs")
    edit_levels = ("jobs",)

    def scope(self, qs, user):
        if level(user, "placement") == "jobs":
            return qs.filter(recruiters=user)
        return qs

    def get_form_class(self, user):
        if level(user, "placement") == "jobs":
            return forms.modelform_factory(self.model, fields=["name", "industry", "website", "contact_person", "contact_email", "contact_phone", "logo"], formfield_callback=html5_widgets)
        return super().get_form_class(user)

    def before_save(self, obj, user, created):
        if created and level(user, "placement") == "jobs":
            obj.is_approved = False
            obj.save()
            obj.recruiters.add(user)


class DriveRes(Resource):
    slug, model, title, icon = "drive", m.PlacementDrive, "Campus Drives", "fa-bus"
    module = "placement"
    fields = ["job", "date", "venue", "rounds", "assessment_link", "notes"]
    columns = [("Job", "job"), ("Date", "date"), ("Venue", "venue"), ("Rounds", "rounds")]
    view_levels = ("view", "jobs")
    edit_levels = ("jobs",)

    def scope(self, qs, user):
        if level(user, "placement") == "jobs":
            return qs.filter(job__company__recruiters=user)
        return qs


class EventRes(Resource):
    slug, model, title, icon = "event", Event, "Events", "fa-calendar-star"
    module = "website"
    fields = ["title", "summary", "body", "image", "venue", "date", "start_time", "end_time", "is_published"]
    columns = [("Title", "title"), ("Date", "date"), ("Venue", "venue"), ("Published", "is_published")]
    search = ["title"]


class NoticeRes(Resource):
    slug, model, title, icon = "notice", Notice, "Notices & News", "fa-newspaper"
    module = "website"
    fields = ["title", "category", "summary", "body", "image", "author", "published_on", "attachment", "is_published"]
    columns = [("Title", "title"), ("Category", "get_category_display"), ("Date", "published_on"), ("Published", "is_published")]
    search = ["title"]
    filters = ["category"]


class FAQRes(Resource):
    slug, model, title, icon = "faq", FAQ, "FAQs", "fa-circle-question"
    module = "website"
    fields = ["question", "answer", "order"]
    columns = [("#", "order"), ("Question", "question")]


class ContactRes(Resource):
    slug, model, title, icon = "contact", ContactMessage, "Website Enquiries", "fa-envelope-open-text"
    module = "website"
    fields = ["name", "email", "phone", "subject", "message", "is_resolved"]
    columns = [("Date", "created_at"), ("Name", "name"), ("Email", "email"), ("Phone", "phone"), ("Subject", "subject"), ("Resolved", "is_resolved")]
    search = ["name", "email", "subject"]
    filters = ["is_resolved"]


REGISTRY = {r.slug: r() for r in [
    DepartmentRes, CourseRes, BatchRes, SubjectRes, UserRes, FacultyRes, ReviewRes, FeeStructureRes,
    ScholarshipRes, ExamRes, ScheduleRes, TimetableRes, CompanyRes, DriveRes, EventRes, NoticeRes, FAQRes, ContactRes,
]}


def apply_search(qs, resource, term):
    if not term or not resource.search:
        return qs
    q = Q()
    for f in resource.search:
        q |= Q(**{f"{f}__icontains": term})
    return qs.filter(q)
