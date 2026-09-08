from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_alter_user_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="police_station",
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
