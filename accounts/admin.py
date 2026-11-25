from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuditLog, Notification, User


@admin.register(User)
class CMSUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "department", "is_active")
    list_filter = ("role", "is_active", "department")
    fieldsets = UserAdmin.fieldsets + (("College", {"fields": ("role", "phone", "department", "avatar")}),)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "target", "ip_address")
    list_filter = ("action",)
    search_fields = ("target", "details", "user__username")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Notification)
