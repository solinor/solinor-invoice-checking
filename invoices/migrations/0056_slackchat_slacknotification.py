# -*- coding: utf-8 -*-
# Generated by Django 1.11.1 on 2017-05-20 19:13
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0055_project_admin_users'),
    ]

    operations = [
        migrations.CreateModel(
            name='SlackChat',
            fields=[
                ('chat_id', models.CharField(editable=False, max_length=50, primary_key=True, serialize=False)),
                ('members', models.ManyToManyField(to='invoices.FeetUser')),
            ],
        ),
        migrations.CreateModel(
            name='SlackNotification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField()),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='invoices.FeetUser')),
            ],
        ),
    ]
