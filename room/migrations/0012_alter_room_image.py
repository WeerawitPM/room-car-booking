# Generated by Django 5.0.4 on 2024-08-14 07:01

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("room", "0011_alter_room_image"),
    ]

    operations = [
        migrations.AlterField(
            model_name="room",
            name="image",
            field=models.ImageField(blank=True, default="", upload_to="room/images/"),
        ),
    ]
