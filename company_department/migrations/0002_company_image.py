# Generated by Django 5.0.4 on 2024-08-14 07:11

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("company_department", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="image",
            field=models.ImageField(
                blank=True, default="", upload_to="company/images/"
            ),
        ),
    ]
