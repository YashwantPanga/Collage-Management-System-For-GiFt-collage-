from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "GIFT Autonomous — Administration"
admin.site.site_title = "GIFT CMS Admin"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("portal/", include("cms.urls")),
    path("api/", include("api.urls")),
    path("", include("website.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "website.views.error_404"
handler403 = "website.views.error_403"
