from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from accounts.models import Role

from .models import Student


def students_for(user):
    """Students the user may see as 'own' data: themselves (student) or their wards (parent)."""
    if user.role == Role.STUDENT:
        return Student.objects.filter(user=user)
    if user.role == Role.PARENT:
        return Student.objects.filter(parent=user)
    return Student.objects.none()


def pick_student(request):
    """Resolve the student a student/parent is looking at (parents may pass ?ward=<id>)."""
    qs = students_for(request.user).select_related("user", "course", "batch")
    ward = request.GET.get("ward")
    if ward:
        return get_object_or_404(qs, pk=ward), qs
    return qs.first(), qs


def ensure_student_access(user, student):
    """Staff with module access are checked by decorators; students/parents only see their own."""
    if user.role in (Role.STUDENT, Role.PARENT) and not students_for(user).filter(pk=student.pk).exists():
        raise PermissionDenied
