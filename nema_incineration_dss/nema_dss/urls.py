from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile, name="profile"),
    path("upload/", views.upload_dataset, name="upload"),
    path("data-preview/", views.data_preview, name="data_preview"),
    path("preprocess/", views.preprocess, name="preprocess"),
    path("predict/", views.predict_settings, name="predict"),
    path("predict/results/", views.prediction_results, name="prediction_results"),
    path("visualize/", views.visualize, name="visualize"),
    path("reports/", views.reports, name="reports"),
    path("reports/generate/", views.generate_report, name="generate_report"),
    path("reports/<int:report_id>/", views.report_preview, name="report_preview"),
    path("reports/<int:report_id>/download/pdf/", views.download_pdf, name="download_pdf"),
    path("reports/<int:report_id>/download/excel/", views.download_excel, name="download_excel"),
    path("reports/<int:report_id>/download/", views.download_page, name="download_page"),
    path("history/", views.history, name="history"),
    path("predictions/<int:prediction_id>/", views.prediction_view, name="prediction_view"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("users/", views.user_management, name="users"),
    path("users/<int:user_id>/status/", views.officer_status, name="officer_status"),
    path("users/<int:user_id>/reset-password/", views.officer_reset_password, name="officer_reset_password"),
    path("users/<int:user_id>/edit/", views.officer_edit, name="officer_edit"),
    path("models/", views.model_management, name="models"),
    path("models/<int:model_id>/status/", views.model_status, name="model_status"),
    path("admin/datasets/", views.admin_datasets, name="admin_datasets"),
    path("admin/reports/", views.admin_reports, name="admin_reports"),
    path("admin/user-activity/", views.user_activity, name="user_activity"),
    path("admin/audit-log/", views.audit_log, name="audit_log"),
    path("admin/system-settings/", views.system_settings, name="system_settings"),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
