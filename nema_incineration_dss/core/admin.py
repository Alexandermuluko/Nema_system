from django.contrib import admin
from .models import UserProfile, Dataset, MLModel, Prediction, Report

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "created_at")

@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "row_count", "column_count", "uploaded_by", "uploaded_at")

@admin.register(MLModel)
class MLModelAdmin(admin.ModelAdmin):
    list_display = ("name", "algorithm", "target_column", "active", "created_at")

@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ("dataset", "target_column", "predicted_value", "status", "created_at")

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("title", "report_type", "generated_by", "generated_at")
