from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from nema_dss.settings import get_allowed_hosts

from .forms import MAX_UPLOAD_SIZE, UploadDatasetForm
from .ml import read_dataset, train_regressor
from .models import AuditEvent, UserProfile, Workflow


class VercelAllowedHostsTests(SimpleTestCase):
    def test_project_vercel_domain_is_allowed_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIn("nema-system.vercel.app", get_allowed_hosts())

    def test_vercel_deployment_hosts_are_allowed(self):
        with patch.dict(
            "os.environ",
            {
                "ALLOWED_HOSTS": "localhost",
                "VERCEL_URL": "nema-system-preview.vercel.app",
                "VERCEL_PROJECT_PRODUCTION_URL": "nema-system.vercel.app",
                "VERCEL_BRANCH_URL": "nema-system-git-main.vercel.app",
            },
        ):
            self.assertEqual(
                get_allowed_hosts(),
                [
                    "localhost",
                    "nema-system-preview.vercel.app",
                    "nema-system.vercel.app",
                    "nema-system-git-main.vercel.app",
                ],
            )


class DemoDatasetTests(SimpleTestCase):
    def test_synthetic_dataset_can_train_a_model(self):
        dataset_path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "demo_test_dataset.csv"
        )
        dataframe = read_dataset(dataset_path)

        self.assertGreaterEqual(len(dataframe), 100)
        self.assertIn("record_time", dataframe.columns)
        self.assertIn("co_a", dataframe.columns)
        self.assertIn("aicsa_071", dataframe.columns)
        self.assertIn("f051_sp_int", dataframe.columns)
        self.assertIn("f052_sp_int", dataframe.columns)

        _, metrics, evaluation = train_regressor(
            dataframe,
            "co_a",
            ["aicsa_071", "f051_sp_int", "f052_sp_int"],
            "RANDOM_FOREST",
        )

        self.assertEqual(
            metrics["training_rows"] + metrics["testing_rows"], len(dataframe)
        )
        self.assertEqual(len(evaluation), metrics["testing_rows"])
        self.assertGreaterEqual(metrics["R2"], 0.0)


class LoginAndNavigationTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.officer = User.objects.create_user(
            username="officer", password="test-password-123"
        )
        UserProfile.objects.create(
            user=self.officer, role=UserProfile.ROLE_OFFICER
        )
        self.admin = User.objects.create_user(
            username="admin", password="test-password-123"
        )
        UserProfile.objects.create(user=self.admin, role=UserProfile.ROLE_ADMIN)

    def test_public_pages_and_login_role_selector(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Sign in to your account")
        self.assertContains(response, "Environmental Officer")
        self.assertContains(response, "Administrator")
        self.assertContains(response, reverse("about"))
        self.assertContains(response, reverse("contact"))
        self.assertContains(response, "Sign in")
        self.assertContains(
            self.client.get(reverse("about")), "Predictions are advisory"
        )
        self.assertContains(
            self.client.get(reverse("contact")), "system administrator"
        )

    def test_upload_form_accepts_large_real_dataset_size(self):
        upload = SimpleUploadedFile(
            "output.csv",
            b"record_time,co_a,hcl_a\n",
            content_type="text/csv",
        )
        upload.size = 126 * 1024 * 1024
        form = UploadDatasetForm(files={"file": upload})

        self.assertEqual(MAX_UPLOAD_SIZE, 200 * 1024 * 1024)
        self.assertTrue(form.is_valid(), form.errors)

    def test_malformed_nema_csv_keeps_valid_rows_and_reports_exclusions(self):
        source = Path(self.media_directory.name) / "output.csv"
        source.write_text(
            "record_time,co_a,hcl_a,nox_a\n"
            "2024-01-01 00:00:00,1.0,2.0,3.0\n"
            "2024-01-01 00:05:00,1.1,2.1,3.1\n"
            "2024-01-01 00:10:00,1.2,2.2,3.2\n"
            "2024-01-01 00:15:00,1.3,2.3,3.3\n"
            "2024-01-01 00:20:00,1.4,2.4,3.4\n"
            "2024-01-01 00:20:00,1.4,2.4,3.4\n"
            "2024-01-01 00:25:00,broken,broken,broken\n"
            "CORRUPTED,record,with,too,many,fields\n",
            encoding="utf-8",
        )

        dataframe = read_dataset(source)

        self.assertEqual(len(dataframe), 5)
        self.assertEqual(dataframe["co_a"].dtype.kind, "f")
        self.assertTrue(dataframe.attrs["source_recovered"])
        self.assertEqual(dataframe.attrs["source_records_excluded"], 3)

    def test_authenticated_user_root_is_still_public_login_page(self):
        self.client.force_login(self.officer)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Sign in to your account")
        self.assertNotContains(response, "WORKFLOW")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_login_verifies_role_and_redirects_to_role_dashboard(self):
        mismatch = self.client.post(
            reverse("login"),
            {
                "username": self.officer.username,
                "password": "test-password-123",
                "role": UserProfile.ROLE_ADMIN,
            },
        )
        self.assertContains(
            mismatch, "Invalid username, password, or selected role."
        )
        self.assertNotIn("_auth_user_id", self.client.session)

        officer_login = self.client.post(
            reverse("login"),
            {
                "username": self.officer.username,
                "password": "test-password-123",
                "role": UserProfile.ROLE_OFFICER,
            },
        )
        self.assertRedirects(officer_login, reverse("dashboard"))
        self.client.logout()
        admin_login = self.client.post(
            reverse("login"),
            {
                "username": self.admin.username,
                "password": "test-password-123",
                "role": UserProfile.ROLE_ADMIN,
            },
        )
        self.assertRedirects(admin_login, reverse("admin_dashboard"))

    def test_officer_cannot_open_administrator_pages(self):
        self.client.force_login(self.officer)
        names = (
            "users", "admin_dashboard", "models", "admin_datasets",
            "admin_reports", "user_activity", "audit_log", "system_settings",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_administrator_pages_and_sidebar_are_available(self):
        self.client.force_login(self.admin)
        names = (
            "users", "admin_dashboard", "models", "admin_datasets",
            "admin_reports", "user_activity", "audit_log", "system_settings",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertContains(
            self.client.get(reverse("admin_dashboard")), "Environmental Officers"
        )

    def test_admin_creation_form_can_only_create_environmental_officers(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("users"),
            {
                "full_name": "Rita Officer",
                "email": "rita@example.test",
                "username": "rita-officer",
                "password": "SafePassword123",
                "confirm_password": "SafePassword123",
                "department": "Compliance",
                "is_active": "True",
                "role": UserProfile.ROLE_ADMIN,
            },
        )
        self.assertRedirects(response, reverse("users"))
        created = User.objects.get(username="rita-officer")
        self.assertEqual(created.profile.role, UserProfile.ROLE_OFFICER)
        self.assertEqual(created.profile.department, "Compliance")
        self.assertTrue(created.is_active)
        self.assertTrue(AuditEvent.objects.filter(action="officer_created").exists())
        self.client.logout()
        sign_in = self.client.post(
            reverse("login"),
            {
                "username": "rita-officer",
                "password": "SafePassword123",
                "role": UserProfile.ROLE_OFFICER,
            },
        )
        self.assertRedirects(sign_in, reverse("dashboard"))
        self.client.logout()
        self.client.force_login(self.admin)
        self.client.post(reverse("officer_status", args=[created.id]))
        created.refresh_from_db()
        self.assertFalse(created.is_active)

    def test_officer_upload_is_owner_bound_and_later_urls_cannot_be_skipped(self):
        self.client.force_login(self.officer)
        unavailable_pages = (
            "data_preview",
            "preprocess",
            "predict",
            "prediction_results",
            "visualize",
            "reports",
            "history",
        )
        for page_name in unavailable_pages:
            with self.subTest(page_name=page_name):
                response = self.client.get(reverse(page_name))
                self.assertRedirects(response, reverse("upload"))
        content = (
            "record_time,co_a,hcl_a\n"
            "2024-01-01 00:00:00,1.2,2.1\n"
            "2024-01-01 00:05:00,1.3,2.0\n"
            "2024-01-01 00:10:00,1.4,2.2\n"
            "2024-01-01 00:15:00,1.5,2.3\n"
            "2024-01-01 00:20:00,1.6,2.4\n"
        )
        upload = SimpleUploadedFile(
            "output.csv", content.encode(), content_type="text/csv"
        )
        response = self.client.post(reverse("upload"), {"file": upload})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("data_preview"))
        preview_response = self.client.get(reverse("data_preview"))
        self.assertContains(preview_response, "Dataset uploaded:")
        workflow = Workflow.objects.get(user=self.officer)
        self.assertEqual(workflow.dataset.uploaded_by, self.officer)
        self.assertEqual(workflow.dataset.validation_status, "VALID")
        self.assertEqual(workflow.completed_stage, 1)
        self.assertTrue(
            workflow.dataset.file.storage.exists(workflow.dataset.file.name)
        )

    def test_complete_officer_flow_through_prediction_visualization_and_exports(self):
        self.client.force_login(self.officer)
        rows = [
            f"2024-01-01 00:{i:02d}:00,{i + 1.0},{i * 1.7 + 2.0},{i * 2.2 + 3.0}"
            for i in range(12)
        ]
        content = "record_time,co_a,hcl_a,nox_a\n" + "\n".join(rows)
        upload = SimpleUploadedFile(
            "output.csv", content.encode(), content_type="text/csv"
        )
        self.client.post(reverse("upload"), {"file": upload})
        self.assertEqual(self.client.get(reverse("data_preview")).status_code, 200)
        self.assertEqual(self.client.get(reverse("preprocess")).status_code, 200)
        response = self.client.post(
            reverse("predict"),
            {
                "algorithm": "LINEAR_REGRESSION",
                "target_column": "nox_a",
                "feature_columns": ["co_a", "hcl_a"],
            },
        )
        self.assertRedirects(response, reverse("prediction_results"))
        self.assertEqual(self.client.get(reverse("prediction_results")).status_code, 200)
        workflow = Workflow.objects.get(user=self.officer)
        workflow.refresh_from_db()
        self.assertEqual(
            workflow.prediction.processing_run_id, workflow.processing_run_id
        )
        self.assertEqual(workflow.prediction.dataset_id, workflow.dataset_id)
        self.assertEqual(workflow.model.target_column, "nox_a")
        self.assertEqual(workflow.model.feature_columns, ["co_a", "hcl_a"])
        self.assertTrue(workflow.model.model_file)
        self.assertTrue(
            workflow.model.model_file.storage.exists(workflow.model.model_file.name)
        )
        self.assertEqual(self.client.get(reverse("visualize")).status_code, 200)
        workflow.refresh_from_db()
        self.assertTrue(workflow.visualization_completed)
        self.assertEqual(
            self.client.post(reverse("generate_report"), {}).status_code, 302
        )
        workflow.refresh_from_db()
        self.assertEqual(workflow.report.prediction_id, workflow.prediction_id)
        self.assertEqual(workflow.report.visualization_id, workflow.visualization_id)
        for export_name in ("download_excel", "download_pdf"):
            response = self.client.get(
                reverse(export_name, args=[workflow.report_id])
            )
            self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditEvent.objects.filter(action="report_generated").exists()
        )
