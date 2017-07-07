# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

from invoices.models import HourEntry, FeetUser

class WorkContract(models.Model):
    user = models.ForeignKey(FeetUser)
    start_date = models.DateField()
    end_date = models.DateField()
    flex_enabled = models.BooleanField(blank=True, default=True)
    worktime_percent = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("start_date", )

    def __unicode__(self):
        return u"%s - %s - %s - %s - %s%%" % (self.user, self.start_date, self.end_date, self.flex_enabled, self.worktime_percent)

class FlexTimeCorrection(models.Model):
    user = models.ForeignKey(FeetUser)
    date = models.DateField()
    adjust_by = models.DecimalField(max_digits=6, decimal_places=2)
    set_to = models.DecimalField(max_digits=6, decimal_places=2)


class PublicHoliday(models.Model):
    name = models.CharField(max_length=100)
    date = models.DateField()
