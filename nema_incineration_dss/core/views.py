import io
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Count
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .access import admin_required, officer_required, has_role
from .forms import (
    LoginForm,
    MAX_UPLOAD_SIZE,
    OfficerUpdateForm,
    UploadDatasetForm,
    PredictionSettingsForm,
    UserCreateForm,
)
from .ml import read_dataset, clean_dataset, train_regressor, predict_one
from .models import (
    Dataset,
    MLModel,
    Prediction,
    ProcessingRun,
    Report,
    UserProfile,
    Visualization,
    Workflow,
    AuditEvent,
)

logger = logging.getLogger(__name__)


def save_chart(fig, prediction_id):
    buffer = io.BytesIO()
    try:
        fig.savefig(buffer, format="png", dpi=150)
    finally:
        plt.close(fig)
    buffer.seek(0)
    key = default_storage.save(
        f"charts/prediction_{prediction_id}/{uuid.uuid4().hex}.png",
        ContentFile(buffer.getvalue()),
    )
    return key


def ensure_profile(user):
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "role": UserProfile.ROLE_ADMIN if user.is_superuser else UserProfile.ROLE_OFFICER
        },
    )
    legacy_roles = {
        "OFFICER": UserProfile.ROLE_OFFICER,
        "ADMIN": UserProfile.ROLE_ADMIN,
    }
    if profile.role in legacy_roles:
        profile.role = legacy_roles[profile.role]
        profile.save(update_fields=["role"])
    return profile

def is_admin(user):
    return has_role(user, UserProfile.ROLE_ADMIN)


def get_workflow(user):
    workflow = Workflow.objects.filter(user=user).first()
    if workflow is None:
        workflow = Workflow.objects.create(user=user, completed_stage=-1)
    return workflow


def record_audit(actor, action, entity_type, entity_id=None, details=None):
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )


def validate_dataset_columns(df):
    mapping_file = settings.BASE_DIR / "config" / "column_mapping.json"
    with mapping_file.open(encoding="utf-8") as source:
        mapping = json.load(source)
    headers = {str(column).strip() for column in df.columns}
    process_tags = set(mapping) - {"record_time"}
    recognized_tags = headers & process_tags
    missing_time = "record_time" not in headers
    if missing_time or len(recognized_tags) < 2:
        missing = ["record_time"] if missing_time else []
        raise ValueError(
            "Dataset must include record_time and at least two configured process-tag columns. "
            f"Recognized process tags: {len(recognized_tags)}."
        )
    return True


def stage_required(stage):
    def decorator(view_func):
        def wrapped(request, *args, **kwargs):
            workflow = get_workflow(request.user)
            if workflow.completed_stage < stage:
                next_stage = workflow.completed_stage + 1
                destinations = {
                    0: ("upload", "Please upload a dataset first."),
                    1: ("data_preview", "Preview and validate your dataset first."),
                    2: ("preprocess", "Prediction is not available yet. Please complete data preprocessing first."),
                    3: ("predict", "Select a model and prediction features first."),
                    4: ("prediction_results", "Complete prediction before continuing."),
                    5: ("visualize", "View the prediction visualization before generating a report."),
                }
                route, message = destinations.get(next_stage, ("dashboard", "Complete the previous workflow step first."))
                messages.warning(request, message)
                return redirect(route)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def home(request):
    return render(request, "login.html", {"form": LoginForm()})


def about(request):
    return render(request, "about.html")


def contact(request):
    return render(request, "contact.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("admin_dashboard" if is_admin(request.user) else "dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
            )
            if user:
                profile = ensure_profile(user)
                selected_role = form.cleaned_data["role"]
                role_matches = profile.role == selected_role
                if role_matches and (
                    not user.is_superuser
                    or selected_role == UserProfile.ROLE_ADMIN
                ):
                    login(request, user)
                    if selected_role == UserProfile.ROLE_OFFICER:
                        get_workflow(user)
                    return redirect(
                        "admin_dashboard"
                        if selected_role == UserProfile.ROLE_ADMIN
                        else "dashboard"
                    )
        messages.error(request, "Invalid username, password, or selected role.")
    return render(request, "login.html", {"form": form})

def logout_view(request):
    logout(request)
    return redirect("login")

@login_required
def profile(request):
    ensure_profile(request.user)
    return render(request, "profile.html", {"profile": request.user.profile})

@login_required
def dashboard(request):
    ensure_profile(request.user)
    if is_admin(request.user):
        return redirect("admin_dashboard")
    workflow = get_workflow(request.user)
    datasets = Dataset.objects.filter(uploaded_by=request.user)
    predictions = Prediction.objects.filter(created_by=request.user)
    reports = Report.objects.filter(generated_by=request.user)
    current_stage = min(workflow.completed_stage + 1, 7)
    current_urls = ["upload", "data_preview", "preprocess", "predict", "prediction_results", "visualize", "reports", "history"]
    workflow_labels = [
        "Upload Dataset", "Data Preview", "Data Preprocessing", "Prediction",
        "Prediction Results", "Visualization", "Report", "History",
    ]
    context = {
        "datasets": datasets.count(),
        "predictions": predictions.count(),
        "reports": reports.count(),
        "alerts": predictions.filter(status="Alert").count(),
        "recent": predictions.select_related("model", "dataset").order_by("-created_at")[:5],
        "latest_prediction": predictions.select_related("model", "dataset").order_by("-created_at").first(),
        "latest_report": reports.order_by("-generated_at").first(),
        "workflow": workflow,
        "current_stage": current_stage,
        "current_url": current_urls[current_stage],
        "workflow_labels": workflow_labels,
        "workflow_step_label": workflow_labels[current_stage],
        "is_admin": is_admin(request.user),
    }
    return render(request, "dashboard.html", context)

@officer_required
def upload_dataset(request):
    if request.method == "POST":
        form = UploadDatasetForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data["file"]
            obj = None
            try:
                if settings.VERCEL and not settings.USE_OBJECT_STORAGE:
                    raise OSError(
                        "Persistent upload storage is not configured. "
                        "Set up Neon Object Storage for this Vercel deployment."
                    )
                obj = Dataset.objects.create(
                    name=f.name, file=f, uploaded_by=request.user
                )
                df = read_dataset(obj.file)
                if len(df.columns) < 2 or len(df) < 5:
                    raise ValueError("Dataset must contain at least two columns and five rows.")
                validate_dataset_columns(df)
                obj.row_count, obj.column_count = df.shape
                obj.columns = [str(c) for c in df.columns]
                preview = df.head(8).copy()
                preview = preview.astype(object).where(pd.notna(preview), None)
                # Datetimes need conversion for JSON.
                for col in preview.columns:
                    preview[col] = preview[col].map(
                        lambda x: x.isoformat() if hasattr(x, "isoformat") else x
                    )
                obj.preview = preview.to_dict(orient="records")
                obj.validation_status = "PENDING"
                excluded_rows = int(df.attrs.get("source_records_excluded", 0))
                obj.preprocessing_summary = {
                    "source_recovered": bool(df.attrs.get("source_recovered", False)),
                    "source_records_excluded": excluded_rows,
                }
                obj.save()
                workflow = get_workflow(request.user)
                workflow.dataset = obj
                workflow.processing_run = None
                workflow.model = None
                workflow.prediction = None
                workflow.visualization = None
                workflow.report = None
                workflow.selected_target = ""
                workflow.selected_features = []
                workflow.completed_stage = 0
                workflow.visualization_completed = False
                workflow.save()
                record_audit(
                    request.user,
                    "dataset_uploaded",
                    "Dataset",
                    obj.id,
                    {"name": obj.name, "rows": obj.row_count, "columns": obj.column_count},
                )
                if excluded_rows:
                    messages.warning(
                        request,
                        f"Dataset uploaded: {obj.name}. "
                        f"{len(df):,} valid records are ready; "
                        f"{excluded_rows:,} malformed records were excluded. "
                        "The original uploaded file is retained unchanged.",
                    )
                else:
                    messages.success(
                        request,
                        f"Dataset uploaded: {obj.name} "
                        f"({len(df):,} records ready for preprocessing).",
                    )
                return redirect("data_preview")
            except Exception as exc:
                logger.exception("Could not process uploaded dataset")
                if obj and obj.file:
                    obj.file.delete(save=False)
                if obj:
                    obj.delete()
                messages.error(request, f"Could not process dataset: {exc}")
    else:
        form = UploadDatasetForm()
    return render(request, "upload.html", {"form": form})


@officer_required
@stage_required(0)
def data_preview(request):
    workflow = get_workflow(request.user)
    dataset = workflow.dataset
    if not dataset or dataset.uploaded_by_id != request.user.id:
        messages.info(request, "Upload your dataset to continue.")
        return redirect("upload")
    try:
        df = read_dataset(dataset.file)
        try:
            validate_dataset_columns(df)
        except ValueError:
            dataset.validation_status = "FAILED"
            dataset.save(update_fields=["validation_status"])
            messages.error(request, "Dataset validation failed. Expected record_time and at least two configured process tags.")
            return redirect("upload")
        dataset.validation_status = "VALID"
        dataset.save(update_fields=["validation_status"])
        workflow.completed_stage = max(workflow.completed_stage, 1)
        workflow.save(update_fields=["completed_stage", "updated_at"])
        rows = df.head(10).copy()
        rows = rows.astype(object).where(pd.notna(rows), "")
        rows = rows.to_dict(orient="records")
        return render(request, "data_preview.html", {
            "dataset": dataset, "rows": rows, "columns": list(df.columns)
        })
    except Exception as exc:
        messages.error(request, f"Could not preview dataset: {exc}")
        return redirect("upload")

@officer_required
@stage_required(1)
def preprocess(request):
    workflow = get_workflow(request.user)
    dataset = workflow.dataset
    if not dataset or dataset.uploaded_by_id != request.user.id:
        messages.info(request, "Upload a dataset first.")
        return redirect("upload")
    try:
        df = read_dataset(dataset.file)
        before = len(df)
        cleaned = clean_dataset(df)
        missing_before = int(df.isna().sum().sum())
        missing_after = int(cleaned.isna().sum().sum())
        duplicates_removed = before - len(df.drop_duplicates())
        outliers_detected = 0
        for column in cleaned.select_dtypes(include=np.number).columns:
            q1, q3 = cleaned[column].quantile([0.25, 0.75])
            spread = q3 - q1
            outliers_detected += int(((cleaned[column] < q1 - 1.5 * spread) | (cleaned[column] > q3 + 1.5 * spread)).sum())
        summary = {
            "rows": len(cleaned),
            "original_records": before,
            "source_records_excluded": int(
                dataset.preprocessing_summary.get("source_records_excluded", 0)
            ),
            "columns": len(cleaned.columns),
            "missing_values_handled": missing_before - missing_after,
            "duplicates_removed": duplicates_removed,
            "outliers_detected": outliers_detected,
            "selected_features": workflow.selected_features,
            "feature_selection": "Selected at prediction settings stage",
            "encoding": "Categorical columns are one-hot encoded during training",
            "scaling": "Numeric features are standardized for the selected model pipeline",
            "steps": {
                "missing_values": {
                    "status": "✓",
                    "detail": f"Completed · {missing_before - missing_after} values handled",
                },
                "duplicates": {
                    "status": "✓",
                    "detail": f"Completed · {duplicates_removed} removed",
                },
                "outliers": {
                    "status": "✓",
                    "detail": f"Completed · {outliers_detected} detected, not removed",
                },
                "scaling": {
                    "status": "Pending",
                    "detail": "Applied in the selected model pipeline during training",
                },
                "feature_selection": {
                    "status": "Pending",
                    "detail": "Choose input features in Prediction Settings",
                },
                "validation": {
                    "status": "✓",
                    "detail": "Completed · configured source columns validated",
                },
            },
        }
        dataset.preprocessing_summary = summary
        dataset.save(update_fields=["preprocessing_summary"])
        processing_run = workflow.processing_run
        if processing_run is None:
            processing_run = ProcessingRun.objects.create(
                dataset=dataset, created_by=request.user, summary=summary
            )
        else:
            processing_run.summary = summary
            processing_run.save(update_fields=["summary"])
        workflow.processing_run = processing_run
        workflow.completed_stage = max(workflow.completed_stage, 2)
        workflow.save(update_fields=["processing_run", "completed_stage", "updated_at"])
        record_audit(
            request.user,
            "dataset_preprocessed",
            "ProcessingRun",
            processing_run.id,
            {"dataset_id": dataset.id, "status": processing_run.status},
        )
        return render(request, "preprocess.html", {"dataset": dataset, "summary": summary, "workflow": workflow})
    except Exception as exc:
        processing_run = workflow.processing_run
        if processing_run is None:
            processing_run = ProcessingRun.objects.create(
                dataset=dataset,
                created_by=request.user,
                status="FAILED",
                summary={"error": str(exc)},
            )
            workflow.processing_run = processing_run
            workflow.save(update_fields=["processing_run", "updated_at"])
        else:
            processing_run.status = "FAILED"
            processing_run.summary = {"error": str(exc)}
            processing_run.save(update_fields=["status", "summary"])
        messages.error(request, f"Preprocessing failed: {exc}")
        return redirect("upload")

@officer_required
@stage_required(2)
def predict_settings(request):
    workflow = get_workflow(request.user)
    dataset = workflow.dataset
    if not dataset or dataset.uploaded_by_id != request.user.id:
        return redirect("upload")
    df = read_dataset(dataset.file)
    cleaned = clean_dataset(df)
    numeric = cleaned.select_dtypes(include=np.number).columns.tolist()
    # Exclude helper timestamp by default, but allow it if the user wants it.
    if "record_time_unix" in numeric:
        numeric.remove("record_time_unix")
    if request.method == "POST":
        form = PredictionSettingsForm(request.POST, columns=numeric)
        if form.is_valid():
            features = [f for f in form.cleaned_data["feature_columns"] if f != form.cleaned_data["target_column"]]
            if not features:
                form.add_error("feature_columns", "Select at least one feature other than the target.")
                return render(request, "predict.html", {"form": form, "dataset": dataset, "numeric": numeric})
            workflow.algorithm = form.cleaned_data["algorithm"]
            workflow.selected_target = form.cleaned_data["target_column"]
            workflow.selected_features = features
            workflow.model = None
            workflow.prediction = None
            workflow.visualization = None
            workflow.report = None
            workflow.completed_stage = 3
            workflow.visualization_completed = False
            workflow.save()
            return redirect("prediction_results")
    else:
        form = PredictionSettingsForm(columns=numeric, initial={
            "algorithm": "RANDOM_FOREST",
            "target_column": numeric[0] if numeric else "",
            "feature_columns": numeric[1:6],
        })
    return render(request, "predict.html", {"form": form, "dataset": dataset, "numeric": numeric, "workflow": workflow})

@officer_required
@stage_required(3)
def prediction_results(request):
    workflow = get_workflow(request.user)
    dataset = workflow.dataset
    if not dataset or dataset.uploaded_by_id != request.user.id or not workflow.selected_target or not workflow.selected_features:
        messages.warning(request, "Select a model and features before running a prediction.")
        return redirect("predict")
    settings_data = {
        "algorithm": workflow.algorithm,
        "target": workflow.selected_target,
        "features": workflow.selected_features,
    }
    if workflow.prediction_id:
        prediction = workflow.prediction
        return render(request, "results.html", {
            "dataset": dataset, "model": workflow.model, "prediction": prediction,
            "predicted": prediction.predicted_value, "actual": prediction.actual_value,
            "metrics": prediction.evaluation, "target": prediction.target_column,
            "algorithm": workflow.model.get_algorithm_display(),
        })
    df = read_dataset(dataset.file)
    try:
        bundle, metrics, evaluation = train_regressor(
            df,
            settings_data["target"],
            settings_data["features"],
            settings_data["algorithm"],
        )
        name = f"{settings_data['algorithm']} - {settings_data['target']}"
        model = MLModel.objects.create(
            name=name,
            algorithm=settings_data["algorithm"],
            target_column=settings_data["target"],
            feature_columns=settings_data["features"],
            metrics=metrics,
            created_by=request.user,
        )
        buf = io.BytesIO()
        import joblib
        joblib.dump(bundle, buf)
        model.model_file.save(f"model_{model.id}.joblib", ContentFile(buf.getvalue()), save=True)

        # Predict the latest valid row.
        cleaned = clean_dataset(df)
        latest = cleaned.iloc[-1].to_dict()
        predicted = predict_one(bundle, latest)
        actual = pd.to_numeric(pd.Series([latest.get(settings_data["target"])]), errors="coerce").iloc[0]
        if pd.isna(actual):
            actual = None
        prediction_rows = evaluation.to_dict(orient="records")
        for row in prediction_rows:
            row["difference"] = float(row["actual"] - row["predicted"])
        prediction = Prediction.objects.create(
            dataset=dataset, model=model, target_column=settings_data["target"],
            predicted_value=predicted, actual_value=actual, created_by=request.user,
            evaluation=metrics,
            prediction_rows=prediction_rows,
            processing_run=workflow.processing_run,
        )
        workflow.model = model
        workflow.prediction = prediction
        workflow.completed_stage = 4
        workflow.save(update_fields=["model", "prediction", "completed_stage", "updated_at"])
        record_audit(
            request.user,
            "prediction_completed",
            "Prediction",
            prediction.id,
            {"dataset_id": dataset.id, "model_id": model.id, "target": prediction.target_column},
        )
        context = {
            "dataset": dataset,
            "model": model,
            "predicted": predicted,
            "actual": actual,
            "metrics": metrics,
            "target": settings_data["target"],
            "algorithm": dict(MLModel.ALGORITHMS).get(settings_data["algorithm"], settings_data["algorithm"]),
            "prediction": prediction,
            "features": settings_data["features"],
        }
        return render(request, "results.html", context)
    except Exception as exc:
        messages.error(request, f"Prediction could not be generated: {exc}")
        return redirect("predict")

@officer_required
@stage_required(4)
def visualize(request):
    workflow = get_workflow(request.user)
    prediction = workflow.prediction
    if not workflow.dataset or not workflow.model or not prediction:
        messages.warning(request, "Complete a prediction before opening its visualizations.")
        return redirect("prediction_results" if workflow.completed_stage >= 3 else "predict")
    evaluation = pd.DataFrame(prediction.prediction_rows)
    chart_urls = []
    chart_keys = []
    source = clean_dataset(read_dataset(workflow.dataset.file))
    target_values = pd.to_numeric(source[prediction.target_column], errors="coerce").dropna()
    if not target_values.empty:
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.hist(target_values, bins=30, color="#5b35c9", alpha=0.85)
        ax.set_title(f"Observed distribution: {prediction.target_column}")
        ax.set_xlabel(prediction.target_column)
        ax.set_ylabel("Record count")
        fig.tight_layout()
        chart_key = save_chart(fig, prediction.id)
        chart_keys.append(chart_key)
        chart_urls.append(default_storage.url(chart_key))
    if not evaluation.empty and {"actual", "predicted"}.issubset(evaluation.columns):
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(evaluation.index, evaluation["actual"], label="Actual")
        ax.plot(evaluation.index, evaluation["predicted"], label="Predicted")
        ax.set_title(f"{prediction.target_column} - Actual vs Predicted")
        ax.set_xlabel("Test record")
        ax.set_ylabel(prediction.target_column)
        ax.legend()
        fig.tight_layout()
        chart_key = save_chart(fig, prediction.id)
        chart_keys.append(chart_key)
        chart_urls.append(default_storage.url(chart_key))
    if workflow.algorithm == "RANDOM_FOREST" and workflow.model.model_file:
        import joblib
        with workflow.model.model_file.open("rb") as model_file:
            bundle = joblib.load(model_file)
        fitted_model = bundle["model"]
        if hasattr(fitted_model, "feature_importances_"):
            importance = pd.Series(fitted_model.feature_importances_, index=bundle["features"]).sort_values().tail(15)
            fig, ax = plt.subplots(figsize=(9, 4))
            importance.plot.barh(ax=ax)
            ax.set_title("Random Forest Feature Importance")
            ax.set_xlabel("Importance")
            fig.tight_layout()
            chart_key = save_chart(fig, prediction.id)
            chart_keys.append(chart_key)
            chart_urls.append(default_storage.url(chart_key))
    visualization, _ = Visualization.objects.update_or_create(
        prediction=prediction,
        defaults={
            "dataset": workflow.dataset,
            "model": workflow.model,
            "created_by": request.user,
            "chart_files": chart_keys,
        },
    )
    workflow.visualization = visualization
    workflow.visualization_completed = bool(chart_urls)
    if workflow.visualization_completed:
        workflow.completed_stage = max(workflow.completed_stage, 5)
        workflow.save(update_fields=["visualization", "visualization_completed", "completed_stage", "updated_at"])
        record_audit(
            request.user,
            "visualization_generated",
            "Visualization",
            visualization.id,
            {"prediction_id": prediction.id, "charts": len(chart_urls)},
        )
    return render(request, "visualize.html", {
        "dataset": workflow.dataset,
        "model": workflow.model,
        "prediction": prediction,
        "chart_urls": chart_urls,
        "target": prediction.target_column,
    })

@officer_required
@stage_required(5)
def reports(request):
    return render(request, "reports.html", {
        "workflow": get_workflow(request.user),
        "reports": Report.objects.filter(generated_by=request.user).order_by("-generated_at")[:10],
    })

@officer_required
@stage_required(5)
def generate_report(request):
    if request.method != "POST":
        return redirect("reports")
    workflow = get_workflow(request.user)
    dataset, model, prediction = workflow.dataset, workflow.model, workflow.prediction
    if not dataset or not model or not prediction or not workflow.visualization_completed:
        messages.error(request, "Complete the prediction and visualization before generating a report.")
        return redirect("visualize")
    title = request.POST.get("title") or f"Incineration Prediction Report - {datetime.now():%B %Y}"
    report = Report.objects.create(
        title=title,
        report_type=request.POST.get("report_type", "SUMMARY"),
        dataset=dataset,
        model=model,
        prediction=prediction,
        visualization=workflow.visualization,
        generated_by=request.user,
        content={
            "sections": ["dataset", "preprocessing", "model", "target", "features", "evaluation", "prediction", "visualizations", "system"],
            "dataset": dataset.name,
            "rows": dataset.row_count,
            "columns": dataset.column_count,
            "preprocessing": dataset.preprocessing_summary,
            "algorithm": model.get_algorithm_display(),
            "features": model.feature_columns,
            "target": model.target_column if model else None,
            "metrics": model.metrics if model else {},
            "predicted": prediction.predicted_value,
            "actual": prediction.actual_value,
            "prediction_rows": prediction.prediction_rows,
            "visualizations": workflow.visualization.chart_files,
            "system": "NEMA Incineration ML Decision Support System",
        },
    )
    workflow.report = report
    workflow.completed_stage = max(workflow.completed_stage, 6)
    workflow.save(update_fields=["report", "completed_stage", "updated_at"])
    record_audit(
        request.user,
        "report_generated",
        "Report",
        report.id,
        {"prediction_id": prediction.id, "dataset_id": dataset.id},
    )
    return redirect("report_preview", report_id=report.id)

@officer_required
def report_preview(request, report_id):
    report = get_object_or_404(Report, pk=report_id, generated_by=request.user)
    return render(request, "report_preview.html", {"report": report})

@officer_required
def download_pdf(request, report_id):
    report = get_object_or_404(Report, pk=report_id, generated_by=request.user)
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _, height = A4
    y = height - 25*mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, y, "NEMA Incineration Prediction Report")
    y -= 10*mm
    c.setFont("Helvetica", 10)
    lines = [
        f"Title: {report.title}",
        f"Dataset: {report.content.get('dataset', '-')}",
        f"Records: {report.content.get('rows', '-')}",
        f"Columns: {report.content.get('columns', '-')}",
        f"Model: {report.content.get('algorithm', '-')}",
        f"Target: {report.content.get('target', '-')}",
        f"Input features: {', '.join(report.content.get('features', []))}",
        f"Original records: {report.content.get('preprocessing', {}).get('original_records', '-')}",
        f"Duplicates removed: {report.content.get('preprocessing', {}).get('duplicates_removed', '-')}",
        f"Missing values handled: {report.content.get('preprocessing', {}).get('missing_values_handled', '-')}",
        f"Outliers detected: {report.content.get('preprocessing', {}).get('outliers_detected', '-')}",
        f"Final records: {report.content.get('preprocessing', {}).get('rows', '-')}",
        f"Latest actual value: {report.content.get('actual', '-')}",
        f"Predicted value: {report.content.get('predicted', '-')}",
        "Model metrics:",
    ]
    for line in lines:
        if y < 25*mm:
            c.showPage()
            y = height - 25*mm
            c.setFont("Helvetica", 10)
        c.drawString(20*mm, y, line[:110])
        y -= 6*mm
    for k, v in report.content.get("metrics", {}).items():
        if y < 25*mm:
            c.showPage()
            y = height - 25*mm
            c.setFont("Helvetica", 10)
        c.drawString(30*mm, y, f"{k}: {v}")
        y -= 5*mm
    y -= 5*mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20*mm, y, "Prediction Evaluation (first 25 test records)")
    y -= 7*mm
    c.setFont("Helvetica", 8)
    for row in report.content.get("prediction_rows", [])[:25]:
        if y < 20*mm:
            c.showPage()
            y = height - 20*mm
        c.drawString(20*mm, y, f"Actual: {row.get('actual')}  Predicted: {row.get('predicted')}  Difference: {row.get('difference')}")
        y -= 4*mm
    for image_name in report.content.get("visualizations", []):
        if default_storage.exists(image_name):
            c.showPage()
            c.setFont("Helvetica-Bold", 12)
            c.drawString(20*mm, height - 20*mm, image_name.rsplit("/", 1)[-1])
            from reportlab.lib.utils import ImageReader
            with default_storage.open(image_name, "rb") as image_file:
                image_data = io.BytesIO(image_file.read())
            c.drawImage(ImageReader(image_data), 20*mm, 35*mm, width=170*mm, height=115*mm, preserveAspectRatio=True, anchor="c")
    y -= 5*mm
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, 15*mm, "Advisory decision support only. This system does not control incineration equipment.")
    c.save()
    buf.seek(0)
    return FileResponse(buf, as_attachment=True, filename=f"report_{report.id}.pdf")

@officer_required
def download_excel(request, report_id):
    report = get_object_or_404(Report, pk=report_id, generated_by=request.user)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        content = report.content
        overview = {
            "Report": report.title,
            "Generated by": request.user.username,
            "Dataset": content.get("dataset"),
            "Records": content.get("rows"),
            "Columns": content.get("columns"),
            "Model": content.get("algorithm"),
            "Target": content.get("target"),
            "Features": ", ".join(content.get("features", [])),
            "Actual": content.get("actual"),
            "Predicted": content.get("predicted"),
            "System": content.get("system"),
        }
        pd.DataFrame([overview]).to_excel(writer, index=False, sheet_name="Dataset Summary")
        pd.DataFrame([content.get("preprocessing", {})]).to_excel(
            writer, index=False, sheet_name="Preprocessing"
        )
        pd.DataFrame(
            list(content.get("metrics", {}).items()), columns=["Metric", "Value"]
        ).to_excel(writer, index=False, sheet_name="Model Evaluation")
        pd.DataFrame(content.get("prediction_rows", [])).to_excel(
            writer, index=False, sheet_name="Prediction Results"
        )
        pd.DataFrame(
            {"Visualization file": content.get("visualizations", [])}
        ).to_excel(writer, index=False, sheet_name="Visualizations")
    output.seek(0)
    return FileResponse(output, as_attachment=True, filename=f"report_{report.id}.xlsx")


@officer_required
def download_page(request, report_id):
    report = get_object_or_404(Report, pk=report_id, generated_by=request.user)
    return render(request, "download.html", {"report": report})

@officer_required
@stage_required(6)
def history(request):
    predictions = Prediction.objects.filter(created_by=request.user).select_related("model", "dataset").order_by("-created_at")[:100]
    rows = [{
        "prediction": prediction,
        "report": Report.objects.filter(prediction=prediction, generated_by=request.user).order_by("-generated_at").first(),
    } for prediction in predictions]
    return render(request, "history.html", {"rows": rows})


@officer_required
def prediction_view(request, prediction_id):
    prediction = get_object_or_404(
        Prediction.objects.select_related("model", "dataset"),
        pk=prediction_id,
        created_by=request.user,
    )
    return render(request, "results.html", {
        "dataset": prediction.dataset,
        "model": prediction.model,
        "prediction": prediction,
        "predicted": prediction.predicted_value,
        "actual": prediction.actual_value,
        "metrics": prediction.evaluation,
        "target": prediction.target_column,
        "algorithm": prediction.model.get_algorithm_display() if prediction.model else "—",
    })

@admin_required
def admin_dashboard(request):
    storage_bytes = 0
    for stored_file in list(Dataset.objects.only("file")) + list(MLModel.objects.only("model_file")):
        file_field = getattr(stored_file, "file", None) or getattr(stored_file, "model_file", None)
        try:
            storage_bytes += file_field.size if file_field else 0
        except (OSError, ValueError):
            continue
    context = {
        "users": User.objects.count(),
        "officers": UserProfile.objects.filter(role=UserProfile.ROLE_OFFICER).count(),
        "datasets": Dataset.objects.count(),
        "models": MLModel.objects.count(),
        "reports": Report.objects.count(),
        "active_users": User.objects.filter(is_active=True).count(),
        "last_model": MLModel.objects.order_by("-created_at").first(),
        "latest_activity": Prediction.objects.select_related("created_by", "dataset").order_by("-created_at").first(),
        "storage_used_mb": round(storage_bytes / (1024 * 1024), 2),
    }
    return render(request, "admin_dashboard.html", context)

@admin_required
def user_management(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            full_name = form.cleaned_data["full_name"].strip().split(maxsplit=1)
            u = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                first_name=full_name[0],
                last_name=full_name[1] if len(full_name) > 1 else "",
                is_active=form.cleaned_data["is_active"] != "False",
            )
            UserProfile.objects.create(
                user=u,
                role=UserProfile.ROLE_OFFICER,
                department=form.cleaned_data["department"],
            )
            record_audit(request.user, "officer_created", "User", u.id, {"username": u.username})
            messages.success(
                request,
                f"Officer account {u.username} created as "
                f"{'active' if u.is_active else 'inactive'}. "
                "They can sign in using the Environmental Officer role.",
            )
            return redirect("users")
    else:
        form = UserCreateForm()
    officers = User.objects.filter(profile__role=UserProfile.ROLE_OFFICER).select_related("profile").order_by("username")
    return render(request, "users.html", {"form": form, "users": officers})

@admin_required
def model_management(request):
    return render(request, "models.html", {"models": MLModel.objects.order_by("-created_at")})


@admin_required
def admin_datasets(request):
    datasets = Dataset.objects.select_related("uploaded_by").order_by("-uploaded_at")
    rows = [{
        "dataset": dataset,
        "processing_status": "Completed" if dataset.processing_runs.filter(status="COMPLETED").exists() else "Pending",
        "prediction_status": "Completed" if dataset.prediction_set.exists() else "Pending",
    } for dataset in datasets]
    return render(request, "admin_datasets.html", {"datasets": rows})


@admin_required
def admin_reports(request):
    return render(request, "admin_reports.html", {
        "reports": Report.objects.select_related("generated_by", "dataset", "model").order_by("-generated_at")[:100]
    })


@admin_required
def user_activity(request):
    recent_predictions = Prediction.objects.select_related("created_by", "dataset", "model").order_by("-created_at")[:100]
    recent_uploads = Dataset.objects.select_related("uploaded_by").order_by("-uploaded_at")[:100]
    return render(request, "user_activity.html", {
        "predictions": recent_predictions,
        "uploads": recent_uploads,
    })


@admin_required
def audit_log(request):
    events = AuditEvent.objects.select_related("actor").order_by("-created_at")[:200]
    return render(request, "audit_log.html", {"events": events})


@admin_required
def system_settings(request):
    return render(request, "system_settings.html", {
        "database_engine": settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1],
        "timezone": settings.TIME_ZONE,
        "debug_enabled": settings.DEBUG,
        "upload_limit_mb": MAX_UPLOAD_SIZE // (1024 * 1024),
    })


@admin_required
def officer_edit(request, user_id):
    officer = get_object_or_404(User, pk=user_id, profile__role=UserProfile.ROLE_OFFICER)
    if request.method == "POST":
        form = OfficerUpdateForm(request.POST)
        if form.is_valid():
            name_parts = form.cleaned_data["full_name"].strip().split(maxsplit=1)
            officer.first_name = name_parts[0]
            officer.last_name = name_parts[1] if len(name_parts) > 1 else ""
            officer.email = form.cleaned_data["email"]
            officer.save(update_fields=["first_name", "last_name", "email"])
            officer.profile.department = form.cleaned_data["department"]
            officer.profile.save(update_fields=["department"])
            record_audit(request.user, "officer_updated", "User", officer.id)
            messages.success(request, f"Officer {officer.username} updated.")
            return redirect("users")
    else:
        form = OfficerUpdateForm(initial={
            "full_name": officer.get_full_name(),
            "email": officer.email,
            "department": officer.profile.department,
        })
    return render(request, "officer_edit.html", {"form": form, "officer": officer})


@admin_required
def officer_status(request, user_id):
    if request.method != "POST":
        return redirect("users")
    officer = get_object_or_404(User, pk=user_id, profile__role=UserProfile.ROLE_OFFICER)
    officer.is_active = not officer.is_active
    officer.save(update_fields=["is_active"])
    record_audit(request.user, "officer_status_changed", "User", officer.id, {"active": officer.is_active})
    messages.success(request, f"Officer {officer.username} status updated.")
    return redirect("users")


@admin_required
def officer_reset_password(request, user_id):
    officer = get_object_or_404(User, pk=user_id, profile__role=UserProfile.ROLE_OFFICER)
    if request.method == "POST":
        password = request.POST.get("password", "")
        confirmation = request.POST.get("confirm_password", "")
        if len(password) < 8 or password != confirmation:
            messages.error(request, "Use matching passwords of at least 8 characters.")
        else:
            officer.set_password(password)
            officer.save(update_fields=["password"])
            record_audit(request.user, "officer_password_reset", "User", officer.id)
            messages.success(request, f"Password reset for {officer.username}.")
    return redirect("users")


@admin_required
def model_status(request, model_id):
    if request.method == "POST":
        model = get_object_or_404(MLModel, pk=model_id)
        model.active = not model.active
        model.save(update_fields=["active"])
        record_audit(request.user, "model_status_changed", "MLModel", model.id, {"active": model.active})
        messages.success(request, f"Model {model.name} status updated.")
    return redirect("models")
