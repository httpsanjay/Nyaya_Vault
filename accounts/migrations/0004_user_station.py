from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_police_station"),
        ("cases", "0013_policestation_case_station"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="station",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="cases.policestation",
            ),
        ),
    ]
