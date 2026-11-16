"""
CAR OS - Training Pipeline for Indian Used Car Resale Model
Trained on CarDekho dataset: dataset/CAR DETAILS FROM CAR DEKHO.csv

Preserves original data, eliminates exact duplicates (763 rows),
adheres to strict featurization ordering (train/test split before fitting),
and saves a versioned artifact: ml/saved_models/resale_regressor_cardekho_v1.pkl
"""
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.pipeline import Pipeline
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_PATH = os.path.join(BASE_DIR, "dataset", "CAR DETAILS FROM CAR DEKHO.csv")
MODELS_DIR = os.path.join(BASE_DIR, "ml", "saved_models")
MODEL_FILENAME = "resale_regressor_cardekho_v1.pkl"
MODEL_PATH = os.path.join(MODELS_DIR, MODEL_FILENAME)


def load_and_clean_cardekho(dataset_path: str = DATASET_PATH) -> tuple[pd.DataFrame, dict]:
    """
    Load CarDekho CSV with explicit validation and drop exact duplicate rows
    without modifying the underlying source file.
    """
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"CarDekho dataset not found at {dataset_path}")

    # Load with explicit string and numeric parsing
    df_raw = pd.read_csv(
        dataset_path,
        dtype={
            "name": str,
            "year": int,
            "selling_price": float,
            "km_driven": float,
            "fuel": str,
            "seller_type": str,
            "transmission": str,
            "owner": str,
        }
    )
    raw_count = len(df_raw)
    dup_count = int(df_raw.duplicated().sum())

    # Drop exact duplicate rows
    df = df_raw.drop_duplicates().reset_index(drop=True)
    clean_count = len(df)

    # Feature extraction
    df["make"] = df["name"].apply(lambda x: str(x).split()[0].strip().title())
    df["model_family"] = df["name"].apply(
        lambda x: str(x).split()[1].strip().title() if len(str(x).split()) > 1 else "Other"
    )
    # Reference year for training data is 2020 (when dataset was collected)
    df["vehicle_age"] = (2020 - df["year"]).clip(lower=0)

    audit_meta = {
        "raw_row_count": raw_count,
        "duplicate_rows_removed": dup_count,
        "clean_row_count": clean_count,
        "columns": list(df.columns),
        "brands_count": int(df["make"].nunique()),
        "models_count": int(df["model_family"].nunique()),
        "min_price_inr": float(df["selling_price"].min()),
        "median_price_inr": float(df["selling_price"].median()),
        "max_price_inr": float(df["selling_price"].max()),
        "min_km": float(df["km_driven"].min()),
        "median_km": float(df["km_driven"].median()),
        "max_km": float(df["km_driven"].max()),
    }
    return df, audit_meta


def train_cardekho_resale_model(dataset_path: str = DATASET_PATH, save_artifact: bool = True) -> dict:
    """
    Train and evaluate the Indian used-car resale regression model.
    Compares Baseline Dummy, Ridge, and Log-Transformed GradientBoosting.
    """
    df, audit_meta = load_and_clean_cardekho(dataset_path)

    features = [
        "make", "model_family", "year", "vehicle_age", "km_driven",
        "fuel", "seller_type", "transmission", "owner"
    ]
    target = "selling_price"

    X = df[features]
    y = df[target]

    # Strict featurization ordering: split train and test sets BEFORE any preprocessing
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )

    cat_cols = ["make", "model_family", "fuel", "seller_type", "transmission", "owner"]
    num_cols = ["year", "vehicle_age", "km_driven"]

    preprocessor = ColumnTransformer([
        ("num", StandardScaler(), num_cols),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols)
    ])

    # 1. Baseline: Median Dummy Regressor
    dummy = DummyRegressor(strategy="median")
    dummy.fit(X_train, y_train)
    y_pred_dummy = dummy.predict(X_test)
    dummy_mae = mean_absolute_error(y_test, y_pred_dummy)
    dummy_rmse = mean_squared_error(y_test, y_pred_dummy) ** 0.5
    dummy_r2 = r2_score(y_test, y_pred_dummy)

    # 2. Linear Baseline: Ridge Regression
    ridge_pipeline = Pipeline([
        ("prep", preprocessor),
        ("reg", Ridge(alpha=1.0))
    ])
    ridge_pipeline.fit(X_train, y_train)
    y_pred_ridge = ridge_pipeline.predict(X_test)
    ridge_mae = mean_absolute_error(y_test, y_pred_ridge)
    ridge_rmse = mean_squared_error(y_test, y_pred_ridge) ** 0.5
    ridge_r2 = r2_score(y_test, y_pred_ridge)

    # 3. Primary Production Model: Log-Transformed Gradient Boosting Regressor
    # Target prices have positive skew; log1p transformation stabilizes heteroscedastic variance
    log_gbr = TransformedTargetRegressor(
        regressor=Pipeline([
            ("prep", preprocessor),
            ("reg", GradientBoostingRegressor(n_estimators=200, max_depth=5, random_state=42))
        ]),
        func=np.log1p,
        inverse_func=np.expm1
    )
    log_gbr.fit(X_train, y_train)
    y_pred_gbr = log_gbr.predict(X_test)

    gbr_mae = mean_absolute_error(y_test, y_pred_gbr)
    gbr_rmse = mean_squared_error(y_test, y_pred_gbr) ** 0.5
    gbr_r2 = r2_score(y_test, y_pred_gbr)

    # Median Absolute Percentage Error (MAPE)
    mape = float(np.median(np.abs((y_test - y_pred_gbr) / y_test)) * 100)

    # Feature names and known categories for safe validation
    known_makes = sorted(df["make"].unique().tolist())
    known_models = sorted(df["model_family"].unique().tolist())

    metrics = {
        "dummy_baseline": {
            "mae": float(dummy_mae),
            "rmse": float(dummy_rmse),
            "r2": float(dummy_r2),
        },
        "ridge_regression": {
            "mae": float(ridge_mae),
            "rmse": float(ridge_rmse),
            "r2": float(ridge_r2),
        },
        "gradient_boosting_primary": {
            "mae": float(gbr_mae),
            "rmse": float(gbr_rmse),
            "r2": float(gbr_r2),
            "median_absolute_percentage_error": mape,
        },
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "data_audit": audit_meta,
        "features": features,
        "known_makes": known_makes,
        "known_models": known_models,
        "version": "1.0.0",
        "currency": "INR (₹)",
        "distance_unit": "Kilometres",
        "market": "Indian Used Car Market (CarDekho)",
        "temporal_limitation": (
            "Dataset represents historical Indian market listings up to year 2020. "
            "Estimates serve as an empirical structural depreciation model; current 2026 "
            "market prices may be higher due to inflation, revised tax regimes, and supply constraints."
        )
    }

    if save_artifact:
        os.makedirs(MODELS_DIR, exist_ok=True)
        artifact = {
            "model": log_gbr,
            "metrics": metrics["gradient_boosting_primary"],
            "features": features,
            "known_makes": known_makes,
            "known_models": known_models,
            "metadata": metrics,
            "data_type": "REAL_INDIAN_MARKET",
            "source": "CarDekho Used Car Dataset (India)",
            "version": "1.0.0",
        }
        joblib.dump(artifact, MODEL_PATH)
        print(f"Versioned resale model saved to: {MODEL_PATH}")

    return metrics


if __name__ == "__main__":
    print("Training CarDekho Indian Used Car Resale Model...")
    res = train_cardekho_resale_model()
    print("\n--- Training Complete ---")
    print(f"Train samples: {res['train_samples']}, Test samples: {res['test_samples']}")
    print(f"Dummy Baseline MAE:  Rs. {res['dummy_baseline']['mae']:,.2f}")
    print(f"Ridge Regression MAE: Rs. {res['ridge_regression']['mae']:,.2f} (R2: {res['ridge_regression']['r2']:.4f})")
    print(f"Primary GBR MAE:      Rs. {res['gradient_boosting_primary']['mae']:,.2f} (R2: {res['gradient_boosting_primary']['r2']:.4f})")
    print(f"Median Error %:       {res['gradient_boosting_primary']['median_absolute_percentage_error']:.2f}%")
