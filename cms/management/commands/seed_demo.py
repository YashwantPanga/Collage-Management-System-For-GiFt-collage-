"""
Load realistic demo data for GIFT Autonomous so every module and role can be tried out.

    python manage.py seed_demo            # create demo data (idempotent for masters)
    python manage.py seed_demo --flush    # wipe college data first

All demo accounts share the password in DEMO_PASSWORD (see README.md). Change them before going live.
"""
import random
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Role
from cms import models as m
from website.models import FAQ, Event, Notice, Testimonial

User = get_user_model()
DEMO_PASSWORD = "Gift@2026"

DEPARTMENTS = [
    ("Computer Science & Engineering", "CSE", "Programming, AI/ML, data science and cloud computing with industry-certified labs."),
    ("Electronics & Communication Engineering", "ECE", "VLSI, embedded systems, IoT and communication networks."),
    ("Electrical Engineering", "EE", "Power systems, drives, renewable energy and smart grids."),
    ("Mechanical Engineering", "ME", "Design, manufacturing, thermal and automobile engineering — home of the Hybrid Solar Car."),
    ("Civil Engineering", "CE", "Structural, geotechnical, transportation and environmental engineering."),
    ("Business Administration", "MBA", "Management education with a strong industry interface."),
    ("Computer Applications", "MCA", "Software development and IT management."),
]

COURSES = [
    ("B.Tech in Computer Science & Engineering", "BTCSE", "CSE", "UG", 4, 8, 180, "brand/prog-btech.jpg", "10+2 with PCM, JEE Main / OJEE rank"),
    ("B.Tech in Electronics & Communication", "BTECE", "ECE", "UG", 4, 8, 120, "brand/gift-a3.jpg", "10+2 with PCM, JEE Main / OJEE rank"),
    ("B.Tech in Electrical Engineering", "BTEE", "EE", "UG", 4, 8, 120, "brand/gift-a4.jpg", "10+2 with PCM, JEE Main / OJEE rank"),
    ("B.Tech in Mechanical Engineering", "BTME", "ME", "UG", 4, 8, 120, "brand/gift-a1.jpg", "10+2 with PCM, JEE Main / OJEE rank"),
    ("B.Tech in Civil Engineering", "BTCE", "CE", "UG", 4, 8, 60, "brand/hero-gate.jpg", "10+2 with PCM, JEE Main / OJEE rank"),
    ("M.Tech in Computer Science", "MTCSE", "CSE", "PG", 2, 4, 18, "brand/prog-mtech.jpg", "B.Tech / B.E. with GATE / OJEE PG"),
    ("Master of Business Administration", "MBA", "MBA", "PG", 2, 4, 120, "brand/prog-mba.jpg", "Graduation with CAT / MAT / OJEE"),
    ("Master of Computer Applications", "MCA", "MCA", "PG", 2, 4, 60, "brand/prog-mca.jpg", "Graduation with Mathematics, OJEE"),
    ("Diploma in Engineering (Lateral)", "DIP", "ME", "DIP", 3, 6, 60, "brand/hero-gate.jpg", "10th pass"),
    ("Ph.D in Engineering & Management", "PHD", "CSE", "PHD", 3, 6, 20, "brand/prog-phd.jpg", "Master's degree with 55%"),
]

SUBJECTS = {
    "BTCSE": {1: [("Engineering Mathematics I", 4), ("Programming in C", 4), ("Engineering Physics", 3), ("Basic Electrical Engg.", 3), ("Communicative English", 2)],
              3: [("Data Structures", 4), ("Discrete Mathematics", 3), ("Digital Electronics", 3), ("Object Oriented Programming", 4), ("Computer Organization", 3)],
              5: [("Database Management Systems", 4), ("Operating Systems", 4), ("Design & Analysis of Algorithms", 4), ("Computer Networks", 3), ("Machine Learning", 3)]},
    "BTECE": {3: [("Network Theory", 4), ("Analog Electronics", 4), ("Signals & Systems", 3), ("Digital Logic Design", 3)]},
    "BTME": {3: [("Engineering Thermodynamics", 4), ("Strength of Materials", 4), ("Fluid Mechanics", 3), ("Manufacturing Processes", 3)]},
    "MBA": {1: [("Principles of Management", 3), ("Managerial Economics", 3), ("Financial Accounting", 3), ("Marketing Management", 3)]},
    "MCA": {1: [("Programming with Python", 4), ("Data Structures using C", 4), ("Discrete Mathematics", 3), ("Computer Networks", 3)]},
}

FIRST = ["Aarav", "Ananya", "Rohit", "Sneha", "Subham", "Priyanka", "Ankit", "Ipsita", "Rakesh", "Smruti", "Debasish", "Pooja", "Sourav",
         "Lipsa", "Abhishek", "Sasmita", "Amit", "Monalisa", "Biswajit", "Swati", "Satyajit", "Pragyan", "Ashutosh", "Riya", "Sandeep",
         "Barsha", "Manas", "Sonali", "Pritam", "Tanuja", "Jyoti", "Sagar", "Ritika", "Bikash", "Shreya", "Om", "Nandini", "Arpit"]
LAST = ["Mohanty", "Panda", "Sahoo", "Das", "Mishra", "Behera", "Nayak", "Pradhan", "Swain", "Rout", "Patnaik", "Jena", "Dash", "Parida", "Samal", "Biswal"]


class Command(BaseCommand):
    help = "Create GIFT Autonomous demo data for all modules and roles."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Delete existing college data first")

    def user(self, username, first, last, role, dept=None, email=None, superuser=False):
        u, created = User.objects.get_or_create(username=username, defaults={
            "first_name": first, "last_name": last, "role": role, "department": dept,
            "email": email or f"{username}@gift.edu.in", "phone": f"+91 9{random.randint(100000000, 999999999)}",
            "is_superuser": superuser, "is_staff": superuser,
        })
        if created:
            u.set_password(DEMO_PASSWORD)
            u.save()
        return u

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(2026)
        if opts["flush"]:
            for model in [m.PlacementApplication, m.PlacementDrive, m.JobPosting, m.PlacementProfile, m.Company, m.Revaluation, m.Mark,
                          m.ExamSchedule, m.Exam, m.Refund, m.Payment, m.Invoice, m.Scholarship, m.FeeStructure, m.AttendanceRecord,
                          m.AttendanceSession, m.Payroll, m.PerformanceReview, m.LeaveRequest, m.FacultyAttendance, m.ApplicationDocument,
                          m.Application, m.Student, m.TimetableSlot, m.Subject, m.FacultyProfile, m.Batch, m.Course, Event, Notice, FAQ, Testimonial]:
                model.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            m.Department.objects.all().delete()

        today = timezone.localdate()
        year = today.year if today.month >= 6 else today.year - 1
        ay = f"{year}-{year + 1}"

        # ---------------------------------------------------------------- masters
        depts = {}
        for name, code, desc in DEPARTMENTS:
            depts[code], _ = m.Department.objects.get_or_create(code=code, defaults={"name": name, "description": desc})
        courses = {}
        for name, code, dcode, level, yrs, sems, seats, img, elig in COURSES:
            courses[code], _ = m.Course.objects.get_or_create(code=code, defaults={
                "name": name, "department": depts[dcode], "level": level, "duration_years": yrs, "total_semesters": sems,
                "seats": seats, "image": img, "eligibility": elig,
                "short_description": f"{yrs}-year {dict(m.Course.Level.choices)[level].lower()} program at GIFT Autonomous, accredited and industry-aligned.",
                "description": f"The {name} program at GIFT Autonomous blends strong fundamentals with hands-on labs, industry projects, "
                               f"internships and mentoring. Students benefit from NAAC A++ quality processes, NBA-accredited curriculum, "
                               f"e-learning and a placement record of 98%+ since 2011.",
            })

        # ---------------------------------------------------------------- staff accounts
        admin = self.user("admin", "System", "Administrator", Role.SUPERADMIN, superuser=True)
        principal = self.user("principal", "Sanjay", "Mohapatra", Role.PRINCIPAL)
        hod_cse = self.user("hod.cse", "Priyambada", "Nayak", Role.HOD, depts["CSE"])
        hod_me = self.user("hod.me", "Bijay", "Kumar Sahu", Role.HOD, depts["ME"])
        for code, h in (("CSE", hod_cse), ("ME", hod_me)):
            depts[code].hod = h
            depts[code].save()
        self.user("admission", "Rashmi", "Pattnaik", Role.ADMISSION)
        accountant = self.user("accountant", "Deepak", "Senapati", Role.ACCOUNTANT)
        self.user("exam", "Manoj", "Tripathy", Role.EXAM)
        self.user("placement", "Sunita", "Rath", Role.PLACEMENT)
        recruiter = self.user("recruiter", "Neha", "Sharma", Role.RECRUITER, email="neha.recruiter@example.com")

        fac_specs = [("faculty", "Subrat", "Mishra", "CSE", "Associate Professor", "Machine Learning"),
                     ("faculty2", "Lopamudra", "Das", "CSE", "Assistant Professor", "Databases"),
                     ("faculty3", "Ajit", "Pradhan", "CSE", "Assistant Professor", "Algorithms"),
                     ("faculty4", "Rajesh", "Behera", "ECE", "Associate Professor", "VLSI"),
                     ("faculty5", "Sangita", "Swain", "ME", "Assistant Professor", "Thermal Engineering"),
                     ("faculty6", "Prakash", "Jena", "MBA", "Professor", "Finance"),
                     ("faculty7", "Itishree", "Rout", "MCA", "Assistant Professor", "Software Engineering")]
        faculty_users = []
        for i, (un, f, l, d, desig, spec) in enumerate(fac_specs, start=1):
            u = self.user(un, f, l, Role.FACULTY, depts[d])
            faculty_users.append(u)
            m.FacultyProfile.objects.get_or_create(user=u, defaults={
                "employee_id": f"GIFT-F{i:03d}", "department": depts[d], "designation": desig, "qualification": "Ph.D, M.Tech",
                "specialization": spec, "experience_years": random.randint(4, 20), "basic_salary": Decimal(random.choice([55000, 65000, 80000, 95000])),
                "bio": f"{desig} in {depts[d].name} specialising in {spec}. Active researcher with publications in reputed journals.",
            })
        for hod, d, n in ((hod_cse, "CSE", 90), (hod_me, "ME", 91)):
            m.FacultyProfile.objects.get_or_create(user=hod, defaults={
                "employee_id": f"GIFT-F{n:03d}", "department": depts[d], "designation": "Professor & HOD", "qualification": "Ph.D",
                "specialization": "Department leadership", "experience_years": 22, "basic_salary": Decimal("120000")})

        # ---------------------------------------------------------------- subjects, batches, timetable
        subjects = {}
        for ccode, sems in SUBJECTS.items():
            dept_fac = [u for u in faculty_users if u.department_id == courses[ccode].department_id] or faculty_users
            for sem, items in sems.items():
                for idx, (sname, credits) in enumerate(items, start=1):
                    sub, _ = m.Subject.objects.get_or_create(code=f"{ccode[:5]}{sem}{idx:02d}", defaults={
                        "course": courses[ccode], "semester": sem, "name": sname, "credits": credits,
                        "faculty": dept_fac[idx % len(dept_fac)], "hours_per_week": credits + 1})
                    subjects.setdefault((ccode, sem), []).append(sub)

        batch_specs = [("BTCSE", year, 1), ("BTCSE", year - 1, 3), ("BTCSE", year - 2, 5), ("BTECE", year - 1, 3), ("BTME", year - 1, 3),
                       ("MBA", year, 1), ("MCA", year, 1)]
        batches = {}
        for ccode, start, sem in batch_specs:
            b, _ = m.Batch.objects.get_or_create(course=courses[ccode], start_year=start, section="A",
                                                 defaults={"academic_year": ay, "current_semester": sem})
            batches[(ccode, sem)] = b
            for d in range(6):
                for p, sub in enumerate(subjects.get((ccode, sem), [])[:5], start=1):
                    if (d + p) % 5 == 4:
                        continue
                    start_t = time(9 + p - 1 if p < 4 else 9 + p, 0)
                    m.TimetableSlot.objects.get_or_create(batch=b, day=d, period=p, defaults={
                        "subject": sub, "faculty": sub.faculty, "start_time": start_t,
                        "end_time": time(start_t.hour, 55), "room": f"{ccode[:3]}-{100 + p}"})

        # ---------------------------------------------------------------- fees
        for c in courses.values():
            for sem in range(1, c.total_semesters + 1):
                base = {"UG": 62000, "PG": 55000, "DIP": 30000, "PHD": 45000}[c.level]
                for cat, factor in (("GEN", 1), ("SC", Decimal("0.5")), ("ST", Decimal("0.5"))):
                    m.FeeStructure.objects.get_or_create(course=c, academic_year=ay, semester=sem, category=cat, defaults={
                        "tuition_fee": Decimal(base) * factor, "exam_fee": Decimal("2500"), "development_fee": Decimal("5000"),
                        "other_fee": Decimal("1500"), "due_date": date(year, 7 if sem % 2 else 12, 31) if sem % 2 else date(year + 1, 1, 15)})
        merit, _ = m.Scholarship.objects.get_or_create(name="Merit Scholarship (90%+)", defaults={"kind": "percent", "value": Decimal("25"), "description": "For students scoring 90%+ in qualifying exam"})
        m.Scholarship.objects.get_or_create(name="Sibling Concession", defaults={"kind": "flat", "value": Decimal("10000")})
        m.Scholarship.objects.get_or_create(name="Sports Quota", defaults={"kind": "percent", "value": Decimal("15")})

        # ---------------------------------------------------------------- students & parents
        if not m.Student.objects.exists():
            n = 0
            parent_demo = self.user("parent", "Ramesh", "Mohanty", Role.PARENT)
            for (ccode, sem), b in batches.items():
                count = 12 if ccode == "BTCSE" else 6
                for k in range(count):
                    n += 1
                    fn, ln = FIRST[n % len(FIRST)], LAST[(n * 7) % len(LAST)]
                    uname = "student" if n == 1 else f"stu{n:03d}"
                    if n == 1:
                        fn, ln = "Ananya", "Mohanty"
                    u = self.user(uname, fn, ln, Role.STUDENT)
                    cat = random.choice(["GEN", "GEN", "GEN", "OBC", "SC", "ST"])
                    parent = parent_demo if n == 1 else None
                    s = m.Student.objects.create(user=u, course=b.course, batch=b, category=cat, parent=parent,
                                                 date_of_birth=date(2006 - (sem // 2), random.randint(1, 12), random.randint(1, 28)),
                                                 gender=random.choice(["Male", "Female"]), address="Bhubaneswar, Odisha",
                                                 admission_date=date(b.start_year, 8, 1))
                    m.PlacementProfile.objects.create(student=s, is_registered=sem >= 5, skills="Python, Java, SQL, Communication")
                    # fees for every semester up to the current one
                    for fsem in range(1, sem + 1):
                        fs = m.FeeStructure.objects.filter(course=b.course, semester=fsem, academic_year=ay,
                                                           category=cat if cat in ("GEN", "SC", "ST") else "GEN").first()
                        inv = m.Invoice.objects.create(student=s, fee_structure=fs, semester=fsem, tuition_fee=fs.tuition_fee,
                                                       exam_fee=fs.exam_fee, other_fee=fs.development_fee + fs.other_fee,
                                                       scholarship=merit if n % 9 == 0 else None,
                                                       due_date=today - timedelta(days=20) if fsem == sem else today - timedelta(days=200 * (sem - fsem)))
                        if fsem < sem or n % 3:
                            amt = inv.net if (fsem < sem or n % 4) else (inv.net / 2).quantize(Decimal("1"))
                            p = m.Payment.objects.create(invoice=inv, amount=amt, method=random.choice(["online", "online", "upi", "cash"]),
                                                         collected_by=accountant, paid_by=u)
                            p.mark_success(f"TXN{p.pk:08d}")
                            p.paid_at = timezone.now() - timedelta(days=random.randint(1, 160))
                            p.save(update_fields=["paid_at"])

        # ---------------------------------------------------------------- attendance (last 4 weeks)
        if not m.AttendanceSession.objects.exists():
            for (ccode, sem), b in batches.items():
                studs = list(b.students.all())
                for back in range(28, 0, -1):
                    d = today - timedelta(days=back)
                    if d.weekday() == 6:
                        continue
                    for slot in b.timetable.filter(day=d.weekday()):
                        sess = m.AttendanceSession.objects.create(subject=slot.subject, batch=b, faculty=slot.faculty, date=d, period=slot.period)
                        recs = []
                        for st in studs:
                            weak = st.pk % 7 == 0
                            status = "P" if random.random() < (0.62 if weak else 0.9) else random.choice(["A", "A", "L"])
                            recs.append(m.AttendanceRecord(session=sess, student=st, status=status, method=random.choice(["manual", "qr"])))
                        m.AttendanceRecord.objects.bulk_create(recs)
            for prof in m.FacultyProfile.objects.all():
                for back in range(1, 26):
                    d = today - timedelta(days=back)
                    if d.weekday() != 6:
                        m.FacultyAttendance.objects.get_or_create(faculty=prof, date=d, defaults={
                            "status": random.choice(["P"] * 12 + ["A", "H"]), "check_in": time(9, random.randint(0, 20)), "check_out": time(17, 0)})

        # ---------------------------------------------------------------- examinations
        if not m.Exam.objects.exists():
            for (ccode, sem), b in batches.items():
                subs = subjects.get((ccode, sem), [])
                if not subs:
                    continue
                prev_sem = sem - 1 if sem > 1 else None
                if prev_sem and subjects.get((ccode, prev_sem)) is None:
                    # create previous-semester subjects so CGPA has history
                    pass
                internal = m.Exam.objects.create(name=f"Mid-Semester {ay}", exam_type="INT", course=b.course, semester=sem, academic_year=ay,
                                                 max_marks=30, pass_marks=12, start_date=today - timedelta(days=40), end_date=today - timedelta(days=35),
                                                 is_published=True, marks_locked=True, published_at=timezone.now() - timedelta(days=30))
                endsem = m.Exam.objects.create(name=f"End-Semester {ay} (Odd)", exam_type="SEM", course=b.course, semester=sem, academic_year=ay,
                                               max_marks=100, pass_marks=40, start_date=today + timedelta(days=25), end_date=today + timedelta(days=35))
                for i, sub in enumerate(subs):
                    m.ExamSchedule.objects.create(exam=endsem, subject=sub, date=today + timedelta(days=25 + i * 2), start_time=time(10, 0),
                                                  end_time=time(13, 0), venue=f"Exam Hall {1 + i % 3}")
                    for st in b.students.all():
                        m.Mark.objects.create(exam=internal, subject=sub, student=st, marks_obtained=Decimal(random.randint(9, 30)), entered_by=sub.faculty)
            # a published previous-semester result for senior CSE batches (SGPA / CGPA / backlogs)
            for (ccode, sem), b in batches.items():
                if sem < 3:
                    continue
                prev_subs = subjects.get((ccode, sem - 2)) or subjects.get((ccode, 1)) or []
                if not prev_subs:
                    continue
                prev = m.Exam.objects.create(name=f"End-Semester Sem {sem - 1}", exam_type="SEM", course=b.course, semester=sem - 1,
                                             academic_year=f"{year - 1}-{year}", max_marks=100, pass_marks=40,
                                             start_date=today - timedelta(days=150), end_date=today - timedelta(days=140),
                                             is_published=True, marks_locked=True, published_at=timezone.now() - timedelta(days=120))
                for st in b.students.all():
                    for sub in prev_subs:
                        mk = random.randint(30, 98) if st.pk % 11 else random.randint(20, 60)
                        m.Mark.objects.create(exam=prev, subject=sub, student=st, marks_obtained=Decimal(mk), entered_by=sub.faculty)

        # ---------------------------------------------------------------- admission applications
        if not m.Application.objects.exists():
            statuses = ["submitted", "submitted", "review", "verified", "approved", "rejected", "submitted", "review"]
            for i, st in enumerate(statuses):
                u = self.user(f"applicant{i + 1}", FIRST[(i * 3) % len(FIRST)], LAST[i % len(LAST)], Role.STUDENT)
                c = random.choice([courses["BTCSE"], courses["BTECE"], courses["MBA"], courses["MCA"]])
                a = m.Application.objects.create(applicant=u, course=c, academic_year=f"{year + 1}-{year + 2}", full_name=u.get_full_name(),
                                                 email=u.email, phone=u.phone, date_of_birth=date(2008, 3, i + 1), gender=random.choice(["Male", "Female"]),
                                                 category="GEN", guardian_name=f"{LAST[i % len(LAST)]} Sr.", guardian_phone="+91 9437000000",
                                                 address="Cuttack, Odisha", previous_institution="DAV Public School", qualifying_exam="+2 Science (CHSE) / JEE Main",
                                                 percentage=Decimal(random.randint(62, 96)), entrance_rank=str(random.randint(5000, 60000)), status=st,
                                                 remarks="Documents incomplete." if st == "rejected" else "")
                a.created_at = timezone.now() - timedelta(days=random.randint(1, 120))
                a.save(update_fields=["created_at"])

        # ---------------------------------------------------------------- faculty HR
        if not m.LeaveRequest.objects.exists():
            for prof in m.FacultyProfile.objects.all()[:5]:
                m.LeaveRequest.objects.create(faculty=prof, leave_type=random.choice(["CL", "SL", "OD"]), from_date=today + timedelta(days=3),
                                              to_date=today + timedelta(days=4), reason="Personal work / conference attendance.")
            for prof in m.FacultyProfile.objects.all():
                m.PerformanceReview.objects.create(faculty=prof, period=f"{year - 1}-{str(year)[-2:]} Even Semester", teaching=random.randint(7, 10),
                                                   research=random.randint(5, 9), student_feedback=random.randint(7, 10), administration=random.randint(6, 9),
                                                   reviewer=principal, comments="Consistent performance.")

        # ---------------------------------------------------------------- placement
        if not m.Company.objects.exists():
            comp_names = [("Tata Consultancy Services", "IT Services"), ("Infosys", "IT Services"), ("Oracle", "Software"), ("Samsung R&D", "Electronics"),
                          ("Maruti Suzuki", "Automobile"), ("ICICI Bank", "Banking"), ("NALCO", "Metals & Mining"), ("Wipro", "IT Services"),
                          ("Vodafone Idea", "Telecom"), ("Jindal Steel & Power", "Steel")]
            comps = []
            for name, ind in comp_names:
                c = m.Company.objects.create(name=name, industry=ind, is_approved=True, contact_person="Campus Relations",
                                             contact_email=f"campus@{name.split()[0].lower()}.example.com")
                comps.append(c)
            comps[0].recruiters.add(recruiter)
            jobs = []
            for c, (title, pkg, cg) in zip(comps[:6], [("Assistant System Engineer", "7.0", "6.0"), ("Systems Engineer", "6.5", "6.5"),
                                                         ("Associate Software Developer", "12.0", "7.5"), ("R&D Engineer", "10.0", "7.0"),
                                                         ("Graduate Engineer Trainee", "5.5", "6.0"), ("Management Trainee", "6.0", "6.0")]):
                j = m.JobPosting.objects.create(company=c, title=title, description=f"{c.name} is hiring {title}s from the {year + 1} batch. "
                                                "Strong fundamentals, problem solving and communication skills required.",
                                                location="Bengaluru / Pune / Hyderabad", package_lpa=Decimal(pkg), vacancies=random.randint(5, 40),
                                                min_cgpa=Decimal(cg), max_backlogs=0, min_attendance=65, deadline=today + timedelta(days=20), posted_by=admin)
                j.eligible_courses.add(courses["BTCSE"], courses["BTECE"], courses["MCA"])
                m.PlacementDrive.objects.create(job=j, date=today + timedelta(days=25), venue="Seminar Hall, Block A",
                                                assessment_link="https://example.com/assessment")
                jobs.append(j)
            seniors = m.Student.objects.filter(batch__current_semester__gte=5)
            for st in seniors:
                for j in random.sample(jobs, 2):
                    stage = random.choice(["applied", "shortlisted", "interview", "selected", "rejected"])
                    m.PlacementApplication.objects.get_or_create(job=j, student=st, defaults={
                        "stage": stage, "offered_package": j.package_lpa if stage == "selected" else None})

        # ---------------------------------------------------------------- website content
        if not Event.objects.exists():
            events = [("Annual Tech Fest — TECHNOVATION", "Three days of hackathons, robotics, coding contests and project expos.", "brand/gift-a2.jpg", 12),
                      ("17th Youth Parliament Competition", "Empowering students through leadership, civic awareness and democratic engagement.", "brand/youth-parliament.jpg", 26),
                      ("Campus Placement Drive — TCS & Infosys", "Mega recruitment drive for the final-year B.Tech and MCA students.", "brand/campus-leader.webp", 33),
                      ("National Conference on Emerging Technologies", "Paper presentations and keynote sessions by industry experts and GIFT faculty.", "brand/gift-a3.jpg", -15)]
            for title, summary, img, delta in events:
                Event.objects.create(title=title, summary=summary, body=summary + "\n\nAll students are encouraged to participate. Registrations are open at the student activity centre.",
                                     image=img, date=today + timedelta(days=delta), start_time=time(9, 30), end_time=time(17, 0))
        if not Notice.objects.exists():
            notices = [("Admission 2026 open for B.Tech, M.Tech, MBA & MCA", "admission", "Apply online through the GIFT portal. Upload your documents and track your application status anytime.", "brand/promo1.webp"),
                       ("GIFT: An MSME Incubation Centre", "achievement", "GIFT is recognised as a Host Institute / Business Incubator under the MSME scheme for entrepreneurial and managerial development.", "brand/gift-1.jpg"),
                       ("GIFT students shine at the National Robotics Fest", "news", "GIFT teams won the 2nd and 3rd prizes at ROBOFEST 2K17, showcasing innovation from our labs.", "brand/gift-a5.jpg"),
                       ("Apply as Supervisor / Co-Supervisor for Ph.D", "notice", "Eligible faculty may apply as supervisors for the Ph.D program. Contact the Ph.D admissions cell for details.", "brand/gift-3-1.png"),
                       ("98% placement for the outgoing batch", "placement", "Congratulations to all GIFTIANs placed in leading companies this season.", "brand/campus-leader.webp")]
            for i, (t, cat, s, img) in enumerate(notices):
                Notice.objects.create(title=t, category=cat, summary=s, body=s + "\n\nFor further details contact info@gift.edu.in.", image=img,
                                      published_on=today - timedelta(days=i * 6))
        if not FAQ.objects.exists():
            for i, (q, a) in enumerate([
                ("How do I apply for admission?", "Register on the portal as a Student, fill the online application, upload your documents and track the status. You'll be notified at every stage."),
                ("What entrance exams are accepted for B.Tech?", "JEE Main and OJEE ranks are accepted. Lateral entry to B.Tech is through the Diploma route."),
                ("Can fees be paid online?", "Yes. Students and parents can pay semester fees online and download receipts instantly from the portal."),
                ("Are scholarships available?", "Merit scholarships, sports quota and government scholarships are available. Concessions are applied directly to your fee invoice."),
                ("How can parents monitor their ward?", "Parents register on the portal and the admission office links them to their ward. They can then see attendance, fees and results."),
                ("What is the placement record?", "GIFT has maintained 98%+ placements since 2011 with recruiters like TCS, Infosys, Oracle, Samsung and Maruti Suzuki."),
            ]):
                FAQ.objects.create(question=q, answer=a, order=i)
        if not Testimonial.objects.exists():
            for i, (n, q, p) in enumerate([
                ("Sagufta Yashmin", "Regular classroom teaching supported by e-learning makes teaching and learning much simpler and lucid.", "brand/gift-t1.jpg"),
                ("Tanuprava Das", "GIFT has an eco-friendly environment and well experienced faculty members who teach with full dedication.", "brand/gift-t2.jpg"),
                ("Yash Aditya", "The college has a majestic infrastructure. We stay connected with teachers through the mentoring system.", "brand/gift-t3.jpg"),
            ]):
                Testimonial.objects.create(name=n, role="3rd Year Student", quote=q, photo=p, order=i)

        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready: {m.Student.objects.count()} students, {m.FacultyProfile.objects.count()} faculty, "
            f"{m.AttendanceRecord.objects.count()} attendance records, {m.Invoice.objects.count()} invoices. "
            f"Demo logins are listed in README.md."))
