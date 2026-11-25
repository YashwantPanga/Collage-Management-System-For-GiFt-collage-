from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    SUPERADMIN = "superadmin", "Super Admin"
    PRINCIPAL = "principal", "College Principal"
    HOD = "hod", "HOD (Head of Department)"
    ADMISSION = "admission", "Admission Officer"
    FACULTY = "faculty", "Faculty"
    ACCOUNTANT = "accountant", "Accountant"
    EXAM = "exam", "Examination Officer"
    PLACEMENT = "placement", "Placement Officer"
    STUDENT = "student", "Student"
    PARENT = "parent", "Parent"
    RECRUITER = "recruiter", "Recruiter"


# Roles that may sign up on the public website. Staff roles are created by the Super Admin.
SELF_REGISTER_ROLES = (Role.STUDENT, Role.PARENT, Role.RECRUITER)


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT, db_index=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    department = models.ForeignKey(
        "cms.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="users",
        help_text="For HOD / Faculty: the department they belong to.",
    )

    class Meta:
        ordering = ["first_name", "last_name"]

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = Role.SUPERADMIN
        if self.role == Role.SUPERADMIN:
            self.is_staff = True
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    def has_role(self, *roles):
        return self.is_superuser or self.role in roles

    def __str__(self):
        return f"{self.display_name} ({self.get_role_display()})"


class Notification(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Info"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        DANGER = "danger", "Alert"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=200, blank=True)
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.user} {self.action} {self.target}"
