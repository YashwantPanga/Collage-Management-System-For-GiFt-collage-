from django.contrib import admin

from .models import FAQ, ContactMessage, Event, Notice, Testimonial

admin.site.register([Event, Notice, ContactMessage, FAQ, Testimonial])
