from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Event(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=210, unique=True, blank=True)
    summary = models.CharField(max_length=300)
    body = models.TextField(blank=True)
    image = models.CharField(max_length=255, blank=True, help_text="Static path or URL")
    venue = models.CharField(max_length=150, default="GIFT Campus, Bhubaneswar")
    date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-date"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:200] or "event"
            base, n = self.slug, 1
            while Event.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                n += 1
                self.slug = f"{base}-{n}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("website:event_detail", args=[self.slug])

    def __str__(self):
        return self.title


class Notice(models.Model):
    """News, notices & announcements (rendered with the template's blog layout)."""
    CATEGORIES = [("notice", "Notice"), ("news", "News"), ("achievement", "Achievement"), ("admission", "Admission"), ("placement", "Placement")]
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=210, unique=True, blank=True)
    category = models.CharField(max_length=12, choices=CATEGORIES, default="notice")
    summary = models.CharField(max_length=300)
    body = models.TextField(blank=True)
    image = models.CharField(max_length=255, blank=True)
    author = models.CharField(max_length=100, default="GIFT Autonomous")
    published_on = models.DateField(default=timezone.localdate)
    is_published = models.BooleanField(default=True)
    attachment = models.FileField(upload_to="notices/", blank=True)

    class Meta:
        ordering = ["-published_on", "-id"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:200] or "notice"
            base, n = self.slug, 1
            while Notice.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                n += 1
                self.slug = f"{base}-{n}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("website:notice_detail", args=[self.slug])

    def __str__(self):
        return self.title


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    subject = models.CharField(max_length=150, blank=True)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}: {self.subject}"


class FAQ(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "FAQ"

    def __str__(self):
        return self.question


class Testimonial(models.Model):
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=120, default="Student")
    quote = models.TextField()
    photo = models.CharField(max_length=255, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name
