import io

import joblib
import numpy as np
import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from core.ml import clean_dataset, predict_one, read_dataset, train_regressor
from core.models import (
    AuditEvent,
    Dataset,
    MLModel,
    Prediction,
    ProcessingRun,
    UserProfile,
    Workflow,
)


class Command(BaseCommand):
    help = "Train and persist a model/prediction for an officer's active dataset workflow."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--target", required=True)
        parser.add_argument(
            "--algorithm",
            choices=("RANDOM_FOREST", "LINEAR_REGRESSION"),
            default="RANDOM_FOREST",
        )
        parser.add_argument("--features", nargs="*", default=None)

    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError("The requested account does not exist.")
        profile = getattr(user, "profile", None)
        if profile is None or profile.role != UserProfile.ROLE_OFFICER:
            raise CommandError("Training must be run for an Environmental Officer.")

        workflow = Workflow.objects.filter(user=user).first()
        dataset = workflow.dataset if workflow else None
        if dataset is None:
            dataset = Dataset.objects.filter(uploaded_by=user).order_by("-uploaded_at").first()
        if dataset is None or not dataset.file:
            raise CommandError("Upload a dataset before training a model.")

        try:
            frame = read_dataset(dataset.file)
        except Exception as exc:
            raise CommandError(f"Could not read the uploaded dataset: {exc}") from exc

        target = options["target"]
        cleaned = clean_dataset(frame)
        numeric_columns = cleaned.select_dtypes(include=np.number).columns.tolist()
        features = options["features"] or [
            column
            for column in numeric_columns
            if column not in {target, "record_time_unix"}
        ]
        if target not in numeric_columns:
            raise CommandError(
                f"Target '{target}' is not a numeric column in the uploaded dataset."
            )
        features = [
            column
            for column in features
            if column in numeric_columns and column not in {target, "record_time_unix"}
        ]
        if not features:
            raise CommandError("Provide at least one numeric input feature besides the target.")

        try:
            bundle, metrics, evaluation = train_regressor(
                frame, target, features, options["algorithm"]
            )
        except (ValueError, TypeError) as exc:
            raise CommandError(f"Model training could not be completed: {exc}") from exc

        latest = cleaned.iloc[-1].to_dict()
        predicted = predict_one(bundle, latest)
        actual_value = pd.to_numeric(
            pd.Series([latest.get(target)]), errors="coerce"
        ).iloc[0]
        actual = None if pd.isna(actual_value) else float(actual_value)

        dataset.row_count, dataset.column_count = frame.shape
        dataset.columns = [str(column) for column in frame.columns]
        dataset.validation_status = "VALID"
        dataset.save(
            update_fields=[
                "row_count",
                "column_count",
                "columns",
                "validation_status",
            ]
        )

        summary = {
            "rows": len(cleaned),
            "original_records": len(frame),
            "duplicates_removed": int(len(frame) - len(frame.drop_duplicates())),
            "missing_values_handled": int(frame.isna().sum().sum()),
            "source_records_excluded": int(
                frame.attrs.get("source_records_excluded", 0)
            ),
            "selected_features": features,
        }
        processing = workflow.processing_run if workflow else None
        if processing is None:
            processing = ProcessingRun.objects.create(
                dataset=dataset, created_by=user, summary=summary
            )
        else:
            processing.summary = summary
            processing.status = "COMPLETED"
            processing.save(update_fields=["summary", "status"])

        model = MLModel.objects.create(
            name=f"{options['algorithm']} - {target}",
            algorithm=options["algorithm"],
            target_column=target,
            feature_columns=features,
            metrics=metrics,
            created_by=user,
        )
        model_buffer = io.BytesIO()
        joblib.dump(bundle, model_buffer)
        model.model_file.save(
            f"model_{model.pk}.joblib",
            ContentFile(model_buffer.getvalue()),
            save=True,
        )

        prediction_rows = evaluation.to_dict(orient="records")
        for row in prediction_rows:
            row["difference"] = float(row["actual"] - row["predicted"])
        prediction = Prediction.objects.create(
            dataset=dataset,
            processing_run=processing,
            model=model,
            target_column=target,
            predicted_value=predicted,
            actual_value=actual,
            created_by=user,
            evaluation=metrics,
            prediction_rows=prediction_rows,
        )

        if workflow is None:
            workflow = Workflow.objects.create(user=user)
        workflow.dataset = dataset
        workflow.processing_run = processing
        workflow.model = model
        workflow.prediction = prediction
        workflow.visualization = None
        workflow.report = None
        workflow.algorithm = options["algorithm"]
        workflow.selected_target = target
        workflow.selected_features = features
        workflow.completed_stage = max(workflow.completed_stage, 4)
        workflow.visualization_completed = False
        workflow.save()

        AuditEvent.objects.create(
            actor=user,
            action="prediction_completed",
            entity_type="Prediction",
            entity_id=prediction.pk,
            details={
                "dataset_id": dataset.pk,
                "model_id": model.pk,
                "algorithm": options["algorithm"],
                "target": target,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Model saved: {model.name}\n"
                f"Dataset: {dataset.name} ({dataset.row_count:,} source rows)\n"
                f"Features: {', '.join(features)}\n"
                f"MAE: {metrics['MAE']:.6f}\n"
                f"RMSE: {metrics['RMSE']:.6f}\n"
                f"R²: {metrics['R2']:.6f} ({metrics['R2'] * 100:.2f}% variance explained; not classification accuracy)\n"
                f"Training/test rows: {metrics['training_rows']:,}/{metrics['testing_rows']:,}\n"
                f"Latest prediction for {target}: {predicted:.6f}"
            )
        )
