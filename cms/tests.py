"""End-to-end workflow tests covering every module of the requirements document."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import AuditLog, Notification, Role
from cms import models as m

User = get_user_model()
PWD = "Test@12345x"


def mk_user(username, role, dept=None):
    u = User.objects.create_user(username=username, password=PWD, role=role, department=dept, email=f"{username}@t.in",
                                 first_name=username.title())
    return u


@override_settings(ALLOWED_HOSTS=["*"], MEDIA_ROOT="test_media")
class WorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = m.Department.objects.create(name="Computer Science", code="CSE")
        cls.course = m.Course.objects.create(name="B.Tech CSE", code="BTCSE", department=cls.dept)
        cls.batch = m.Batch.objects.create(course=cls.course, academic_year="2026-2027", start_year=2026, current_semester=1)
        cls.admin = mk_user("admin", Role.SUPERADMIN)
        cls.principal = mk_user("principal", Role.PRINCIPAL)
        cls.hod = mk_user("hod", Role.HOD, cls.dept)
        cls.officer = mk_user("officer", Role.ADMISSION)
        cls.accountant = mk_user("accountant", Role.ACCOUNTANT)
        cls.examofficer = mk_user("examofficer", Role.EXAM)
        cls.placement = mk_user("placementofficer", Role.PLACEMENT)
        cls.fac_user = mk_user("teacher", Role.FACULTY, cls.dept)
        cls.faculty = m.FacultyProfile.objects.create(user=cls.fac_user, employee_id="F1", department=cls.dept, basic_salary=Decimal("50000"))
        cls.subject = m.Subject.objects.create(course=cls.course, semester=1, code="CS101", name="Programming", credits=4, faculty=cls.fac_user)
        cls.fs = m.FeeStructure.objects.create(course=cls.course, academic_year="2026-2027", semester=1, category="GEN",
                                               tuition_fee=Decimal("50000"), exam_fee=Decimal("2000"), due_date=date.today() + timedelta(days=30))

    def login(self, user):
        self.client.force_login(user)

    # ------------------------------------------------------------------ authentication
    def test_register_login_logout_and_lockout(self):
        r = self.client.post(reverse("accounts:register"), {
            "role": "student", "first_name": "Asha", "last_name": "Das", "username": "asha", "email": "asha@x.in",
            "phone": "9999999999", "password1": "Strong#Pass2026", "password2": "Strong#Pass2026"})
        self.assertRedirects(r, reverse("cms:apply"))
        self.client.post(reverse("accounts:logout"))
        r = self.client.post(reverse("accounts:login"), {"username": "asha@x.in", "password": "Strong#Pass2026"})
        self.assertRedirects(r, reverse("cms:dashboard"))
        self.client.post(reverse("accounts:logout"))
        for _ in range(5):
            self.client.post(reverse("accounts:login"), {"username": "asha", "password": "wrong"})
        r = self.client.post(reverse("accounts:login"), {"username": "asha", "password": "Strong#Pass2026"})
        self.assertContains(r, "Too many failed attempts")

    def test_staff_role_cannot_self_register(self):
        r = self.client.post(reverse("accounts:register"), {
            "role": "superadmin", "first_name": "X", "username": "x", "email": "x@x.in", "phone": "1",
            "password1": "Strong#Pass2026", "password2": "Strong#Pass2026"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="x").exists())

    def test_rbac_blocks_student_from_staff_pages(self):
        stu = mk_user("s1", Role.STUDENT)
        self.login(stu)
        for name in ["cms:applications", "cms:invoices", "cms:marks_entry", "cms:audit_log", "cms:payroll"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.client.get(reverse("cms:resource_list", args=["user"])).status_code, 403)

    # ------------------------------------------------------------------ admission -> enrollment -> fees
    def test_full_admission_lifecycle(self):
        applicant = mk_user("applicant", Role.STUDENT)
        self.login(applicant)
        r = self.client.post(reverse("cms:apply"), {
            "course": self.course.pk, "full_name": "Ravi Kumar", "email": "ravi@x.in", "phone": "9000000000", "date_of_birth": "2008-01-01",
            "gender": "Male", "category": "GEN", "guardian_name": "Father", "guardian_phone": "9000000001", "address": "BBSR",
            "previous_institution": "DAV", "qualifying_exam": "JEE", "percentage": "88.5", "entrance_rank": "1234"})
        app = m.Application.objects.get(applicant=applicant)
        self.assertRedirects(r, reverse("cms:application_detail", args=[app.pk]))
        self.assertTrue(app.application_no.startswith("GIFT"))
        doc = SimpleUploadedFile("marks.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        self.client.post(reverse("cms:application_detail", args=[app.pk]), {"upload": "1", "doc_type": "12th", "file": doc})
        self.assertEqual(app.documents.count(), 1)
        # applicant cannot approve their own application
        self.assertEqual(self.client.post(reverse("cms:application_action", args=[app.pk, "approve"])).status_code, 403)

        self.login(self.officer)
        self.client.post(reverse("cms:verify_document", args=[app.documents.first().pk]), {"verified": "1"})
        self.client.post(reverse("cms:application_action", args=[app.pk, "verify"]), {"remarks": "ok"})
        app.refresh_from_db()
        self.assertEqual(app.status, "verified")
        self.login(self.principal)
        self.client.post(reverse("cms:application_action", args=[app.pk, "approve"]))
        app.refresh_from_db()
        self.assertEqual(app.status, "approved")
        self.login(self.officer)
        self.client.post(reverse("cms:enroll", args=[app.pk]), {"batch": self.batch.pk})
        app.refresh_from_db()
        self.assertEqual(app.status, "enrolled")
        student = app.student
        self.assertTrue(student.roll_no.startswith("26BTCS"))
        inv = student.invoices.get()
        self.assertEqual(inv.net, Decimal("52000"))
        self.assertTrue(Notification.objects.filter(user=applicant, title__icontains="Welcome").exists())
        self.assertTrue(AuditLog.objects.filter(action="admission.enroll").exists())

        # online payment through the demo gateway
        self.login(applicant)
        self.client.post(reverse("cms:pay_invoice", args=[inv.pk]), {"amount": "52000"})
        pay = inv.payments.get()
        r = self.client.post(reverse("cms:payment_callback", args=[pay.pk]), {"result": "success", "order": pay.gateway_order_id})
        pay.refresh_from_db()
        self.assertEqual(pay.status, "success")
        self.assertRedirects(r, reverse("cms:receipt", args=[pay.pk]))
        self.assertEqual(inv.balance, 0)
        self.assertEqual(self.client.get(reverse("cms:receipt", args=[pay.pk])).status_code, 200)
        # another student cannot see this receipt
        other = mk_user("other", Role.STUDENT)
        self.login(other)
        self.assertEqual(self.client.get(reverse("cms:receipt", args=[pay.pk])).status_code, 403)

    def _student(self, username="stu", parent=None):
        u = mk_user(username, Role.STUDENT)
        return m.Student.objects.create(user=u, course=self.course, batch=self.batch, parent=parent)

    # ------------------------------------------------------------------ attendance (manual + QR + shortage alerts)
    def test_attendance_manual_qr_and_shortage(self):
        parent = mk_user("parent", Role.PARENT)
        s1, s2 = self._student("a1", parent), self._student("a2")
        self.login(self.fac_user)
        for i in range(5):
            self.client.post(reverse("cms:take_attendance"), {"subject": self.subject.pk, "batch": self.batch.pk,
                                                                  "date": (date.today() - timedelta(days=i)).isoformat(), "period": 1})
            sess = m.AttendanceSession.objects.latest("id")
            self.client.post(reverse("cms:attendance_session", args=[sess.pk]), {f"st_{s1.pk}": "A", f"st_{s2.pk}": "P"})
        self.assertEqual(s1.attendance_percentage(), 0)
        self.assertEqual(s2.attendance_percentage(), 100)
        self.assertTrue(Notification.objects.filter(user=parent, title="Attendance shortage").exists())
        # QR flow
        sess.open_qr(10)
        self.login(s1.user)
        self.client.get(reverse("cms:qr_mark", args=[sess.qr_token]))
        self.assertEqual(m.AttendanceRecord.objects.get(session=sess, student=s1).status, "P")
        # faculty of another subject cannot mark this session
        other_fac = mk_user("otherfac", Role.FACULTY, self.dept)
        self.login(other_fac)
        self.assertEqual(self.client.get(reverse("cms:attendance_session", args=[sess.pk])).status_code, 403)

    # ------------------------------------------------------------------ exams: marks, GPA, publish, revaluation, hall ticket
    def test_marks_gpa_publish_and_revaluation(self):
        parent = mk_user("p2", Role.PARENT)
        s = self._student("e1", parent)
        exam = m.Exam.objects.create(name="End Sem", exam_type="SEM", course=self.course, semester=1, academic_year="2026-2027",
                                     start_date=date.today(), end_date=date.today(), require_fee_clearance=False, min_attendance=0)
        self.login(self.fac_user)
        url = reverse("cms:marks_entry") + f"?exam={exam.pk}&subject={self.subject.pk}"
        self.client.post(url, {f"m_{s.pk}": "85"})
        mk = m.Mark.objects.get(student=s)
        self.assertEqual((mk.grade, mk.grade_point), ("E", 9))
        self.client.post(url, {f"m_{s.pk}": "150"})  # out of range is rejected
        mk.refresh_from_db()
        self.assertEqual(mk.marks_obtained, Decimal("85"))
        self.login(self.examofficer)
        self.client.post(reverse("cms:results_admin"), {"exam": exam.pk, "action": "publish"})
        exam.refresh_from_db()
        self.assertTrue(exam.is_published and exam.marks_locked)
        self.assertEqual(s.cgpa(), Decimal("9.00"))
        self.assertTrue(Notification.objects.filter(user=parent, title="Results published").exists())
        # parent sees ward results; student requests revaluation
        self.login(parent)
        self.assertContains(self.client.get(reverse("cms:my_results")), "End Sem")
        self.login(s.user)
        self.client.post(reverse("cms:revaluations"), {"mark": mk.pk, "reason": "Recheck Q3"})
        rv = m.Revaluation.objects.get()
        self.login(self.examofficer)
        self.client.post(reverse("cms:revaluations"), {"id": rv.pk, "status": "completed", "new_marks": "91"})
        mk.refresh_from_db()
        self.assertEqual(mk.grade, "O")
        self.assertTrue(AuditLog.objects.filter(action="marks.revaluation_change").exists())

    def test_hall_ticket_blocked_by_fee_dues(self):
        s = self._student("h1")
        m.Invoice.objects.create(student=s, semester=1, tuition_fee=Decimal("1000"), due_date=date.today())
        exam = m.Exam.objects.create(name="Sem", course=self.course, semester=1, academic_year="2026-2027",
                                     start_date=date.today(), end_date=date.today(), min_attendance=0)
        self.login(s.user)
        self.assertContains(self.client.get(reverse("cms:hall_ticket", args=[exam.pk])), "Fee dues")

    # ------------------------------------------------------------------ faculty: leave -> attendance -> payroll
    def test_leave_approval_feeds_payroll(self):
        self.login(self.fac_user)
        start = date.today().replace(day=1)
        self.client.post(reverse("cms:leaves"), {"apply": "1", "leave_type": "LOP", "from_date": start.isoformat(),
                                                 "to_date": (start + timedelta(days=1)).isoformat(), "reason": "Family"})
        leave = m.LeaveRequest.objects.get()
        self.login(self.hod)
        self.client.post(reverse("cms:leave_decide", args=[leave.pk, "approved"]))
        leave.refresh_from_db()
        self.assertEqual(leave.status, "approved")
        self.assertEqual(self.faculty.attendance.filter(status="L").count(), 2)
        self.login(self.accountant)
        self.client.post(reverse("cms:payroll"), {"generate": "1", "month": start.strftime("%Y-%m")})
        pr = m.Payroll.objects.get(faculty=self.faculty)
        self.assertGreaterEqual(pr.lop_days, 2)
        self.assertLess(pr.net_pay, pr.basic + pr.allowances)

    # ------------------------------------------------------------------ placement eligibility + pipeline
    def test_placement_eligibility_and_selection(self):
        s = self._student("pl1")
        m.PlacementProfile.objects.create(student=s, is_registered=True)
        comp = m.Company.objects.create(name="Acme", is_approved=True)
        recruiter = mk_user("rec", Role.RECRUITER)
        comp.recruiters.add(recruiter)
        job = m.JobPosting.objects.create(company=comp, title="SDE", description="x", package_lpa=Decimal("8"),
                                          min_cgpa=Decimal("7"), deadline=date.today() + timedelta(days=5))
        exam = m.Exam.objects.create(name="S", course=self.course, semester=1, academic_year="x", start_date=date.today(),
                                     end_date=date.today(), is_published=True)
        m.Mark.objects.create(exam=exam, subject=self.subject, student=s, marks_obtained=Decimal("55"))  # CGPA 6 -> not eligible
        self.login(s.user)
        self.client.post(reverse("cms:job_detail", args=[job.pk]), {"apply": "1"})
        self.assertFalse(job.applications.exists())
        m.Mark.objects.filter(student=s).update(marks_obtained=Decimal("80"), grade="E", grade_point=9)
        self.client.post(reverse("cms:job_detail", args=[job.pk]), {"apply": "1"})
        app = job.applications.get()
        self.login(recruiter)
        self.client.post(reverse("cms:application_stage", args=[app.pk]), {"stage": "selected", "offered_package": "8"})
        app.refresh_from_db()
        self.assertEqual(app.stage, "selected")
        self.assertTrue(Notification.objects.filter(user=s.user, title="Placement update").exists())

    # ------------------------------------------------------------------ REST API with JWT
    def test_api_jwt_and_scoping(self):
        s = self._student("api1")
        other = self._student("api2")
        r = self.client.post("/api/auth/token/", {"username": "api1", "password": PWD}, content_type="application/json")
        token = r.json()["access"]
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        me = self.client.get("/api/me/", **auth).json()
        self.assertEqual(me["role"], "student")
        ids = [x["id"] for x in self.client.get("/api/students/", **auth).json()["results"]]
        self.assertEqual(ids, [s.pk])
        self.assertNotIn(other.pk, ids)
        self.assertEqual(self.client.get("/api/me/").status_code, 401)

    def test_dashboards_render_for_every_role(self):
        self._student("dash")
        for u in [self.admin, self.principal, self.hod, self.officer, self.accountant, self.examofficer, self.placement, self.fac_user]:
            self.login(u)
            self.assertEqual(self.client.get(reverse("cms:dashboard")).status_code, 200, u.role)
