# Generated by Django 2.0 on 2018-02-11 15:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flex_hours', '0005_auto_20180202_1028'),
    ]

    operations = [
        migrations.CreateModel(
            name='Permission',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'permissions': (('can_see_flex_saldos', 'Can see flex saldos overview'),),
            },
        ),
    ]
