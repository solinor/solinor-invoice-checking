# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2017-05-12 21:04
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0047_amazoninvoicerow_currency'),
    ]

    operations = [
        migrations.AddField(
            model_name='feetuser',
            name='amazon_account',
            field=models.ManyToManyField(blank=True, to='invoices.AmazonLinkedAccount'),
        ),
    ]
