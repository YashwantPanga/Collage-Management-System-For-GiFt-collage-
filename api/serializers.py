from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.models import Notification
from cms import models as m
from website.models import Event, Notice

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone", "role", "role_display", "department"]
        read_only_fields = ["role", "department"]


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Department
        fields = ["id", "name", "code", "hod", "description"]


class CourseSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = m.Course
        fields = ["id", "name", "code", "slug", "department", "department_name", "level", "duration_years", "total_semesters",
                  "seats", "eligibility", "short_description", "is_active"]


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Subject
        fields = ["id", "course", "semester", "code", "name", "credits", "faculty", "hours_per_week"]


class StudentSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.display_name", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    course_code = serializers.CharField(source="course.code", read_only=True)
    batch_name = serializers.CharField(source="batch.__str__", read_only=True)
    attendance = serializers.SerializerMethodField()
    cgpa = serializers.SerializerMethodField()
    fee_due = serializers.SerializerMethodField()

    class Meta:
        model = m.Student
        fields = ["id", "roll_no", "name", "email", "course", "course_code", "batch", "batch_name", "category", "semester",
                  "attendance", "cgpa", "fee_due", "is_active"]

    def get_attendance(self, obj):
        return obj.attendance_percentage()

    def get_cgpa(self, obj):
        return obj.cgpa()

    def get_fee_due(self, obj):
        return obj.fee_due()


class ApplicationSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = m.Application
        fields = ["id", "application_no", "course", "academic_year", "full_name", "email", "phone", "date_of_birth", "gender",
                  "category", "guardian_name", "guardian_phone", "address", "previous_institution", "qualifying_exam",
                  "percentage", "entrance_rank", "status", "status_display", "remarks", "created_at"]
        read_only_fields = ["application_no", "academic_year", "status", "remarks"]


class AttendanceRecordSerializer(serializers.ModelSerializer):
    subject = serializers.CharField(source="session.subject.code", read_only=True)
    date = serializers.DateField(source="session.date", read_only=True)
    period = serializers.IntegerField(source="session.period", read_only=True)

    class Meta:
        model = m.AttendanceRecord
        fields = ["id", "student", "subject", "date", "period", "status", "method"]


class InvoiceSerializer(serializers.ModelSerializer):
    net = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    paid = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = m.Invoice
        fields = ["id", "invoice_no", "student", "semester", "tuition_fee", "exam_fee", "other_fee", "concession", "net", "paid",
                  "balance", "status", "due_date"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Payment
        fields = ["id", "invoice", "amount", "method", "status", "transaction_id", "receipt_no", "paid_at"]


class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Exam
        fields = ["id", "name", "exam_type", "course", "semester", "academic_year", "max_marks", "pass_marks", "start_date",
                  "end_date", "is_published"]


class MarkSerializer(serializers.ModelSerializer):
    subject_code = serializers.CharField(source="subject.code", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    credits = serializers.IntegerField(source="subject.credits", read_only=True)

    class Meta:
        model = m.Mark
        fields = ["id", "exam", "subject", "subject_code", "subject_name", "credits", "student", "marks_obtained", "is_absent",
                  "grade", "grade_point"]
        read_only_fields = ["grade", "grade_point"]


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Company
        fields = ["id", "name", "industry", "website", "is_approved"]


class JobSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = m.JobPosting
        fields = ["id", "company", "company_name", "title", "description", "location", "package_lpa", "vacancies", "min_cgpa",
                  "max_backlogs", "min_attendance", "deadline", "is_open"]


class PlacementApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.PlacementApplication
        fields = ["id", "job", "student", "stage", "interview_at", "offered_package", "remarks", "created_at"]
        read_only_fields = ["student", "stage", "interview_at", "offered_package", "remarks"]


class LeaveSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.LeaveRequest
        fields = ["id", "faculty", "leave_type", "from_date", "to_date", "reason", "status", "remarks", "created_at"]
        read_only_fields = ["faculty", "status", "remarks"]


class TimetableSerializer(serializers.ModelSerializer):
    subject_code = serializers.CharField(source="subject.code", read_only=True)
    day_name = serializers.CharField(source="get_day_display", read_only=True)

    class Meta:
        model = m.TimetableSlot
        fields = ["id", "batch", "subject", "subject_code", "faculty", "day", "day_name", "period", "start_time", "end_time", "room"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "title", "message", "link", "level", "is_read", "created_at"]


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ["id", "title", "slug", "summary", "venue", "date", "start_time", "end_time"]


class NoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notice
        fields = ["id", "title", "slug", "category", "summary", "published_on"]
