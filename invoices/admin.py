from django.contrib import admin
from invoices.models import AuthToken, ProjectFixedEntry, InvoiceFixedEntry, SlackChannel

class AuthTokenAdmin(admin.ModelAdmin):
    pass
admin.site.register(AuthToken, AuthTokenAdmin)


class ProjectFixedEntryAdmin(admin.ModelAdmin):
    pass
admin.site.register(ProjectFixedEntry, ProjectFixedEntryAdmin)


class InvoiceFixedEntryAdmin(admin.ModelAdmin):
    pass
admin.site.register(InvoiceFixedEntry, InvoiceFixedEntryAdmin)


class SlackChannelAdmin(admin.ModelAdmin):
    pass

admin.site.register(SlackChannel, SlackChannelAdmin)
