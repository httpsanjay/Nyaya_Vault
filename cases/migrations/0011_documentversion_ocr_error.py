from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0010_documentversion_ocr_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentversion",
            name="ocr_error",
            field=models.TextField(blank=True),
        ),
    ]