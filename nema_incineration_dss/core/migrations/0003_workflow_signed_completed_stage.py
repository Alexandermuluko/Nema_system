from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0002_dataset_validation_status_prediction_evaluation_and_more")]

    operations = [
        migrations.AlterField(
            model_name="workflow",
            name="completed_stage",
            field=models.SmallIntegerField(default=-1),
        ),
    ]
