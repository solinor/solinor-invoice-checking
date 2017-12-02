# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

from invoices.models import HourEntry, FeetUser

class WorkContract(models.Model):
    user = models.ForeignKey(FeetUser, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    flex_enabled = models.BooleanField(blank=True, default=True)
    worktime_percent = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ("start_date", "user")

    def __unicode__(self):
        return u"%s - %s - %s - %s - %s%%" % (self.user, self.start_date, self.end_date, self.flex_enabled, self.worktime_percent)

    def __str__(self):
        return u"%s - %s - %s - %s - %s%%" % (self.user, self.start_date, self.end_date, self.flex_enabled, self.worktime_percent)


class FlexTimeCorrection(models.Model):
    user = models.ForeignKey(FeetUser, on_delete=models.CASCADE)
    date = models.DateField()
    adjust_by = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    set_to = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    def __unicode__(self):
        return u"%s - %s: adjust by %s or set to %s" % (self.user, self.date, self.adjust_by, self.set_to)

    def __str__(self):
        return u"%s - %s: adjust by %s or set to %s" % (self.user, self.date, self.adjust_by, self.set_to)

    class Meta:
        ordering = ("date", "user",)


class PublicHoliday(models.Model):
    name = models.CharField(max_length=100)
    date = models.DateField()

    def __unicode__(self):
        return u"%s - %s" % (self.date, self.name)

    def __str__(self):
        return u"%s - %s" % (self.date, self.name)

    class Meta:
        ordering = ("date", )
