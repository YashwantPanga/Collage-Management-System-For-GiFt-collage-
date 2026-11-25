from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView, TokenVerifyView

from . import views

router = DefaultRouter()
router.register("departments", views.DepartmentViewSet)
router.register("courses", views.CourseViewSet)
router.register("subjects", views.SubjectViewSet)
router.register("students", views.StudentViewSet, basename="student")
router.register("applications", views.ApplicationViewSet, basename="application")
router.register("attendance", views.AttendanceViewSet, basename="attendance")
router.register("invoices", views.InvoiceViewSet, basename="invoice")
router.register("payments", views.PaymentViewSet, basename="payment")
router.register("exams", views.ExamViewSet)
router.register("marks", views.MarkViewSet, basename="mark")
router.register("companies", views.CompanyViewSet)
router.register("jobs", views.JobViewSet, basename="job")
router.register("leaves", views.LeaveViewSet, basename="leave")
router.register("timetable", views.TimetableViewSet, basename="timetable")
router.register("notifications", views.NotificationViewSet, basename="notification")
router.register("events", views.EventViewSet)
router.register("notices", views.NoticeViewSet)

urlpatterns = [
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("auth/logout/", TokenBlacklistView.as_view(), name="token_blacklist"),
    path("me/", views.me, name="api_me"),
    path("", include(router.urls)),
]
