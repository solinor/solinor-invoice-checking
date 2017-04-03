from django.conf.urls import include, url

from django.contrib import admin
admin.autodiscover()
import invoices.views
import googleauth

# Examples:
# url(r'^$', 'invoice_checking.views.home', name='home'),
# url(r'^blog/', include('blog.urls')),

urlpatterns = [
    url(r'^invoice/(?P<year>[0-9]{4})/(?P<month>[0-9]{1,2})/(?P<invoice>.+)', invoices.views.invoice_page, name="invoice"),
    url(r'^admin/', include(admin.site.urls)),
    url(r'^accounts/', include('googleauth.urls')),
    url(r'^$', invoices.views.frontpage),
]
