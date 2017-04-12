from django.contrib import admin
from invoices.models import AuthToken

class AuthTokenAdmin(admin.ModelAdmin):
    pass
admin.site.register(AuthToken, AuthTokenAdmin)
