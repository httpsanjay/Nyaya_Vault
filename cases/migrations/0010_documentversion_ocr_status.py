from django.db import migrations, models


def initialize_ocr_status(apps, schema_editor):
    document_version = apps.get_model("cases", "DocumentVersion")
    document_version.objects.filter(
        extracted_text__gt=""
    ).update(ocr_status="COMPLETED")


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0009_alter_documentversion_file"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentversion",
            name="ocr_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("PROCESSING", "Processing"),
                    ("COMPLETED", "Completed"),
                    ("FAILED", "Failed"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.RunPython(
            initialize_ocr_status,
            migrations.RunPython.noop,
        ),
    ]
