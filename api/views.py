"""
REST API (Django REST Framework + JWT) for the web and future React Native mobile app.

Every endpoint enforces the same RBAC matrix as the portal (cms.permissions).
"""
from django.utils import timezone
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from accounts.models import Role
from accounts.utils import audit
from cms import models as m
from cms.helpers import students_for
from cms.permissions import FULL, can, level
from website.models import Event, Notice

from . import serializers as s


class ModuleAccess(permissions.BasePermission):
    """Read needs any access to the view's module; write needs one of `write_levels`."""

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False
        module = getattr(view, "module", None)
        if module is None:
            return True
        if request.method in permissions.SAFE_METHODS:
            return can(user, module)
        return can(user, module, *getattr(view, "write_levels", (FULL,)))


class Base(viewsets.ModelViewSet):
    permission_classes = [ModuleAccess]
    write_levels = (FULL,)

    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, f"api.{self.basename}.create", obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, f"api.{self.basename}.update", obj)

    def perform_destroy(self, instance):
        audit(self.request, f"api.{self.basename}.delete", instance)
        instance.delete()


class DepartmentViewSet(Base):
    module = "masters"
    queryset = m.Department.objects.all()
    serializer_class = s.DepartmentSerializer
    search_fields = ["name", "code"]


class CourseViewSet(Base):
    module = None  # public catalogue for any signed-in user; writes restricted below
    queryset = m.Course.objects.select_related("department")
    serializer_class = s.CourseSerializer
    filterset_fields = ["department", "level", "is_active"]
    search_fields = ["name", "code"]

    def get_permissions(self):
        if self.request.method not in permissions.SAFE_METHODS:
            self.module = "masters"
        return super().get_permissions()


class SubjectViewSet(Base):
    module = "masters"
    queryset = m.Subject.objects.all()
    serializer_class = s.SubjectSerializer
    filterset_fields = ["course", "semester", "faculty"]

    def get_permissions(self):
        self.module = None if self.request.method in permissions.SAFE_METHODS else "masters"
        return super().get_permissions()


class StudentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.StudentSerializer
    filterset_fields = ["course", "batch", "is_active"]
    search_fields = ["roll_no", "user__first_name", "user__last_name"]

    def get_queryset(self):
        u = self.request.user
        qs = m.Student.objects.select_related("user", "course", "batch")
        if u.role in (Role.STUDENT, Role.PARENT):
            return students_for(u).select_related("user", "course", "batch")
        if u.role == Role.HOD:
            return qs.filter(course__department_id=u.department_id)
        if any(can(u, mod, FULL, "approve", "view", "mark") for mod in ("admission", "attendance", "fees", "exams")):
            return qs
        return qs.none()


class ApplicationViewSet(Base):
    module = "admission"
    write_levels = (FULL, "apply")
    serializer_class = s.ApplicationSerializer
    filterset_fields = ["status", "course"]

    def get_queryset(self):
        u = self.request.user
        if level(u, "admission") == "apply":
            return m.Application.objects.filter(applicant=u)
        return m.Application.objects.all()

    def perform_create(self, serializer):
        from cms.forms import current_academic_year
        obj = serializer.save(applicant=self.request.user, academic_year=current_academic_year())
        audit(self.request, "api.admission.apply", obj)

    def update(self, request, *args, **kwargs):
        if level(request.user, "admission") == "apply":
            return Response({"detail": "Submitted applications cannot be edited."}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)


class AttendanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.AttendanceRecordSerializer
    filterset_fields = ["student", "status"]

    def get_queryset(self):
        u = self.request.user
        qs = m.AttendanceRecord.objects.select_related("session__subject")
        if u.role in (Role.STUDENT, Role.PARENT):
            return qs.filter(student__in=students_for(u))
        lvl = level(u, "attendance")
        if lvl in (FULL, "view"):
            return qs
        if lvl == "dept":
            return qs.filter(session__subject__course__department_id=u.department_id)
        if lvl == "mark":
            return qs.filter(session__subject__faculty=u)
        return qs.none()


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.InvoiceSerializer
    filterset_fields = ["student", "semester"]

    def get_queryset(self):
        u = self.request.user
        qs = m.Invoice.objects.all()
        if level(u, "fees") == "pay":
            return qs.filter(student__in=students_for(u))
        return qs if can(u, "fees", FULL, "view") else qs.none()


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.PaymentSerializer

    def get_queryset(self):
        u = self.request.user
        qs = m.Payment.objects.filter(status="success")
        if level(u, "fees") == "pay":
            return qs.filter(invoice__student__in=students_for(u))
        return qs if can(u, "fees", FULL, "view") else qs.none()


class ExamViewSet(Base):
    module = "exams"
    queryset = m.Exam.objects.all()
    serializer_class = s.ExamSerializer
    filterset_fields = ["course", "semester", "exam_type", "is_published"]


class MarkViewSet(viewsets.ModelViewSet):
    serializer_class = s.MarkSerializer
    filterset_fields = ["exam", "subject", "student"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        u = self.request.user
        qs = m.Mark.objects.select_related("subject", "exam")
        lvl = level(u, "exams")
        if lvl in ("own", "ward"):
            return qs.filter(student__in=students_for(u), exam__is_published=True)
        if lvl == "marks":
            return qs.filter(subject__faculty=u)
        if lvl == "dept":
            return qs.filter(subject__course__department_id=u.department_id)
        return qs if lvl in (FULL, "view") else qs.none()

    def _check_write(self, data):
        u = self.request.user
        lvl = level(u, "exams")
        exam, subject = data.get("exam"), data.get("subject")
        if lvl not in (FULL, "marks") or (lvl == "marks" and subject.faculty_id != u.id):
            raise serializers.ValidationError("You cannot enter marks for this subject.")
        if exam.marks_locked:
            raise serializers.ValidationError("Marks are locked for this exam.")
        if data.get("marks_obtained", 0) > exam.max_marks:
            raise serializers.ValidationError(f"Marks cannot exceed {exam.max_marks}.")

    def perform_create(self, serializer):
        self._check_write(serializer.validated_data)
        obj = serializer.save(entered_by=self.request.user)
        audit(self.request, "api.marks.create", obj)

    def perform_update(self, serializer):
        data = {"exam": serializer.instance.exam, "subject": serializer.instance.subject, **serializer.validated_data}
        self._check_write(data)
        old = serializer.instance.marks_obtained
        obj = serializer.save(entered_by=self.request.user)
        audit(self.request, "api.marks.change", obj, f"{old} -> {obj.marks_obtained}")


class CompanyViewSet(Base):
    module = "placement"
    queryset = m.Company.objects.filter(is_approved=True)
    serializer_class = s.CompanySerializer


class JobViewSet(Base):
    module = "placement"
    write_levels = (FULL, "jobs")
    serializer_class = s.JobSerializer
    filterset_fields = ["company", "is_open"]

    def get_queryset(self):
        u = self.request.user
        qs = m.JobPosting.objects.select_related("company")
        if level(u, "placement") == "jobs":
            return qs.filter(company__recruiters=u)
        if level(u, "placement") == "register":
            return qs.filter(is_open=True, company__is_approved=True, deadline__gte=timezone.localdate())
        return qs

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        job = self.get_object()
        student = getattr(request.user, "student", None)
        if student is None:
            return Response({"detail": "Only enrolled students can apply."}, status=403)
        profile = getattr(student, "placement_profile", None)
        if not profile or not profile.is_registered:
            return Response({"detail": "Register for placements first."}, status=400)
        ok, reasons = job.eligibility_for(student)
        if not ok:
            return Response({"detail": "Not eligible", "reasons": reasons}, status=400)
        app, created = m.PlacementApplication.objects.get_or_create(job=job, student=student)
        audit(request, "api.placement.apply", app)
        return Response(s.PlacementApplicationSerializer(app).data, status=201 if created else 200)


class LeaveViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = s.LeaveSerializer

    def get_queryset(self):
        u = self.request.user
        lvl = level(u, "faculty")
        qs = m.LeaveRequest.objects.all()
        if lvl in (FULL, "approve"):
            return qs
        if lvl == "dept":
            return qs.filter(faculty__department_id=u.department_id)
        return qs.filter(faculty__user=u)

    def perform_create(self, serializer):
        prof = getattr(self.request.user, "faculty_profile", None)
        if prof is None:
            raise serializers.ValidationError("Only faculty can apply for leave.")
        obj = serializer.save(faculty=prof)
        audit(self.request, "api.leave.apply", obj)


class TimetableViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.TimetableSerializer
    filterset_fields = ["batch", "faculty", "day"]

    def get_queryset(self):
        u = self.request.user
        qs = m.TimetableSlot.objects.select_related("subject")
        if u.role in (Role.STUDENT, Role.PARENT):
            return qs.filter(batch__in=students_for(u).values("batch"))
        if u.role == Role.FACULTY:
            return qs.filter(faculty=u)
        return qs


class NotificationViewSet(mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = s.NotificationSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        return self.request.user.notifications.all()

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        n = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"marked": n})


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Event.objects.filter(is_published=True)
    serializer_class = s.EventSerializer


class NoticeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    queryset = Notice.objects.filter(is_published=True)
    serializer_class = s.NoticeSerializer


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def me(request):
    if request.method == "PATCH":
        ser = s.UserSerializer(request.user, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)
    data = s.UserSerializer(request.user).data
    data["modules"] = {mod: level(request.user, mod) for mod in
                       ["admission", "faculty", "attendance", "fees", "exams", "placement", "reports", "masters", "users", "website", "audit"]}
    data["students"] = s.StudentSerializer(students_for(request.user), many=True).data
    return Response(data)
