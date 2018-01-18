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
    path("projects/<uuid:project_id>", invoices.views.project_details, name="project"),
    path("projects/<uuid:project_id>/charts", invoices.views.project_charts, name="project_charts"),
    path("invoices/<uuid:invoice_id>", invoices.views.invoice_page, name="invoice"),
    path("invoices/<uuid:invoice_id>/hours", invoices.views.invoice_hours, name="invoice_hours"),
    path("invoices/<uuid:invoice_id>/charts", invoices.views.invoice_charts, name="invoice_charts"),
    path("invoices/<uuid:invoice_id>/export/pdf/<slug:pdf_type>", invoices.views.get_invoice_pdf, name="get_invoice_pdf"),
    path("invoices/<uuid:invoice_id>/export/xls/<slug:xls_type>", invoices.views.get_invoice_xls, name="get_invoice_xls"),
    path("invoices/amazon/<int:linked_account_id>/<int:year>/<int:month>", invoices.views.amazon_invoice, name="amazon_invoice"),
    path("invoices/amazon", invoices.views.amazon_overview, name="amazon_overview"),
    path("hours/browser", invoices.views.hours_browser, name="hours_browser"),
    path("hours/charts", invoices.views.hours_charts, name="hours_charts"),
    path("hours/overview", invoices.views.hours_overview, name="hours_overview"),
    path("hours/sickleaves", invoices.views.hours_sickleaves, name="hours_sickleaves"),
    path("users", invoices.views.users_list, name="users_list"),
    path("users/charts", invoices.views.users_charts, name="users_charts"),
    path("users/<uuid:user_guid>", invoices.views.person_details, name="person_details"),
    path("users/<uuid:user_guid>/<int:year>/<int:month>", invoices.views.person_details_month, name="person_month"),
    path("users/<uuid:user_guid>/flexhours", flex_hours.views.person_flex_hours, name="person_flex_hours"),
    path("you/flexhours", flex_hours.views.your_flex_hours, name="your_flex_hours"),
    path("you/flexhours/json", flex_hours.views.your_flex_hours_json, name="your_flex_hours_json"),

    path("queue_update", invoices.views.queue_update, name="queue_update"),
    path("queue_slack_notification", invoices.views.queue_slack_notification, name="queue_slack_notification"),

    url(r"^accounts/profile/$", RedirectView.as_view(pattern_name="frontpage", permanent=False)),
    url(r"^accounts/", include("googleauth.urls")),
    path("", invoices.views.frontpage, name="frontpage"),
    url(r"^admin/", admin.site.urls),

    # Deprecated paths
    path("project/<uuid:project_id>", RedirectView.as_view(pattern_name="project")),
    path("project/<uuid:project_id>/charts", RedirectView.as_view(pattern_name="project_charts")),
    path("invoice/<uuid:invoice_id>/hours", RedirectView.as_view(pattern_name="invoice_hours")),
    path("invoice/<uuid:invoice_id>/charts", RedirectView.as_view(pattern_name="invoice_charts")),
    path("invoice/<uuid:invoice_id>/pdf/<slug:pdf_type>", RedirectView.as_view(pattern_name="get_invoice_pdf")),
    path("invoice/<uuid:invoice_id>/xls/<slug:xls_type>", RedirectView.as_view(pattern_name="get_invoice_xls")),
    path("invoice/<uuid:invoice_id>", RedirectView.as_view(pattern_name="invoice")),
    path("amazon_invoice/<int:linked_account_id>/<int:year>/<int:month>", RedirectView.as_view(pattern_name="amazon_invoice")),
    path("amazon", RedirectView.as_view(pattern_name="amazon_overview")),
    path("hours", RedirectView.as_view(pattern_name="hours_browser")),
    path("hours/charts", RedirectView.as_view(pattern_name="hours_charts")),
    path("people", RedirectView.as_view(pattern_name="people")),
    path("people/hourmarkings", RedirectView.as_view(pattern_name="hours_overview")),
    path("people/charts", RedirectView.as_view(pattern_name="users_charts")),
    path("person/<uuid:user_guid>/<int:year>/<int:month>", RedirectView.as_view(pattern_name="person_month")),
    path("person/<uuid:user_guid>", RedirectView.as_view(pattern_name="person_details")),
    path("person/<uuid:user_guid>/flexhours", RedirectView.as_view(pattern_name="person_flex_hours")),
    path("your/flexhours", RedirectView.as_view(pattern_name="your_flex_hours")),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        url(r"^__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns
