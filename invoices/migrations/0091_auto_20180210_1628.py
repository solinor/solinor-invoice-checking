# Generated by Django 2.0 on 2018-02-10 14:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0090_auto_20180210_1625'),
    ]

    operations = [
        migrations.AlterField(
            model_name='amazoninvoicerow',
            name='billing_period_end',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='amazoninvoicerow',
            name='billing_period_start',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
