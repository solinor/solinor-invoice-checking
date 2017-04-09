from django.conf.urls import include, url
from django.contrib import admin
from django.views.generic.base import RedirectView
import invoices.views

admin.autodiscover()

urlpatterns = [
    url(r'^invoice/(?P<invoice>[0-9A-Fa-f-]+)/pdf/(?P<pdf_type>.+)$', invoices.views.get_pdf, name="get_pdf"),
    url(r'^invoice/(?P<invoice>[0-9A-Fa-f-]+)$', invoices.views.invoice_page, name="invoice"),
    url(r'^invoice/(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})/(?P<invoice>[0-9A-Fa-f-]+)$', invoices.views.invoice_page, name="invoice_backward_compatibility"),  # deprecated
    url(r'^people$', invoices.views.people_list, name='people'),
    url(r'^person/(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})/(?P<user_email>.*)', invoices.views.person_details, name='person'),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^queue_update$', invoices.views.queue_update, name="queue_update"),
    url(r'^accounts/profile/$', RedirectView.as_view(pattern_name='frontpage', permanent=False)),
    url(r'^accounts/', include('googleauth.urls')),
    url(r'^$', invoices.views.frontpage, name="frontpage"),
]
