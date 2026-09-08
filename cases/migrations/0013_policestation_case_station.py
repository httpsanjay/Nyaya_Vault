from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0012_case_police_station"),
    ]

    operations = [
        migrations.CreateModel(
            name="PoliceStation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=150, unique=True)),
                ("code", models.CharField(max_length=50, unique=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="case",
            name="station",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cases",
                to="cases.policestation",
            ),
        ),
    ]
