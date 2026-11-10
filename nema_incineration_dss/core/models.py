from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    ROLE_OFFICER = "ENVIRONMENTAL_OFFICER"
    ROLE_ADMIN = "ADMINISTRATOR"
    ROLE_CHOICES = [
        (ROLE_OFFICER, "Environmental Officer"),
        (ROLE_ADMIN, "Administrator"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=24, choices=ROLE_CHOICES, default=ROLE_OFFICER)
    department = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

class Dataset(models.Model):
    VALIDATION_CHOICES = [("PENDING", "Pending"), ("VALID", "Valid"), ("FAILED", "Failed")]
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="datasets/")
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    row_count = models.PositiveIntegerField(default=0)
    column_count = models.PositiveIntegerField(default=0)
    columns = models.JSONField(default=list)
    preprocessing_summary = models.JSONField(default=dict, blank=True)
    preview = models.JSONField(default=list, blank=True)
    validation_status = models.CharField(max_length=12, choices=VALIDATION_CHOICES, default="PENDING")

    def __str__(self):
        return self.name

class MLModel(models.Model):
    ALGORITHMS = [("RANDOM_FOREST", "Random Forest Regressor"), ("LINEAR_REGRESSION", "Linear Regression")]
    name = models.CharField(max_length=255)
    algorithm = models.CharField(max_length=40, choices=ALGORITHMS)
    target_column = models.CharField(max_length=255)
    feature_columns = models.JSONField(default=list)
    metrics = models.JSONField(default=dict, blank=True)
    model_file = models.FileField(upload_to="models/", null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Prediction(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE)
    processing_run = models.ForeignKey("ProcessingRun", on_delete=models.SET_NULL, null=True, blank=True)
    model = models.ForeignKey(MLModel, on_delete=models.SET_NULL, null=True)
    target_column = models.CharField(max_length=255)
    predicted_value = models.FloatField(null=True, blank=True)
    actual_value = models.FloatField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, default="Completed")
    evaluation = models.JSONField(default=dict, blank=True)
    prediction_rows = models.JSONField(default=list, blank=True)


class ProcessingRun(models.Model):
    STATUS_CHOICES = [("COMPLETED", "Completed"), ("FAILED", "Failed")]
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="processing_runs")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="COMPLETED")
    summary = models.JSONField(default=dict, blank=True)


class Visualization(models.Model):
    prediction = models.OneToOneField(Prediction, on_delete=models.CASCADE, related_name="visualization")
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE)
    model = models.ForeignKey(MLModel, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    chart_files = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditEvent(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=80)
    entity_id = models.PositiveBigIntegerField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Workflow(models.Model):
    STAGE_CHOICES = [
        (0, "Upload Dataset"),
        (1, "Data Preview"),
        (2, "Preprocessing"),
        (3, "Prediction Settings"),
        (4, "Prediction Results"),
        (5, "Visualization"),
        (6, "Generate Report"),
        (7, "Prediction History"),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="workflow")
    dataset = models.ForeignKey(Dataset, on_delete=models.SET_NULL, null=True, blank=True)
    processing_run = models.ForeignKey(ProcessingRun, on_delete=models.SET_NULL, null=True, blank=True)
    model = models.ForeignKey("MLModel", on_delete=models.SET_NULL, null=True, blank=True)
    prediction = models.ForeignKey(Prediction, on_delete=models.SET_NULL, null=True, blank=True)
    visualization = models.ForeignKey("Visualization", on_delete=models.SET_NULL, null=True, blank=True)
    report = models.ForeignKey("Report", on_delete=models.SET_NULL, null=True, blank=True)
    selected_target = models.CharField(max_length=255, blank=True)
    selected_features = models.JSONField(default=list, blank=True)
    algorithm = models.CharField(max_length=40, blank=True)
    completed_stage = models.IntegerField(default=-1)
    visualization_completed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

class Report(models.Model):
    REPORT_TYPES = [("SUMMARY", "Prediction Summary Report"), ("MONITORING", "Environmental Monitoring Report")]
    title = models.CharField(max_length=255)
    report_type = models.CharField(max_length=30, choices=REPORT_TYPES, default="SUMMARY")
    dataset = models.ForeignKey(Dataset, on_delete=models.SET_NULL, null=True, blank=True)
    model = models.ForeignKey(MLModel, on_delete=models.SET_NULL, null=True, blank=True)
    prediction = models.ForeignKey(Prediction, on_delete=models.SET_NULL, null=True, blank=True)
    visualization = models.ForeignKey(Visualization, on_delete=models.SET_NULL, null=True, blank=True)
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    content = models.JSONField(default=dict, blank=True)
    generated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
