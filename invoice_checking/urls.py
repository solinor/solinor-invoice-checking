from django.conf.urls import include, url
from django.contrib import admin
from django.views.generic.base import RedirectView
from django.conf import settings

import invoices.views


admin.autodiscover()

urlpatterns = [
    url(r'^customer/(?P<auth_token>[0-9A-Fa-f-\.]+)$', invoices.views.customer_view, name='customer'),
    url(r'^customer/(?P<auth_token>[0-9A-Fa-f-\.]+)/hours/(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})$', invoices.views.customer_view_hours, name='customer_hours'),
    url(r'^customer/(?P<auth_token>[0-9A-Fa-f-\.]+)/invoice/(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})$', invoices.views.customer_view_invoice, name='customer_invoice'),

    url(r'^projects$', invoices.views.projects_list, name='projects_list'),
    url(r'^project/(?P<project_id>[0-9A-Fa-f-]+)$', invoices.views.project_details, name='project'),
    url(r'^project/(?P<project_id>[0-9A-Fa-f-]+)/charts$', invoices.views.project_charts, name='project_charts'),
    url(r'^invoice/(?P<invoice_id>[0-9A-Fa-f-]+)/hours$', invoices.views.invoice_hours, name='invoice_hours'),
    url(r'^invoice/(?P<invoice_id>[0-9A-Fa-f-]+)/charts$', invoices.views.invoice_charts, name='invoice_charts'),
    url(r'^invoice/(?P<invoice_id>[0-9A-Fa-f-]+)/pdf/(?P<pdf_type>.+)$', invoices.views.get_pdf, name="get_pdf"),
    url(r'^invoice/(?P<invoice_id>[0-9A-Fa-f-]+)$', invoices.views.invoice_page, name="invoice"),
    url(r'^weekly_report/(?P<weekly_report_id>[0-9A-Fa-f-]+)$', invoices.views.weekly_report_page, name="weekly_report"),
    url(r'^amazon_invoice/(?P<linked_account_id>[0-9A-Fa-f-]+)/(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})$', invoices.views.amazon_invoice, name="amazon_invoice"),
    url(r'^amazon$', invoices.views.amazon_overview, name="amazon_overview"),
    url(r'^hours$', invoices.views.hours_list, name="hours_list"),
    url(r'^hours/charts$', invoices.views.hours_charts, name="hours_charts"),
    url(r'^people$', invoices.views.people_list, name='people'),
    url(r'^people/hourmarkings$', invoices.views.people_hourmarkings, name='people_hourmarkings'),
    url(r'^people/charts$', invoices.views.people_charts, name='people_charts'),
    url(r'^person/(?P<user_guid>[0-9A-Fa-f-]+)/(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})', invoices.views.person_details_month, name='person'),
    #url(r'^person/(?P<user_guid>[0-9A-Fa-f-]+)/(?P<year>[0-9]{4})/(?P<week>[0-9]{1,2})',invoices.views.person_details_week, name='person'),
    url(r'^person/(?P<user_guid>[0-9A-Fa-f-]+)', invoices.views.person_details, name='person_details'),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^queue_update$', invoices.views.queue_update, name="queue_update"),
    url(r'^accounts/profile/$', RedirectView.as_view(pattern_name='frontpage', permanent=False)),
    url(r'^accounts/', include('googleauth.urls')),
    url(r'^$', invoices.views.frontpage, name="frontpage"),
    url(r'^admin/', admin.site.urls),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
