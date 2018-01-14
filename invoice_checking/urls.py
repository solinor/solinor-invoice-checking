from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
from django.urls import path
from django.views.generic.base import RedirectView

import flex_hours.views
import invoices.views

admin.autodiscover()

urlpatterns = [
    path("projects", invoices.views.projects_list, name="projects_list"),
    path("project/<uuid:project_id>", invoices.views.project_details, name="project"),
    path("project/<uuid:project_id>/charts", invoices.views.project_charts, name="project_charts"),
    path("invoice/<uuid:invoice_id>/hours", invoices.views.invoice_hours, name="invoice_hours"),
    path("invoice/<uuid:invoice_id>/charts", invoices.views.invoice_charts, name="invoice_charts"),
    path("invoice/<uuid:invoice_id>/pdf/<slug:pdf_type>", invoices.views.get_pdf, name="get_pdf"),
    path("invoice/<uuid:invoice_id>/xls/<slug:xls_type>", invoices.views.get_xls, name="get_xls"),
    path("invoice/<uuid:invoice_id>", invoices.views.invoice_page, name="invoice"),
    path("amazon_invoice/<int:linked_account_id>/<int:year>/<int:month>", invoices.views.amazon_invoice, name="amazon_invoice"),
    path("amazon", invoices.views.amazon_overview, name="amazon_overview"),
    path("hours", invoices.views.hours_list, name="hours_list"),
    path("hours/charts", invoices.views.hours_charts, name="hours_charts"),
    path("people", invoices.views.people_list, name="people"),
    path("people/hourmarkings", invoices.views.people_hourmarkings, name="people_hourmarkings"),
    path("people/charts", invoices.views.people_charts, name="people_charts"),
    path("person/<uuid:user_guid>/<int:year>/<int:month>", invoices.views.person_details_month, name="person"),
    path("person/<uuid:user_guid>", invoices.views.person_details, name="person_details"),
    path("person/<uuid:user_guid>/flexhours", flex_hours.views.person_flex_hours, name="person_flex_hours"),
    path("your/flexhours", flex_hours.views.your_flex_hours, name="your_flex_hours"),
    path("queue_update", invoices.views.queue_update, name="queue_update"),
    path("queue_slack_notification", invoices.views.queue_slack_notification, name="queue_slack_notification"),
    url(r"^accounts/profile/$", RedirectView.as_view(pattern_name="frontpage", permanent=False)),
    url(r"^accounts/", include("googleauth.urls")),
    path("", invoices.views.frontpage, name="frontpage"),
    url(r"^admin/", admin.site.urls),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        url(r"^__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns
