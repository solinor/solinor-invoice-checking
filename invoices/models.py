from __future__ import unicode_literals

import uuid
from django.db import models
from django.contrib.auth.models import User

class HourEntry(models.Model):
    date = models.DateField()
    year = models.IntegerField()
    month = models.IntegerField()

    user_id = models.IntegerField()
    user_name = models.CharField(max_length=100)
    client = models.CharField(max_length=100)
    project = models.CharField(max_length=100)
    incurred_hours = models.FloatField()
    incurred_money = models.FloatField()
    category = models.CharField(max_length=100)
    notes = models.CharField(max_length=250)
    entry_type = models.CharField(max_length=100)
    discipline = models.CharField(max_length=100)
    role = models.CharField(max_length=100)
    bill_rate = models.FloatField()
    leave_type = models.CharField(max_length=100)
    phase_name = models.CharField(max_length=100)
    billable = models.BooleanField(blank=True)
    approved = models.BooleanField(blank=True)

class Invoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    year = models.IntegerField()
    month = models.IntegerField()
    client = models.CharField(max_length=100)
    project = models.CharField(max_length=100)

    class Meta:
        unique_together = ("year", "month", "client", "project")
        ordering = ("year", "month", "client", "project")


class Comments(models.Model):
    invoice = models.ForeignKey("Invoice")
    timestamp = models.DateTimeField(auto_now_add=True)
    comments = models.TextField(null=True, blank=True)
    checked = models.NullBooleanField(blank=True, null=True)
    checked_non_billable_ok = models.NullBooleanField(blank=True, null=True)
    checked_bill_rates_ok = models.NullBooleanField(blank=True, null=True)
    checked_phases_ok = models.NullBooleanField(blank=True, null=True)
    user = models.TextField(max_length=100, null=True, blank=True)

    class Meta:
        get_latest_by = "timestamp"
