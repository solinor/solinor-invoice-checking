# Generated by Django 2.0 on 2018-02-10 13:30

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0085_auto_20180210_1453'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hourentry',
            name='invoice',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='invoices.Invoice'),
        ),
    ]
