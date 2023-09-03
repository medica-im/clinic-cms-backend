"""backend URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path, re_path

from wagtail.admin import urls as wagtailadmin_urls
from wagtail import urls as wagtail_urls
from wagtail.documents import urls as wagtaildocs_urls
from cms.api import api_router
from django.views.generic import TemplateView
from accounts.reset import PasswordResetConfirmRedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/accounts/', include('accounts.urls', namespace='accounts')),
    path('addressbook/', include('addressbook.urls', namespace='addressbook')),
    path('api/v1/addressbook/', include('addressbook.api.urls', namespace='addressbook_api')),
    path('api/v1/facility/', include('facility.urls', namespace='facility')),
    path('api/v1/opengraph/', include('opengraph.urls', namespace='opengraph')),
    path('api/v1/workforce/', include('workforce.urls', namespace='workforce')),
    path('form/', include('contact.urls', namespace='contact')),
    path('cms/api/v2/', api_router.urls),
    path('cms/', include(wagtailadmin_urls)),
    path('documents/', include(wagtaildocs_urls)),
    path('pages/', include(wagtail_urls)),
    path('verification/', include('verify_email.urls')),
    path('dj-rest-auth/', include('dj_rest_auth.urls')),
    # this url is used to generate email content
    #re_path(
    #    r"^password-reset/confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/$",
    #    TemplateView.as_view(template_name="password_reset_confirm.html"),
    #    name="password_reset_confirm",
    #),
    re_path(
        r"^password-reset/confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,32})/$",
        PasswordResetConfirmRedirectView.as_view(),
        name="password_reset_confirm",
    ),
    re_path(r'^password-reset/confirm/$',
        TemplateView.as_view(template_name="password_reset_confirm.html"),
        name='password-reset-confirm'),
]

# Use static() to add url mappings to serve static files during development (only)
from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)