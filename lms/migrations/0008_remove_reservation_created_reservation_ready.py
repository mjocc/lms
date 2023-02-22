# Generated by Django 4.1.1 on 2023-01-27 17:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lms", "0007_reservation_copy"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="reservation",
            name="created",
        ),
        migrations.AddField(
            model_name="reservation",
            name="ready",
            field=models.DateField(
                blank=True,
                help_text="date the reservation was ready for collection",
                null=True,
            ),
        ),
    ]
