# Generated by Django 5.1.1 on 2024-11-10 03:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('room', '0018_booking_message'),
    ]

    operations = [
        migrations.AddField(
            model_name='room',
            name='maximum_capacity',
            field=models.IntegerField(blank=True, default=0),
        ),
    ]