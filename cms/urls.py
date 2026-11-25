from django.urls import path

from .views import admission, attendance, common, crud, exams, faculty, fees, placement

app_name = "cms"

urlpatterns = [
    path("", common.dashboard, name="dashboard"),
    path("notifications/", common.notifications, name="notifications"),
    path("notifications/<int:pk>/", common.notification_open, name="notification_open"),
    path("notifications/feed/", common.notification_feed, name="notification_feed"),
    path("audit/", common.audit_log, name="audit_log"),

    # generic master-data CRUD
    path("r/<slug:slug>/", crud.resource_list, name="resource_list"),
    path("r/<slug:slug>/add/", crud.resource_form, name="resource_add"),
    path("r/<slug:slug>/<int:pk>/edit/", crud.resource_form, name="resource_edit"),
    path("r/<slug:slug>/<int:pk>/delete/", crud.resource_delete, name="resource_delete"),

    # 3.1 admission
    path("admission/apply/", admission.apply, name="apply"),
    path("admission/mine/", admission.my_applications, name="my_applications"),
    path("admission/applications/", admission.applications, name="applications"),
    path("admission/applications/<int:pk>/", admission.application_detail, name="application_detail"),
    path("admission/applications/<int:pk>/<str:action>/", admission.application_action, name="application_action"),
    path("admission/applications/<int:pk>/enroll/do/", admission.enroll, name="enroll"),
    path("admission/documents/<int:pk>/verify/", admission.verify_document, name="verify_document"),
    path("admission/students/", admission.students, name="students"),
    path("admission/students/<int:pk>/", admission.student_detail, name="student_detail"),
    path("admission/report/", admission.admission_report, name="admission_report"),

    # 3.2 faculty
    path("faculty/me/", faculty.my_faculty, name="my_faculty"),
    path("faculty/leaves/", faculty.leaves, name="leaves"),
    path("faculty/leaves/<int:pk>/<str:decision>/", faculty.leave_decide, name="leave_decide"),
    path("faculty/attendance/", faculty.faculty_attendance, name="faculty_attendance"),
    path("faculty/timetable/", faculty.timetable, name="timetable"),
    path("faculty/workload/", faculty.workload, name="workload"),
    path("attendance/timetable/", faculty.class_timetable, name="class_timetable"),
    path("faculty/payroll/", faculty.payroll, name="payroll"),
    path("faculty/payroll/<int:pk>/", faculty.payslip, name="payslip"),

    # 3.3 attendance
    path("attendance/take/", attendance.take_attendance, name="take_attendance"),
    path("attendance/session/<int:pk>/", attendance.attendance_session, name="attendance_session"),
    path("attendance/qr/<str:token>/", attendance.qr_mark, name="qr_mark"),
    path("attendance/mine/", attendance.my_attendance, name="my_attendance"),
    path("attendance/report/", attendance.attendance_report, name="attendance_report"),

    # 3.4 fees
    path("fees/mine/", fees.my_fees, name="my_fees"),
    path("fees/invoices/", fees.invoices, name="invoices"),
    path("fees/invoices/generate/", fees.generate_invoices, name="generate_invoices"),
    path("fees/invoices/<int:pk>/", fees.invoice_detail, name="invoice_detail"),
    path("fees/invoices/<int:pk>/pay/", fees.pay_invoice, name="pay_invoice"),
    path("fees/payments/", fees.payments, name="payments"),
    path("fees/payments/<int:pk>/callback/", fees.payment_callback, name="payment_callback"),
    path("fees/receipt/<int:pk>/", fees.receipt, name="receipt"),
    path("fees/refunds/", fees.refunds, name="refunds"),
    path("fees/reports/", fees.fee_reports, name="fee_reports"),

    # 3.5 examination
    path("exams/schedule/", exams.exam_schedule, name="exam_schedule"),
    path("exams/marks/", exams.marks_entry, name="marks_entry"),
    path("exams/results/", exams.results_admin, name="results_admin"),
    path("exams/my-results/", exams.my_results, name="my_results"),
    path("exams/marksheet/<int:exam_pk>/<int:student_pk>/", exams.marksheet, name="marksheet"),
    path("exams/hall-ticket/<int:exam_pk>/", exams.hall_ticket, name="hall_ticket"),
    path("exams/revaluation/", exams.revaluations, name="revaluations"),

    # 3.6 placement
    path("placement/profile/", placement.placement_profile, name="placement_profile"),
    path("placement/jobs/", placement.jobs, name="jobs"),
    path("placement/jobs/new/", placement.job_form, name="job_add"),
    path("placement/jobs/<int:pk>/", placement.job_detail, name="job_detail"),
    path("placement/jobs/<int:pk>/edit/", placement.job_form, name="job_edit"),
    path("placement/applications/<int:pk>/", placement.application_stage, name="application_stage"),
    path("placement/my-applications/", placement.my_job_applications, name="my_job_applications"),
    path("placement/stats/", placement.placement_stats, name="placement_stats"),
]
