# Proposal-to-implementation traceability

| Proposal requirement | Implementation |
|---|---|
| Django-based system | `nema_dss/`, `core/` |
| Environmental Officer login | Django authentication |
| Dataset upload | `UploadDatasetForm`, `/upload/` |
| CSV/Excel | Pandas CSV/Excel readers |
| Data preprocessing | `core/ml.py`, `/preprocess/` |
| Missing values | Median imputation for numeric fields |
| Duplicate records | Duplicate removal |
| Feature selection | Prediction Settings |
| Machine learning | Random Forest and Linear Regression |
| Model evaluation | MAE, RMSE, R² |
| Prediction results | `/predict/results/` |
| Visualisation | Matplotlib chart |
| Reports | Report model, PDF/Excel export |
| Prediction history | Prediction model and `/history/` |
| Administrator | `/admin-dashboard/`, `/users/`, `/models/` |
| No automatic control | No plant-control/API endpoint is implemented |

The proposal itself states that the system should provide predictive insights and should not include real-time monitoring or automatic control of incineration equipment.
