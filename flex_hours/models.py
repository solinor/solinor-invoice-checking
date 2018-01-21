# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.exceptions import ValidationError
from django.db import models

from invoices.models import TenkfUser


def validate_percent_field(value):
    if value is None:
        return
    if 0 > value > 100:
        raise ValidationError(
            _('%(value)s is not between 0-100'),
            params={'value': value},
        )


class WorkContract(models.Model):
    user = models.ForeignKey(TenkfUser, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    flex_enabled = models.BooleanField(blank=True, default=True)
    worktime_percent = models.IntegerField(default=100, validators=(validate_percent_field,))

    class Meta:
        ordering = ("start_date", "user")

    @property
    def workday_length(self):
        return float(self.worktime_percent / 100) * 7.5

    def __str__(self):
        return u"%s - %s - %s - %s - %s%%" % (self.user, self.start_date, self.end_date, self.flex_enabled, self.worktime_percent)


class FlexTimeCorrection(models.Model):
    user = models.ForeignKey(TenkfUser, on_delete=models.CASCADE)
    date = models.DateField()
    adjust_by = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    set_to = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    def __str__(self):
        message = "%s - %s: " % (self.user, self.date)
        if self.adjust_by:
            message += "adjust by %sh" % self.adjust_by
        if self.set_to is not None:
            if self.adjust_by:
                message += " and"
            message += "set to %sh" % self.set_to
        return message

    class Meta:
        ordering = ("date", "user",)


class PublicHoliday(models.Model):
    name = models.CharField(max_length=100)
    date = models.DateField()

    def __str__(self):
        return u"%s - %s" % (self.date, self.name)

    class Meta:
        ordering = ("date", )
