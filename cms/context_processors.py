from django.conf import settings

from .permissions import menu_for


def portal(request):
    if not request.path.startswith(("/portal", "/accounts/profile")) or not request.user.is_authenticated:
        return {}
    return {
        "portal_menu": menu_for(request.user, request.path),
        "unread_count": request.user.notifications.filter(is_read=False).count(),
        "attendance_threshold": settings.ATTENDANCE_THRESHOLD,
    }
