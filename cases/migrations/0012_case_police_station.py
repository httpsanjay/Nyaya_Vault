from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0011_documentversion_ocr_error"),
    ]

    operations = [
        migrations.AddField(
            model_name="case",
            name="police_station",
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
