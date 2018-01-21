# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from reversion.admin import VersionAdmin

from flex_hours.models import FlexTimeCorrection, PublicHoliday, WorkContract


class WorkContractAdmin(VersionAdmin):
    fields = ("user", "start_date", "end_date", "flex_enabled", "worktime_percent")
    list_display = ("user", "start_date", "end_date", "flex_enabled", "worktime_percent")
    search_fields = ("user__first_name", "user__last_name", "user__email")


admin.site.register(WorkContract, WorkContractAdmin)


class FlexTimeCorrectionAdmin(VersionAdmin):
    fields = ("user", "date", "adjust_by", "set_to")
    list_display = ("user", "date", "adjust_by", "set_to")
    search_fields = ("user__first_name", "user__last_name", "user__email")


admin.site.register(FlexTimeCorrection, FlexTimeCorrectionAdmin)


class PublicHolidayAdmin(VersionAdmin):
    fields = ("name", "date")
    list_display = ("name", "date")
    search_fields = ("name", "date")


admin.site.register(PublicHoliday, PublicHolidayAdmin)
