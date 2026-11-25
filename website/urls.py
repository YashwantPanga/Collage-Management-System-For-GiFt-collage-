from django.urls import path

from . import views

app_name = "website"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("programs/", views.programs, name="programs"),
    path("programs/<slug:slug>/", views.program_detail, name="program_detail"),
    path("departments/", views.departments, name="departments"),
    path("faculty/", views.faculty_list, name="faculty"),
    path("faculty/<int:pk>/", views.faculty_detail, name="faculty_detail"),
    path("events/", views.events, name="events"),
    path("events/<slug:slug>/", views.event_detail, name="event_detail"),
    path("news/", views.notices, name="notices"),
    path("news/<slug:slug>/", views.notice_detail, name="notice_detail"),
    path("campus-life/", views.campus, name="campus"),
    path("placements/", views.placements, name="placements"),
    path("admission/", views.admission, name="admission"),
    path("faq/", views.faq, name="faq"),
    path("contact/", views.contact, name="contact"),
    path("search/", views.search, name="search"),
]
