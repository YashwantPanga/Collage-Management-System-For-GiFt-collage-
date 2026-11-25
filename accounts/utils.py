from django.conf import settings
from django.core.mail import send_mail

from .models import AuditLog, Notification


def client_ip(request):
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or None


def audit(request, action, target="", details="", user=None):
    """Record a key action (approvals, marks changes, payments...) in the audit log."""
    if user is None and request is not None and request.user.is_authenticated:
        user = request.user
    AuditLog.objects.create(
        user=user, action=action, target=str(target)[:200], details=details, ip_address=client_ip(request)
    )


def notify(users, title, message="", link="", level="info", email=False):
    """Create in-app notifications (and optionally e-mail) for one or many users."""
    if users is None:
        return
    if not isinstance(users, (list, tuple, set)) and not hasattr(users, "__iter__"):
        users = [users]
    users = [u for u in users if u is not None]
    Notification.objects.bulk_create(
        [Notification(user=u, title=title, message=message, link=link, level=level) for u in users]
    )
    if email:
        recipients = [u.email for u in users if u.email]
        if recipients:
            send_mail(title, f"{message}\n\n{link}", settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)
