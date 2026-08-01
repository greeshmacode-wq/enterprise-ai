# Manually created migration to add role field to User
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="role",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("admin", "Admin"),
                    ("manager", "Manager"),
                    ("employee", "Employee"),
                ],
                default="employee",
            ),
        ),
    ]