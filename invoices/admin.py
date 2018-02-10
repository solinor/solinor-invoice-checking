from django.contrib import admin

from invoices.models import InvoiceFixedEntry, Project, ProjectFixedEntry, SlackChannel, TenkfUser


class DeleteNotAllowedModelAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


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
    def get_client_name(self, obj):
        return obj.client_m.name
    get_client_name.admin_order_field = "client"
    get_client_name.short_description = "Client"

    fields = ("slack_channel", "amazon_account")
    list_display = ("get_client_name", "name", "slack_channel")
    search_fields = ("get_client_name", "name")


admin.site.register(Project, ProjectAdmin)


class UserAdmin(DeleteNotAllowedModelAdmin):
    fields = ("amazon_account",)
    list_display = ("first_name", "last_name", "email")
    search_fields = ("first_name", "last_name", "email")


admin.site.register(TenkfUser, UserAdmin)
