# Generated by Django 2.0 on 2018-02-02 08:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flex_hours', '0004_auto_20180121_1648'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='publicholiday',
            name='id',
        ),
        migrations.AddField(
            model_name='publicholiday',
            name='created_at',
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name='publicholiday',
            name='updated_at',
            field=models.DateTimeField(null=True),
        ),
        migrations.AlterField(
            model_name='publicholiday',
            name='date',
            field=models.DateField(primary_key=True, serialize=False),
        ),
    ]
