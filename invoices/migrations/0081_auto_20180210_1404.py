# Generated by Django 2.0 on 2018-02-10 12:04

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0080_auto_20180210_1404'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='invoice',
            name='month',
        ),
        migrations.RemoveField(
            model_name='invoice',
            name='year',
        ),
    ]
