from pathlib import Path
import json
import shutil
import tempfile
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

def read_dataset(source):
    is_path = isinstance(source, (str, Path))
    name = source if is_path else getattr(source, "name", "")
    suffix = Path(name).suffix.lower()
    stream = source

    if not is_path and hasattr(source, "open"):
        stream = source.open("rb")
    elif not is_path and hasattr(source, "seek"):
        source.seek(0)

    if suffix == ".csv":
        try:
            return pd.read_csv(source if is_path else stream)
        except (pd.errors.ParserError, UnicodeDecodeError) as error:
            if is_path:
                return _read_recoverable_nema_csv(Path(source), error)
            with tempfile.NamedTemporaryFile(suffix=".csv") as local_copy:
                stream.seek(0)
                shutil.copyfileobj(stream, local_copy)
                local_copy.flush()
                return _read_recoverable_nema_csv(
                    Path(local_copy.name), error
                )
    return pd.read_excel(source if is_path else stream)


def _read_recoverable_nema_csv(path, original_error):
    """Recover valid configured NEMA rows after a malformed CSV record.

    The source file is never changed. This path is deliberately restricted to
    the configured timestamp + process-tag format so arbitrary CSVs are not
    silently accepted with skipped rows.
    """
    mapping_path = Path(__file__).resolve().parent.parent / "config" / "column_mapping.json"
    try:
        with mapping_path.open(encoding="utf-8") as mapping_file:
            configured_columns = set(json.load(mapping_file))
        header = pd.read_csv(path, nrows=0, encoding_errors="replace")
    except (OSError, ValueError, pd.errors.ParserError):
        raise original_error

    columns = {str(column).strip() for column in header.columns}
    recognized_tags = sorted((columns & configured_columns) - {"record_time"})
    if "record_time" not in columns or len(recognized_tags) < 2:
        raise original_error

    recovered = pd.read_csv(
        path,
        on_bad_lines="skip",
        encoding_errors="replace",
        low_memory=False,
    )
    recovered.columns = [str(column).strip() for column in recovered.columns]
    timestamps = pd.to_datetime(recovered["record_time"], errors="coerce")
    numeric_tags = recovered[recognized_tags].apply(pd.to_numeric, errors="coerce")
    valid_rows = timestamps.notna() & numeric_tags.notna().all(axis=1)
    recovered = recovered.loc[valid_rows].copy()
    numeric_tags = numeric_tags.loc[valid_rows]
    if recovered.empty:
        raise original_error

    unique_rows = ~recovered.duplicated(keep="first")
    recovered = recovered.loc[unique_rows].copy()
    numeric_tags = numeric_tags.loc[recovered.index]
    recovered = recovered.reset_index(drop=True)
    for column in recognized_tags:
        recovered[column] = numeric_tags[column].to_numpy()

    # Count malformed rows skipped by the CSV parser as well as invalid parsed
    # rows. The supplied file is a one-record-per-line CSV.
    with path.open("rb") as source:
        source_data_lines = max(sum(1 for _ in source) - 1, 0)
    excluded_rows = max(source_data_lines - len(recovered), 0)
    recovered.attrs["source_records_excluded"] = excluded_rows
    recovered.attrs["source_recovered"] = True
    return recovered

def clean_dataset(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.drop_duplicates()
    if "record_time" in df.columns:
        df["record_time"] = pd.to_datetime(df["record_time"], errors="coerce")
        # Numeric timestamp feature, while retaining the original column for display.
        df["record_time_unix"] = pd.to_numeric(df["record_time"].astype("int64"), errors="coerce") / 10**9
    numeric = df.select_dtypes(include=np.number).columns.tolist()
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().all():
            df[col] = 0.0
        else:
            df[col] = df[col].fillna(df[col].median())
    # Convert non-numeric fields into stable string categories.
    for col in df.columns:
        if col not in numeric and col != "record_time":
            df[col] = df[col].fillna("Unknown").astype(str)
    return df

def train_regressor(df, target, features, algorithm):
    work = clean_dataset(df)
    if target not in work.columns:
        raise ValueError("Target column not found.")
    features = [f for f in features if f in work.columns and f != target]
    if not features:
        raise ValueError("Select at least one feature other than the target.")

    X = work[features].copy()
    y = pd.to_numeric(work[target], errors="coerce")
    valid = y.notna()
    X, y = X.loc[valid], y.loc[valid]
    if len(y) < 5:
        raise ValueError("At least 5 valid target records are required for training.")

    # Keep the implementation deterministic for repeatable academic evaluation.
    categorical = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
    numeric = [c for c in X.columns if c not in categorical]
    X = pd.get_dummies(X, columns=categorical, dummy_na=True)
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0)
    scaler = StandardScaler()
    if numeric:
        X[numeric] = scaler.fit_transform(X[numeric])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )
    if algorithm == "LINEAR_REGRESSION":
        model = LinearRegression()
    else:
        model = RandomForestRegressor(
            n_estimators=100,
            max_depth=16,
            min_samples_leaf=3,
            max_features="sqrt",
            random_state=42,
            n_jobs=-1,
        )
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    metrics = {
        "MAE": float(mean_absolute_error(y_test, pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_test, pred))),
        "R2": float(r2_score(y_test, pred)),
        "training_rows": int(len(X_train)),
        "testing_rows": int(len(X_test)),
    }
    bundle = {
        "model": model,
        "features": list(X.columns),
        "raw_features": features,
        "numeric_features": numeric,
        "scaler": scaler,
        "target": target,
    }
    return bundle, metrics, pd.DataFrame({"actual": y_test.values, "predicted": pred})

def predict_one(bundle, row):
    model = bundle["model"]
    raw_features = bundle["raw_features"]
    frame = pd.DataFrame([row])
    for col in raw_features:
        if col not in frame.columns:
            frame[col] = 0
    frame = frame[raw_features].copy()
    categorical = [c for c in frame.columns if not pd.api.types.is_numeric_dtype(frame[c])]
    numeric = [c for c in frame.columns if c not in categorical]
    frame = pd.get_dummies(frame, columns=categorical, dummy_na=True)
    frame = frame.reindex(columns=bundle["features"], fill_value=0)
    if numeric:
        # scaler was fitted on numeric columns; absent one-hot columns are ignored.
        numeric_present = [c for c in numeric if c in frame.columns]
        if numeric_present:
            frame[numeric_present] = bundle["scaler"].transform(
                frame[numeric_present]
            )
    return float(model.predict(frame)[0])
