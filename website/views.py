from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cms.models import Company, Course, Department, FacultyProfile, PlacementApplication, Student

from .forms import ContactForm
from .models import FAQ, Event, Notice, Testimonial


def home(request):
    return render(request, "website/home.html", {
        "programs": Course.objects.filter(is_active=True).select_related("department")[:8],
        "events": Event.objects.filter(is_published=True, date__gte=timezone.localdate()).order_by("date")[:3]
        or Event.objects.filter(is_published=True)[:3],
        "notices": Notice.objects.filter(is_published=True)[:3],
        "faqs": FAQ.objects.all()[:5],
        "testimonials": Testimonial.objects.all(),
        "faculty": FacultyProfile.objects.filter(is_public=True).select_related("user", "department")[:4],
        "companies": Company.objects.filter(is_approved=True)[:12],
        "stats": {
            "programs": Course.objects.filter(is_active=True).count(),
            "faculty": FacultyProfile.objects.count(),
            "students": Student.objects.filter(is_active=True).count(),
            "placed": PlacementApplication.objects.filter(stage="selected").count(),
        },
    })


def about(request):
    return render(request, "website/about.html", {
        "faculty": FacultyProfile.objects.filter(is_public=True).select_related("user", "department")[:4],
        "testimonials": Testimonial.objects.all(),
    })


def programs(request):
    qs = Course.objects.filter(is_active=True).select_related("department")
    level = request.GET.get("level", "")
    if level:
        qs = qs.filter(level=level)
    return render(request, "website/programs.html", {"programs": qs, "level": level, "levels": Course.Level.choices})


def program_detail(request, slug):
    course = get_object_or_404(Course.objects.select_related("department"), slug=slug, is_active=True)
    return render(request, "website/program_detail.html", {
        "course": course,
        "subjects": course.subjects.order_by("semester", "code"),
        "fees": course.fee_structures.filter(category="GEN").order_by("semester")[:8],
        "others": Course.objects.filter(is_active=True).exclude(pk=course.pk)[:5],
    })


def departments(request):
    return render(request, "website/departments.html", {
        "departments": Department.objects.annotate(n_courses=Count("courses"), n_faculty=Count("faculty")),
    })


def faculty_list(request):
    qs = FacultyProfile.objects.filter(is_public=True).select_related("user", "department")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(department__name__icontains=q)
                       | Q(specialization__icontains=q))
    return render(request, "website/faculty.html", {"faculty": qs, "q": q})


def faculty_detail(request, pk):
    prof = get_object_or_404(FacultyProfile.objects.select_related("user", "department"), pk=pk, is_public=True)
    return render(request, "website/faculty_detail.html", {"prof": prof, "subjects": prof.user.subjects.select_related("course")})


def events(request):
    page = Paginator(Event.objects.filter(is_published=True), 6).get_page(request.GET.get("page"))
    return render(request, "website/events.html", {"page": page})


def event_detail(request, slug):
    event = get_object_or_404(Event, slug=slug, is_published=True)
    return render(request, "website/event_detail.html", {"event": event, "others": Event.objects.filter(is_published=True).exclude(pk=event.pk)[:3]})


def notices(request):
    qs = Notice.objects.filter(is_published=True)
    cat = request.GET.get("category", "")
    if cat:
        qs = qs.filter(category=cat)
    page = Paginator(qs, 6).get_page(request.GET.get("page"))
    return render(request, "website/notices.html", {"page": page, "category": cat, "categories": Notice.CATEGORIES,
                                                    "recent": Notice.objects.filter(is_published=True)[:4]})


def notice_detail(request, slug):
    notice = get_object_or_404(Notice, slug=slug, is_published=True)
    return render(request, "website/notice_detail.html", {"notice": notice, "recent": Notice.objects.filter(is_published=True).exclude(pk=notice.pk)[:4],
                                                          "categories": Notice.CATEGORIES})


CAMPUS_GALLERY = [
    ("brand/campus1.jpg", "Main Campus", "A green, eco-friendly campus on the outskirts of Bhubaneswar."),
    ("brand/hero-gate.jpg", "Academic Blocks", "500 Cr+ invested in new and refurbished buildings and facilities."),
    ("brand/hero-students.jpg", "Campus Events", "Cultural fests, tech fests and seminars all year round."),
    ("brand/gift-a1.jpg", "Hybrid Solar Car", "Built by students and inaugurated by the Vice Chairman."),
    ("brand/gift-a2.jpg", "Hackathon Winners", "First prize with a cash award of Rs. One Lakh at a national hackathon."),
    ("brand/gift-a3.jpg", "National Conferences", "Awards at the 33rd Convention of Mechanical Engineers, Udaipur."),
    ("brand/gift-a4.jpg", "Graced by the President of India", "Technical paper presentation by GIFT students."),
    ("brand/gift-a5.jpg", "Robotics Champions", "GIFT teams won the 2nd and 3rd prizes at ROBOFEST 2K17."),
    ("brand/youth-parliament.jpg", "Youth Parliament", "Leadership, civic awareness and democratic engagement."),
]


def campus(request):
    return render(request, "website/campus.html", {"gallery": CAMPUS_GALLERY})


def placements(request):
    selected = PlacementApplication.objects.filter(stage="selected").select_related("student__user", "job__company")
    return render(request, "website/placements.html", {"companies": Company.objects.filter(is_approved=True), "selected": selected[:12],
                                                       "count": selected.count()})


def admission(request):
    return render(request, "website/admission.html", {"programs": Course.objects.filter(is_active=True), "faqs": FAQ.objects.all()[:6]})


def faq(request):
    return render(request, "website/faq.html", {"faqs": FAQ.objects.all()})


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Thank you! Your message has been received. Our team will contact you shortly.")
        return redirect("website:contact")
    return render(request, "website/contact.html", {"form": form})


def search(request):
    q = request.GET.get("q", "").strip()
    results = {}
    if q:
        results = {
            "Programs": Course.objects.filter(Q(name__icontains=q) | Q(code__icontains=q), is_active=True)[:10],
            "Notices": Notice.objects.filter(title__icontains=q, is_published=True)[:10],
            "Events": Event.objects.filter(title__icontains=q, is_published=True)[:10],
        }
    return render(request, "website/search.html", {"q": q, "results": results})


def error_404(request, exception=None):
    return render(request, "website/error.html", {"code": 404, "title": "Page not found"}, status=404)


def error_403(request, exception=None):
    return render(request, "website/error.html", {"code": 403, "title": "Access denied",
                                                  "text": "You do not have permission to view this page."}, status=403)
