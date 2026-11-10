# Setup and next steps

## 1. Install

Use Python 3.11+.

    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    pip install -r requirements.txt

Copy `.env.example` to `.env`.

## 2. Database

### SQLite
Use `DB_ENGINE=sqlite` for a simple local demonstration.

    python manage.py migrate
    python manage.py createsuperuser
    python manage.py runserver

### PostgreSQL
Create a PostgreSQL database named `nema_dss`, then set the credentials in `.env`.

    DB_ENGINE=postgresql
    DB_NAME=nema_dss
    DB_USER=postgres
    DB_PASSWORD=...
    DB_HOST=127.0.0.1
    DB_PORT=5432

Then run:

    python manage.py migrate
    python manage.py createsuperuser

The included `database/schema.sql` documents the application tables, but do not manually maintain a second schema indefinitely: use Django migrations for the deployed application.

## 3. Dataset

The supplied real `output.csv` is already integrated under `data/output.csv`. The source file contains a corrupted tail after the last fully valid record (`2024-10-10 23:35:20`), so the packaged working copy contains the 314,924 clean records. Keep the original uploaded CSV as the raw source for traceability.

Expected columns:

- record_time
- aicsa_071
- co_a
- f051_sp_int
- f052_sp_int
- f081_sp_int
- hcl_a
- hf_a
- jz_zl
- nox_a
- p062a_sp_int
- p062b_sp_int
- p071a_sp_int
- p071b_sp_int
- si02_a
- so2_a
- tia_051
- tia_057
- tia_075
- ti_053
- yyz_wf_t_rc
- i052

## 4. Critical data-mapping step

Before using the system for academic model evaluation, obtain the plant/data dictionary that explains each tag. The proposal mentions furnace temperature, oxygen concentration, airflow, fuel consumption and emissions, but the supplied CSV header does not explicitly identify which tag is which.

Do not claim:
- `tia_051` is furnace temperature,
- `i052` is oxygen,
- or any other mapping,

unless the dataset owner confirms it.

After confirmation, update `config/column_mapping.json` with the verified display labels and units.

## 5. Model evaluation

For an academic report, use the same train/test strategy for all candidate models. Record:
- MAE
- RMSE
- R²
- training rows
- testing rows

Do not compare models using only training performance.

## 6. UI workflow

The implemented workflow follows the supplied UI reference:

1. Login
2. Dashboard
3. Upload Dataset
4. Uploaded Data / Data Preview
5. Data Preprocessing
6. Prediction Settings
7. Prediction Results
8. Visualization / Charts
9. Generate Report
10. Report Preview
11. Download / Export Report
12. Prediction History
13. Admin Dashboard
14. User Management
15. Model Management

## 7. Suggested evidence for the final project report

Capture screenshots of:
- login screen
- dashboard after data upload
- output.csv preview
- preprocessing summary
- prediction settings
- prediction results with metrics
- actual vs predicted chart
- generated report
- PDF report
- prediction history
- admin dashboard
- user management
- model management

For the dissertation/project report, clearly label any screenshots using synthetic data as demonstration screenshots.

## 8. Future enhancements

The proposal's scope excludes real-time monitoring, automatic process control and sensor integration. Those can be listed as future work rather than implemented as hidden functionality.

Possible future additions:
- verified NEMA/plant tag dictionary
- model comparison page
- cross-validation
- model versioning and activation
- role permissions per action
- audit logging
- richer Plotly charts
- real plant data validation
- deployment behind HTTPS
