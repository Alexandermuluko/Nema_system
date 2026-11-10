# NEMA Hazardous Waste Incineration ML Decision Support System

A Django + scikit-learn decision-support prototype based on the supplied Dedan Kimathi University of Technology proposal and the 15-screen UI reference.

## Project basis

The supplied proposal specifies:
- Django + Python backend
- Pandas/NumPy for data processing
- scikit-learn for machine learning
- Matplotlib/Plotly for visualisation
- CSV/Excel uploads
- Environmental Officer and System Administrator roles
- preprocessing, prediction, charts, reports, history and model management
- no real-time control and no automatic control of incineration equipment

The application implements those modules while keeping the prediction target configurable because the supplied `output.csv` column names are process tags rather than self-describing business labels.

## Included data

`data/output.csv` contains the requested header:

`record_time, aicsa_071, co_a, f051_sp_int, f052_sp_int, f081_sp_int, hcl_a, hf_a, jz_zl, nox_a, p062a_sp_int, p062b_sp_int, p071a_sp_int, p071b_sp_int, si02_a, so2_a, tia_051, tia_057, tia_075, ti_053, yyz_wf_t_rc, i052`

The supplied real `output.csv` has been integrated. During inspection, the file contained a clean, consistently structured portion followed by a corrupted tail. The packaged `data/output.csv` contains the 314,924 fully valid records ending at `2024-10-10 23:35:20`. The original uploaded file should be retained separately as the raw source; do not claim the corrupted tail as valid measurements.

For a complete local demonstration without the supplied dataset, run:

    python manage.py seed_demo_data

This generates synthetic records only for software testing.

## Quick start

1. Create and activate a virtual environment.
2. Install packages:

    pip install -r requirements.txt

3. Copy `.env.example` to `.env`.

4. For the fastest development setup, leave:

    DB_ENGINE=sqlite

5. Create database tables:

    python manage.py migrate

6. Create an administrator:

    python manage.py createsuperuser

7. Optional demo data:

    python manage.py seed_demo_data

8. Run:

    python manage.py runserver
http://127.0.0.1:8000
9. Open `/` to reach the Login screen. After signing in, the app opens the dashboard at `/dashboard/`.

### Admin-created officer sign-in

Administrators create Environmental Officer accounts from User Management. New accounts default to **Active** unless the administrator explicitly selects **Inactive**. The officer signs in with the created username/password and chooses **Environmental Officer** as the role. Selecting Administrator does not grant admin access; the selected role must match the account's stored role.

## PostgreSQL

Set these variables in `.env`:

    DB_ENGINE=postgresql
    DB_NAME=nema_dss
    DB_USER=postgres
    DB_PASSWORD=your_password
    DB_HOST=127.0.0.1
    DB_PORT=5432

Then:

    python manage.py migrate
    python manage.py createsuperuser
    python manage.py runserver

The `database/schema.sql` file is provided as a reference/initialisation script for the application tables. Django migrations remain the authoritative schema mechanism.

## CSV upload

The UI accepts CSV and Excel files up to 200 MB. The supplied working `data/output.csv` is approximately 126 MB, so it now fits within the upload limit. After upload, the file is stored under `MEDIA_ROOT`, attached to the signed-in officer's active workflow, previewed/validated, and passed through preprocessing and prediction without asking the user to upload it again.

The application:
- validates uploaded files
- parses dates where possible
- removes duplicate rows
- handles numeric missing values using median imputation
- one-hot encodes categorical values
- scales values where required by the selected model
- performs an 80/20 train-test split
- stores preprocessing metadata

## Prediction design

The UI lets the user select:
- algorithm: Random Forest Regressor or Linear Regression
- target parameter
- input features

This is deliberate: the proposal does not specify which of the supplied process-tag columns is the target, and the supplied header does not identify a unique "furnace temperature", "oxygen", "airflow", or "fuel" field. The system therefore does not silently invent a mapping.

The current real-data training run uses Random Forest Regressor to estimate `co_a` from the other configured numeric process tags. On a deterministic 80/20 holdout from 314,924 valid rows, it achieved R² 0.994395 (99.44% variance explained), MAE 2.143424, and RMSE 13.090101. R² is a regression metric, not classification accuracy or a guarantee of operational performance. The model and prediction are saved against the officer's active workflow.

`config/column_mapping.json` is included as a place to add verified plant-specific labels after the meaning of each tag has been confirmed.

## Safety / scope

This is a research/academic decision-support application. It is not an automatic incinerator controller and does not send commands to plant equipment. Predictions are advisory and depend on the quality and representativeness of historical data.

## UI

The frontend follows the supplied reference: purple header/sidebar, NEMA branding text, numbered workflow:
1 Login
2 Dashboard
3 Upload Dataset
4 Data Preview
5 Data Preprocessing
6 Prediction Settings
7 Prediction Results
8 Visualization / Charts
9 Generate Report
10 Report Preview
11 Download / Export Report
12 Prediction History
13 Admin Dashboard
14 User Management
15 Model Management

## Main URLs

- `/` login screen
- `/login/` login screen
- `/dashboard/` authenticated dashboard
- `/about/` system scope and proposal workflow
- `/contact/` support and safety guidance
- `/upload/`
- `/preprocess/`
- `/predict/`
- `/visualize/`
- `/reports/`
- `/history/`
- `/admin-dashboard/`
- `/users/`
- `/models/`
- `/django-admin/`

