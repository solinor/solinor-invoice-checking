# Generated by Django 2.0 on 2018-02-11 09:36

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0092_auto_20180210_1641'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='hourentry',
            name='project_m',
        ),
    ]
