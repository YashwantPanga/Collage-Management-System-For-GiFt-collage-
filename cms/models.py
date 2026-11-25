"""
College Management System domain models.

Sections follow the requirements document:
  Masters (departments, courses, batches, subjects, timetable)
  3.1 Admission   3.2 Faculty   3.3 Attendance   3.4 Fees
  3.5 Examination 3.6 Placement
"""
import secrets
from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL
DOC_VALIDATOR = FileExtensionValidator(["pdf", "jpg", "jpeg", "png", "doc", "docx"])


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# --------------------------------------------------------------------------- masters
class Department(TimeStamped):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=12, unique=True)
    hod = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="headed_departments")
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="departments/", blank=True, null=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Course(TimeStamped):
    class Level(models.TextChoices):
        UG = "UG", "Undergraduate"
        PG = "PG", "Postgraduate"
        DIPLOMA = "DIP", "Diploma"
        PHD = "PHD", "Doctorate"

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="courses")
    level = models.CharField(max_length=4, choices=Level.choices, default=Level.UG)
    duration_years = models.PositiveSmallIntegerField(default=4)
    total_semesters = models.PositiveSmallIntegerField(default=8)
    seats = models.PositiveIntegerField(default=60)
    eligibility = models.CharField(max_length=255, blank=True)
    short_description = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    image = models.CharField(max_length=255, blank=True, help_text="Static path or URL of the cover image")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["level", "name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.code}-{self.name}")[:160]
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("website:program_detail", args=[self.slug])

    def __str__(self):
        return f"{self.name} ({self.code})"


class Batch(TimeStamped):
    """A cohort of students of a course (e.g. B.Tech CSE 2024-28, section A)."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="batches")
    academic_year = models.CharField(max_length=9, help_text="e.g. 2025-2026")
    start_year = models.PositiveIntegerField()
    section = models.CharField(max_length=5, default="A")
    current_semester = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["-start_year", "course__name", "section"]
        unique_together = ("course", "start_year", "section")
        verbose_name_plural = "batches"

    def __str__(self):
        end = self.start_year + self.course.duration_years
        return f"{self.course.code} {self.start_year}-{str(end)[-2:]} {self.section}"


class Subject(TimeStamped):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="subjects")
    semester = models.PositiveSmallIntegerField()
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    credits = models.PositiveSmallIntegerField(default=3)
    faculty = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="subjects",
        limit_choices_to={"role__in": ["faculty", "hod"]},
    )
    hours_per_week = models.PositiveSmallIntegerField(default=4)

    class Meta:
        ordering = ["course", "semester", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class TimetableSlot(TimeStamped):
    DAYS = [(i, d) for i, d in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"])]
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="timetable")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="slots")
    faculty = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="timetable_slots")
    day = models.PositiveSmallIntegerField(choices=DAYS)
    period = models.PositiveSmallIntegerField(default=1)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["day", "start_time"]

    def __str__(self):
        return f"{self.get_day_display()} P{self.period} {self.subject.code} ({self.batch})"


# --------------------------------------------------------------------------- 3.1 admission
class Student(TimeStamped):
    class Category(models.TextChoices):
        GENERAL = "GEN", "General"
        OBC = "OBC", "OBC"
        SC = "SC", "SC"
        ST = "ST", "ST"
        EWS = "EWS", "EWS"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student")
    roll_no = models.CharField(max_length=20, unique=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="students")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="students")
    category = models.CharField(max_length=5, choices=Category.choices, default=Category.GENERAL)
    parent = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="wards",
        limit_choices_to={"role": "parent"},
    )
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, blank=True)
    address = models.TextField(blank=True)
    admission_date = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["roll_no"]

    def save(self, *args, **kwargs):
        if not self.roll_no:
            prefix = f"{str(self.batch.start_year)[-2:]}{self.course.code[:4].upper()}"
            last = Student.objects.filter(roll_no__startswith=prefix).order_by("-roll_no").first()
            seq = int(last.roll_no[len(prefix):]) + 1 if last and last.roll_no[len(prefix):].isdigit() else 1
            self.roll_no = f"{prefix}{seq:04d}"
        super().save(*args, **kwargs)

    @property
    def semester(self):
        return self.batch.current_semester

    def attendance_percentage(self, subject=None):
        qs = self.attendance_records.all()
        if subject is not None:
            qs = qs.filter(session__subject=subject)
        total = qs.count()
        if not total:
            return None
        present = qs.filter(status__in=["P", "L"]).count()
        return round(present * 100 / total, 1)

    def cgpa(self):
        return compute_gpa(Mark.objects.filter(student=self, exam__is_published=True, exam__exam_type="SEM"))

    def backlogs(self):
        failed = Mark.objects.filter(student=self, exam__is_published=True, exam__exam_type="SEM", grade="F")
        cleared = set(
            Mark.objects.filter(student=self, exam__is_published=True, exam__exam_type__in=["SEM", "SUP"])
            .exclude(grade="F").values_list("subject_id", flat=True)
        )
        return [m for m in failed if m.subject_id not in cleared]

    def fee_due(self):
        return sum((inv.balance for inv in self.invoices.all()), Decimal("0"))

    def __str__(self):
        return f"{self.roll_no} - {self.user.display_name}"


class Application(TimeStamped):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "review", "Under Review"
        VERIFIED = "verified", "Documents Verified"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        ENROLLED = "enrolled", "Enrolled"

    application_no = models.CharField(max_length=20, unique=True, blank=True)
    applicant = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="applications")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="applications")
    academic_year = models.CharField(max_length=9)
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=[("Male", "Male"), ("Female", "Female"), ("Other", "Other")])
    category = models.CharField(max_length=5, choices=Student.Category.choices, default=Student.Category.GENERAL)
    guardian_name = models.CharField(max_length=150)
    guardian_phone = models.CharField(max_length=20)
    address = models.TextField()
    previous_institution = models.CharField(max_length=200)
    qualifying_exam = models.CharField(max_length=100, help_text="e.g. +2 Science / JEE Main / OJEE")
    percentage = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)])
    entrance_rank = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    remarks = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_applications")
    student = models.OneToOneField(Student, null=True, blank=True, on_delete=models.SET_NULL, related_name="application")

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.application_no:
            self.application_no = f"GIFT{timezone.now():%y}{self.pk:05d}"
            super().save(update_fields=["application_no"])

    def __str__(self):
        return f"{self.application_no} - {self.full_name}"


class ApplicationDocument(TimeStamped):
    DOC_TYPES = [
        ("photo", "Passport Photo"), ("10th", "10th Marksheet"), ("12th", "12th / Diploma Marksheet"),
        ("entrance", "Entrance Scorecard"), ("tc", "Transfer Certificate"), ("caste", "Caste Certificate"),
        ("id", "ID Proof (Aadhaar)"), ("other", "Other"),
    ]
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=10, choices=DOC_TYPES)
    file = models.FileField(upload_to="admission_docs/%Y/", validators=[DOC_VALIDATOR])
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.get_doc_type_display()} - {self.application}"


# --------------------------------------------------------------------------- 3.2 faculty
class FacultyProfile(TimeStamped):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="faculty_profile")
    employee_id = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="faculty")
    designation = models.CharField(max_length=80, default="Assistant Professor")
    qualification = models.CharField(max_length=200, blank=True)
    specialization = models.CharField(max_length=200, blank=True)
    experience_years = models.PositiveSmallIntegerField(default=0)
    date_of_joining = models.DateField(default=timezone.localdate)
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("50000"))
    bio = models.TextField(blank=True)
    photo = models.CharField(max_length=255, blank=True, help_text="Static path or URL of the photo")
    is_public = models.BooleanField(default=True, help_text="Show on the public website")

    class Meta:
        ordering = ["department", "user__first_name"]

    @property
    def weekly_hours(self):
        return self.user.timetable_slots.count()

    def __str__(self):
        return f"{self.user.display_name} - {self.designation}"


class FacultyAttendance(TimeStamped):
    STATUS = [("P", "Present"), ("A", "Absent"), ("L", "On Leave"), ("H", "Half Day")]
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=1, choices=STATUS, default="P")
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)

    class Meta:
        unique_together = ("faculty", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.faculty} {self.date} {self.status}"


class LeaveRequest(TimeStamped):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    LEAVE_TYPES = [("CL", "Casual Leave"), ("SL", "Sick Leave"), ("EL", "Earned Leave"), ("OD", "On Duty"), ("LOP", "Loss of Pay")]
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name="leaves")
    leave_type = models.CharField(max_length=3, choices=LEAVE_TYPES, default="CL")
    from_date = models.DateField()
    to_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_leaves")
    remarks = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def days(self):
        return (self.to_date - self.from_date).days + 1

    def __str__(self):
        return f"{self.faculty.user.display_name} {self.leave_type} {self.from_date}→{self.to_date}"


class PerformanceReview(TimeStamped):
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name="reviews")
    period = models.CharField(max_length=30, help_text="e.g. 2025-26 Odd Semester")
    teaching = models.PositiveSmallIntegerField(validators=[MaxValueValidator(10)])
    research = models.PositiveSmallIntegerField(validators=[MaxValueValidator(10)])
    student_feedback = models.PositiveSmallIntegerField(validators=[MaxValueValidator(10)])
    administration = models.PositiveSmallIntegerField(validators=[MaxValueValidator(10)])
    comments = models.TextField(blank=True)
    reviewer = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    @property
    def overall(self):
        return round((self.teaching + self.research + self.student_feedback + self.administration) / 4, 1)

    def __str__(self):
        return f"{self.faculty} {self.period}"


class Payroll(TimeStamped):
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.CASCADE, related_name="payrolls")
    month = models.DateField(help_text="First day of the month")
    working_days = models.PositiveSmallIntegerField(default=26)
    days_present = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    paid_leave_days = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    lop_days = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    basic = models.DecimalField(max_digits=10, decimal_places=2)
    allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)

    class Meta:
        unique_together = ("faculty", "month")
        ordering = ["-month"]

    def __str__(self):
        return f"{self.faculty.user.display_name} {self.month:%b %Y}"


# --------------------------------------------------------------------------- 3.3 attendance
class AttendanceSession(TimeStamped):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="sessions")
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="sessions")
    faculty = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="attendance_sessions")
    date = models.DateField(default=timezone.localdate)
    period = models.PositiveSmallIntegerField(default=1)
    qr_token = models.CharField(max_length=48, blank=True, db_index=True)
    qr_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("subject", "batch", "date", "period")
        ordering = ["-date", "-period"]

    def open_qr(self, minutes):
        self.qr_token = secrets.token_urlsafe(24)
        self.qr_expires_at = timezone.now() + timezone.timedelta(minutes=minutes)
        self.save(update_fields=["qr_token", "qr_expires_at"])

    @property
    def qr_active(self):
        return bool(self.qr_token and self.qr_expires_at and self.qr_expires_at > timezone.now())

    def __str__(self):
        return f"{self.subject.code} {self.batch} {self.date} P{self.period}"


class AttendanceRecord(models.Model):
    STATUS = [("P", "Present"), ("A", "Absent"), ("L", "Leave / OD")]
    METHOD = [("manual", "Manual"), ("qr", "QR Scan"), ("bio", "Biometric")]
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name="records")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_records")
    status = models.CharField(max_length=1, choices=STATUS, default="P")
    method = models.CharField(max_length=6, choices=METHOD, default="manual")
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("session", "student")

    def __str__(self):
        return f"{self.student.roll_no} {self.session} {self.status}"


# --------------------------------------------------------------------------- 3.4 fees
class FeeStructure(TimeStamped):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="fee_structures")
    academic_year = models.CharField(max_length=9)
    semester = models.PositiveSmallIntegerField()
    category = models.CharField(max_length=5, choices=Student.Category.choices, default=Student.Category.GENERAL)
    tuition_fee = models.DecimalField(max_digits=10, decimal_places=2)
    exam_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    development_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    due_date = models.DateField()

    class Meta:
        unique_together = ("course", "academic_year", "semester", "category")
        ordering = ["course", "semester"]

    @property
    def total(self):
        return self.tuition_fee + self.exam_fee + self.development_fee + self.other_fee

    def __str__(self):
        return f"{self.course.code} Sem {self.semester} {self.category} {self.academic_year}"


class Scholarship(TimeStamped):
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=[("percent", "Percentage"), ("flat", "Flat amount")], default="percent")
    value = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)

    def amount_for(self, total):
        if self.kind == "percent":
            return (total * self.value / Decimal("100")).quantize(Decimal("0.01"))
        return min(self.value, total)

    def __str__(self):
        return self.name


class Invoice(TimeStamped):
    invoice_no = models.CharField(max_length=20, unique=True, blank=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="invoices")
    fee_structure = models.ForeignKey(FeeStructure, null=True, blank=True, on_delete=models.SET_NULL)
    semester = models.PositiveSmallIntegerField()
    tuition_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    exam_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    scholarship = models.ForeignKey(Scholarship, null=True, blank=True, on_delete=models.SET_NULL)
    concession = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    due_date = models.DateField()

    class Meta:
        ordering = ["-due_date"]

    def save(self, *args, **kwargs):
        if self.scholarship_id and not self.concession:
            self.concession = self.scholarship.amount_for(self.gross)
        super().save(*args, **kwargs)
        if not self.invoice_no:
            self.invoice_no = f"INV{timezone.now():%y}{self.pk:06d}"
            super().save(update_fields=["invoice_no"])

    @property
    def gross(self):
        return self.tuition_fee + self.exam_fee + self.other_fee

    @property
    def net(self):
        return max(self.gross - self.concession, Decimal("0"))

    @property
    def paid(self):
        paid = self.payments.filter(status="success").aggregate(s=Sum("amount"))["s"] or Decimal("0")
        refunded = self.refunds.filter(status="processed").aggregate(s=Sum("amount"))["s"] or Decimal("0")
        return paid - refunded

    @property
    def balance(self):
        return max(self.net - self.paid, Decimal("0"))

    @property
    def status(self):
        if self.balance <= 0:
            return "Paid"
        if self.due_date < timezone.localdate():
            return "Overdue"
        return "Partially Paid" if self.paid > 0 else "Pending"

    def __str__(self):
        return f"{self.invoice_no} {self.student.roll_no} Sem {self.semester}"


class Payment(TimeStamped):
    METHODS = [("online", "Online (Gateway)"), ("cash", "Cash"), ("dd", "Demand Draft"), ("neft", "NEFT / Bank Transfer"), ("upi", "UPI")]
    STATUS = [("created", "Created"), ("success", "Success"), ("failed", "Failed")]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("1"))])
    method = models.CharField(max_length=7, choices=METHODS, default="online")
    status = models.CharField(max_length=7, choices=STATUS, default="created", db_index=True)
    gateway_order_id = models.CharField(max_length=80, blank=True)
    transaction_id = models.CharField(max_length=80, blank=True)
    receipt_no = models.CharField(max_length=20, unique=True, null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="collected_payments")
    paid_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments_made")

    class Meta:
        ordering = ["-created_at"]

    def mark_success(self, transaction_id=""):
        self.status = "success"
        self.transaction_id = transaction_id or self.transaction_id
        self.paid_at = timezone.now()
        if not self.receipt_no:
            self.receipt_no = f"RCPT{timezone.now():%y%m}{self.pk:06d}"
        self.save()

    def __str__(self):
        return f"{self.receipt_no or self.pk} ₹{self.amount} {self.status}"


class Refund(TimeStamped):
    STATUS = [("requested", "Requested"), ("processed", "Processed"), ("rejected", "Rejected")]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="refunds")
    payment = models.ForeignKey(Payment, null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("1"))])
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS, default="requested")
    processed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"Refund ₹{self.amount} {self.invoice}"


# --------------------------------------------------------------------------- 3.5 examination
GRADE_SCALE = [  # (min %, grade, grade point) — 10 point scale
    (90, "O", 10), (80, "E", 9), (70, "A", 8), (60, "B", 7), (50, "C", 6), (40, "D", 5), (0, "F", 0),
]


def grade_for(percent):
    for minimum, grade, point in GRADE_SCALE:
        if percent >= minimum:
            return grade, point
    return "F", 0


def compute_gpa(marks):
    """Credit-weighted grade point average across marks (SGPA for one exam, CGPA across all)."""
    total_credits = Decimal("0")
    weighted = Decimal("0")
    best = {}
    for m in marks.select_related("subject"):
        prev = best.get(m.subject_id)
        if prev is None or m.grade_point > prev.grade_point:
            best[m.subject_id] = m
    for m in best.values():
        total_credits += m.subject.credits
        weighted += m.subject.credits * m.grade_point
    if not total_credits:
        return None
    return round(weighted / total_credits, 2)


class Exam(TimeStamped):
    TYPES = [("INT", "Internal Assessment"), ("SEM", "End Semester"), ("SUP", "Supplementary")]
    name = models.CharField(max_length=120)
    exam_type = models.CharField(max_length=3, choices=TYPES, default="SEM")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="exams")
    semester = models.PositiveSmallIntegerField()
    academic_year = models.CharField(max_length=9)
    max_marks = models.PositiveSmallIntegerField(default=100)
    pass_marks = models.PositiveSmallIntegerField(default=40)
    start_date = models.DateField()
    end_date = models.DateField()
    min_attendance = models.PositiveSmallIntegerField(default=75, help_text="Minimum attendance % to sit for the exam")
    require_fee_clearance = models.BooleanField(default=True)
    marks_locked = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} ({self.course.code} Sem {self.semester})"


class ExamSchedule(TimeStamped):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="schedule")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    venue = models.CharField(max_length=80)

    class Meta:
        ordering = ["date", "start_time"]
        unique_together = ("exam", "subject")

    def __str__(self):
        return f"{self.exam} {self.subject.code} {self.date}"


class Mark(TimeStamped):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="marks")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="marks")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="marks")
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])
    is_absent = models.BooleanField(default=False)
    grade = models.CharField(max_length=2, blank=True)
    grade_point = models.PositiveSmallIntegerField(default=0)
    entered_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("exam", "subject", "student")
        ordering = ["student__roll_no", "subject__code"]

    def save(self, *args, **kwargs):
        if self.is_absent:
            self.marks_obtained = Decimal("0")
        percent = float(self.marks_obtained) * 100 / max(self.exam.max_marks, 1)
        self.grade, self.grade_point = grade_for(percent)
        if self.marks_obtained < self.exam.pass_marks:  # pass_marks is absolute, out of max_marks
            self.grade, self.grade_point = "F", 0
        super().save(*args, **kwargs)

    @property
    def is_pass(self):
        return self.grade != "F"

    def __str__(self):
        return f"{self.student.roll_no} {self.subject.code} {self.marks_obtained}"


class Revaluation(TimeStamped):
    STATUS = [("requested", "Requested"), ("in_progress", "In Progress"), ("completed", "Completed"), ("rejected", "Rejected")]
    mark = models.ForeignKey(Mark, on_delete=models.CASCADE, related_name="revaluations")
    reason = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS, default="requested")
    old_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    new_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    handled_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Revaluation {self.mark}"


# --------------------------------------------------------------------------- 3.6 placement
class Company(TimeStamped):
    name = models.CharField(max_length=150, unique=True)
    industry = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    contact_person = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    logo = models.CharField(max_length=255, blank=True)
    recruiters = models.ManyToManyField(User, blank=True, related_name="companies", limit_choices_to={"role": "recruiter"})
    is_approved = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "companies"

    def __str__(self):
        return self.name


class PlacementProfile(TimeStamped):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name="placement_profile")
    is_registered = models.BooleanField(default=False)
    resume = models.FileField(upload_to="resumes/", blank=True, validators=[FileExtensionValidator(["pdf", "doc", "docx"])])
    skills = models.CharField(max_length=300, blank=True)
    linkedin = models.URLField(blank=True)
    github = models.URLField(blank=True)
    summary = models.TextField(blank=True)

    def __str__(self):
        return f"Placement profile {self.student}"


class JobPosting(TimeStamped):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="jobs")
    title = models.CharField(max_length=150)
    description = models.TextField()
    location = models.CharField(max_length=120, blank=True)
    package_lpa = models.DecimalField("Package (LPA)", max_digits=6, decimal_places=2)
    vacancies = models.PositiveIntegerField(default=1)
    eligible_courses = models.ManyToManyField(Course, blank=True, related_name="jobs")
    min_cgpa = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("6.0"))
    max_backlogs = models.PositiveSmallIntegerField(default=0)
    min_attendance = models.PositiveSmallIntegerField(default=0)
    deadline = models.DateField()
    is_open = models.BooleanField(default=True)
    posted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def eligibility_for(self, student):
        """Return (eligible, [reasons]) using CGPA, backlogs and attendance."""
        reasons = []
        if self.eligible_courses.exists() and not self.eligible_courses.filter(pk=student.course_id).exists():
            reasons.append("Course not eligible")
        cgpa = student.cgpa()
        if cgpa is not None and cgpa < self.min_cgpa:
            reasons.append(f"CGPA {cgpa} < {self.min_cgpa}")
        if len(student.backlogs()) > self.max_backlogs:
            reasons.append(f"Backlogs exceed {self.max_backlogs}")
        att = student.attendance_percentage()
        if self.min_attendance and att is not None and att < self.min_attendance:
            reasons.append(f"Attendance {att}% < {self.min_attendance}%")
        return (not reasons), reasons

    def __str__(self):
        return f"{self.title} @ {self.company}"


class PlacementDrive(TimeStamped):
    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="drives")
    date = models.DateField()
    venue = models.CharField(max_length=120)
    rounds = models.CharField(max_length=255, default="Aptitude Test, Technical Interview, HR Interview")
    assessment_link = models.URLField(blank=True, help_text="Online assessment platform link")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.job} on {self.date}"


class PlacementApplication(TimeStamped):
    class Stage(models.TextChoices):
        APPLIED = "applied", "Applied"
        SHORTLISTED = "shortlisted", "Shortlisted"
        TEST = "test", "Online Test"
        INTERVIEW = "interview", "Interview"
        SELECTED = "selected", "Selected"
        REJECTED = "rejected", "Rejected"

    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="applications")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="job_applications")
    stage = models.CharField(max_length=12, choices=Stage.choices, default=Stage.APPLIED, db_index=True)
    interview_at = models.DateTimeField(null=True, blank=True)
    offer_letter = models.FileField(upload_to="offers/", blank=True, validators=[FileExtensionValidator(["pdf"])])
    offered_package = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("job", "student")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} → {self.job} ({self.stage})"
