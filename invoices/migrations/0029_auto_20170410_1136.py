# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2017-04-10 11:36
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0028_auto_20170409_2006'),
    ]

    operations = [
        migrations.AlterField(
            model_name='comments',
            name='checked',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='comments',
            name='checked_bill_rates_ok',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='comments',
            name='checked_changes_last_month',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='comments',
            name='checked_non_billable_ok',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='comments',
            name='checked_phases_ok',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='bill_rate_avg',
            field=models.FloatField(default=0),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='billable_incorrect_price_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='empty_descriptions_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='has_comments',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='incorrect_entries_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='is_approved',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='non_billable_hours_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='non_phase_specific_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='not_approved_hours_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='total_hours',
            field=models.FloatField(default=0),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='total_money',
            field=models.FloatField(default=0),
        ),
    ]
