from django.conf.urls import include, url

from django.contrib import admin

admin.autodiscover()
import invoices.views
import googleauth
from django.views.generic.base import RedirectView

urlpatterns = [
    url(r'^invoice/(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})/(?P<invoice>.+)/pdf/(?P<pdf_type>.+)$', invoices.views.get_pdf, name="get_pdf"),
    url(r'^invoice/(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})/(?P<invoice>.+)$', invoices.views.invoice_page, name="invoice"),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^accounts/profile/$', RedirectView.as_view(pattern_name='frontpage', permanent=False)),
    url(r'^accounts/', include('googleauth.urls')),
    url(r'^$', invoices.views.frontpage, name="frontpage"),
]
