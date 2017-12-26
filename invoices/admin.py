from django.contrib import admin

from invoices.models import AuthToken, FeetUser, InvoiceFixedEntry, Project, ProjectFixedEntry, SlackChannel


class DeleteNotAllowedModelAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


class AuthTokenAdmin(admin.ModelAdmin):
    pass


admin.site.register(AuthToken, AuthTokenAdmin)


class ProjectFixedEntryAdmin(admin.ModelAdmin):
    pass


admin.site.register(ProjectFixedEntry, ProjectFixedEntryAdmin)


class InvoiceFixedEntryAdmin(admin.ModelAdmin):
    pass


admin.site.register(InvoiceFixedEntry, InvoiceFixedEntryAdmin)


class SlackChannelAdmin(DeleteNotAllowedModelAdmin):
    list_display = ("channel_id", "name")
    search_fields = ("name",)


admin.site.register(SlackChannel, SlackChannelAdmin)


class ProjectAdmin(DeleteNotAllowedModelAdmin):
    fields = ("slack_channel", "amazon_account")
    list_display = ("client", "name", "slack_channel")
    search_fields = ("client", "name")


admin.site.register(Project, ProjectAdmin)


class UserAdmin(DeleteNotAllowedModelAdmin):
    fields = ("amazon_account",)
    list_display = ("first_name", "last_name", "email")
    search_fields = ("first_name", "last_name", "email")


admin.site.register(FeetUser, UserAdmin)
