# Generated by Django 2.0 on 2018-02-02 08:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0067_hourentrychecksum'),
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(max_length=50)),
                ('succeeded', models.BooleanField(default=False)),
                ('message', models.TextField()),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ('-timestamp',),
            },
        ),
    ]
