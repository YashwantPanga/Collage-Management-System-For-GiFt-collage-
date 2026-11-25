# GIFT Autonomous — College Management System

A complete college website + management portal for **GIFT Autonomous, Bhubaneswar**, built from:

1. **Design** — the *Stadum* university HTML template (all CSS/JS plugins kept: Bootstrap 5, Swiper, GSAP + ScrollTrigger, Magnific Popup, WOW, Isotope, CounterUp, Lenis).
2. **Features** — the *College Management System — Requirements* document (11 roles, 7 modules).
3. **Branding** — logo, campus photos, accreditations and content from the GIFT Autonomous website (`static/brand/`).

Stack: Python 3.11 · Django 5.2 · Django REST Framework · JWT (SimpleJWT) · SQLite (dev) / PostgreSQL (prod) · Chart.js · WhiteNoise · Docker.

---

## Quick start (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_demo
.\.venv\Scripts\python manage.py runserver
```

Open http://127.0.0.1:8000 (website) and http://127.0.0.1:8000/portal/ (portal).

### Demo accounts (created by `seed_demo`)

All demo accounts use the password **`Gift@2026`** — change or delete them before going live.

| Role | Username |
|---|---|
| Super Admin | `admin` |
| College Principal | `principal` |
| HOD (CSE / ME) | `hod.cse`, `hod.me` |
| Admission Officer | `admission` |
| Faculty | `faculty` … `faculty7` |
| Accountant | `accountant` |
| Examination Officer | `exam` |
| Placement Officer | `placement` |
| Student | `student` (plus `stu002`…) |
| Applicant (not yet enrolled) | `applicant1` … `applicant8` |
| Parent (linked to `student`) | `parent` |
| Recruiter | `recruiter` |

`python manage.py seed_demo --flush` wipes college data and recreates it.

---

## What is included

### Public website (template pages, GIFT content, live data)
Home (hero slider, programs, counters, why-GIFT, accreditations, campus life, events, admission CTA, recruiters, testimonials, FAQ, news) · About · Departments · Programs + program details (curriculum & fee table) · Faculty + profiles · Events · Notices & News · Campus Life gallery · Placements · Admission 2026 · FAQ · Contact (saved to DB, honeypot anti-spam) · Search · branded 404/403. Login/Register popup from the template is wired to real authentication. Fully responsive (template breakpoints + mobile menu).

### Authentication & security
Login by username **or** email, registration for Student/Parent/Recruiter (staff accounts are created by the Super Admin), password reset by email, password change, profile & avatar, brute-force lockout (5 failures → 15 min), CSRF, hashed passwords, secure cookies/HSTS in production, **JWT** for the API (access/refresh/blacklist), role-based access control on every view and API endpoint, and an **audit log** of approvals, marks changes, payments and logins.

### Portal modules (requirements §3)
| Module | Features |
|---|---|
| **Admission** | Online application, course selection, document upload (PDF/JPG/PNG ≤5 MB) & per-document verification, workflow Submitted → Under Review → Verified → Approved/Rejected → Enrolled, live status tracker, auto **roll-number** generation, batch/academic-year management, admission & seat-utilisation report, parent linking. |
| **Faculty** | Faculty records, department & subject allocation, daily faculty attendance, leave apply/approve (HOD/Principal), timetable (class & personal), workload balance, performance evaluation, **payroll** generated from attendance + approved leave (LOP, allowances, PF) with printable payslips. |
| **Attendance** | Subject/period-wise registers, manual marking, **time-limited QR attendance** (students scan with phone), biometric records via API, automatic percentages, **shortage alerts** to students & parents, monthly class-wise report. |
| **Fees** | Course/semester/category fee structures, invoice generation per batch, scholarships & concessions, **online payment gateway** (Razorpay; built-in test gateway when no keys), counter collection (cash/DD/NEFT/UPI), downloadable receipts, pending dues, refunds, defaulter report + reminders, financial summary charts. |
| **Examination** | Exam scheduling & timetable, internal/semester/supplementary exams, faculty marks entry with validation & lock, automatic grade / **SGPA / CGPA**, controlled result publication (notifies students & parents), result portal & printable grade sheet, **hall tickets** blocked by attendance shortage or fee dues, revaluation workflow, backlog tracking, pass-% & grade analytics. |
| **Placement** | Student registration & resume, company/recruiter registration with approval, job postings, **automatic eligibility** (CGPA, backlogs, attendance, course), campus drives with online-assessment links, shortlisting/interview/selection pipeline, offer letters, placement statistics. |
| **Dashboard** | Institution-wide analytics (students per department, faculty strength, attendance, fee collection vs pending, exam pass %, placement %, admission pipeline & trend), department-scoped for HODs; personalised dashboards for students, parents, faculty and recruiters. |
| **Administration** | Users & roles, departments, courses, subjects, events, notices, FAQs, website enquiries, audit log, Django admin. |

Notifications: in-app bell (live refresh) + email for every key trigger listed in §9 of the document.

### REST API (for the React Native mobile app)
`/api/` (browsable) — `auth/token/`, `auth/token/refresh/`, `auth/logout/`, `me/`, `students/`, `applications/`, `attendance/`, `invoices/`, `payments/`, `exams/`, `marks/`, `jobs/` (+ `jobs/{id}/apply/`), `leaves/`, `timetable/`, `notifications/`, `courses/`, `subjects/`, `departments/`, `companies/`, `events/`, `notices/`. Every endpoint enforces the same RBAC as the portal.

```bash
curl -X POST http://127.0.0.1:8000/api/auth/token/ -H "Content-Type: application/json" -d '{"username":"student","password":"Gift@2026"}'
curl http://127.0.0.1:8000/api/me/ -H "Authorization: Bearer <access>"
```

---

## Configuration
All settings are in `.env` (see `.env.example`): secret key, debug, hosts, PostgreSQL, SMTP email, Razorpay keys, attendance threshold (default 75%) and QR validity (default 10 min).

## Production
```bash
cp .env.example .env   # set DJANGO_DEBUG=False, a strong DJANGO_SECRET_KEY, hosts, DB_PASSWORD, SMTP, Razorpay
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```
Serve behind HTTPS (Nginx / AWS ALB). Media uploads are stored in the `media` volume (swap to S3 with `django-storages` if needed).

## Tests
```powershell
.\.venv\Scripts\python manage.py test cms
```
Covers registration/login/lockout, RBAC, the full admission → enrollment → online payment → receipt flow, manual + QR attendance with shortage alerts, marks → grades → publish → revaluation, hall-ticket fee check, leave → payroll, placement eligibility & selection, JWT API scoping and all dashboards.

## Notes / not included
* Real-time updates use 30-second polling instead of Django Channels/WebSockets, and emails are sent synchronously instead of via Celery/Redis — both can be added without changing the data model.
* SMS gateway, biometric device drivers and the React Native app are outside this repository; the REST API is ready for them.
* Photos/logos belong to GIFT Autonomous; template assets are licensed with the Stadum template.
