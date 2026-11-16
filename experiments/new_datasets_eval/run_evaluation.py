"""
CAR OS - Experimental Evaluation of New Candidate Datasets
Evaluates:
  1. toyota_car_os_dataset.csv
  2. train_set.csv
  3. test_set.csv

Strictly isolated in experiments/new_datasets_eval/ to avoid affecting production models.
"""
import os
import json
import numpy as np
import pandas as pd
import joblib

from sklearn.preprocessing import StandardScaler, OneHotEncoder, OrdinalEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report,
    r2_score, mean_absolute_error, mean_squared_error
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUTPUT_DIR, exist_ok=True)


def inspect_datasets():
    results = {}
    files = {
        "toyota": os.path.join(BASE_DIR, "toyota_car_os_dataset.csv"),
        "train": os.path.join(BASE_DIR, "train_set.csv"),
        "test": os.path.join(BASE_DIR, "test_set.csv")
    }

    for key, path in files.items():
        df = pd.read_csv(path)
        col_info = {}
        for col in df.columns:
            col_info[col] = {
                "dtype": str(df[col].dtype),
                "null_count": int(df[col].isnull().sum()),
                "nunique": int(df[col].nunique()),
                "sample_values": [str(x) for x in df[col].dropna().head(3).tolist()]
            }
            if pd.api.types.is_numeric_dtype(df[col]):
                col_info[col].update({
                    "min": float(df[col].min()),
                    "max": float(df[col].max()),
                    "mean": float(df[col].mean()),
                    "std": float(df[col].std())
                })
        results[key] = {
            "shape": list(df.shape),
            "duplicates": int(df.duplicated().sum()),
            "columns": col_info
        }

    # Train vs Test compatibility
    train_df = pd.read_csv(files["train"])
    test_df = pd.read_csv(files["test"])
    overlap = len(pd.merge(train_df, test_df, how="inner"))
    col_diff = list(set(train_df.columns).symmetric_difference(set(test_df.columns)))
    
    cat_match = {}
    for c in train_df.select_dtypes(include=["object"]).columns:
        tr_cats = set(train_df[c].unique())
        te_cats = set(test_df[c].unique())
        cat_match[c] = {
            "match": tr_cats == te_cats,
            "train_only": list(tr_cats - te_cats),
            "test_only": list(te_cats - tr_cats)
        }

    results["train_test_compatibility"] = {
        "column_diff": col_diff,
        "exact_row_overlap": overlap,
        "categorical_match": cat_match,
        "train_target_dist": {str(k): int(v) for k, v in train_df["Need_Maintenance"].value_counts().items()},
        "test_target_dist": {str(k): int(v) for k, v in test_df["Need_Maintenance"].value_counts().items()}
    }
    return results


def evaluate_maintenance_classifiers():
    train_path = os.path.join(BASE_DIR, "train_set.csv")
    test_path = os.path.join(BASE_DIR, "test_set.csv")
    
    train_df = pd.read_csv(train_path)
    test_df = pd.read_csv(test_path)

    target = "Need_Maintenance"
    features = [c for c in train_df.columns if c != target]

    cat_cols = ["Vehicle_Model", "Maintenance_History", "Fuel_Type", "Transmission_Type", "Owner_Type", "Tire_Condition"]
    num_cols = [c for c in features if c not in cat_cols]

    X_train = train_df[features]
    y_train = train_df[target]
    X_test = test_df[features]
    y_test = test_df[target]

    # 1. Majority Class Baseline
    dummy = DummyClassifier(strategy="most_frequent")
    dummy.fit(X_train, y_train)
    y_pred_dummy = dummy.predict(X_test)

    # 2. Logistic Regression Baseline
    lr_preprocessor = ColumnTransformer([
        ("num", StandardScaler(), num_cols),
        ("cat", OneHotEncoder(drop="first", sparse_output=False), cat_cols)
    ])
    lr_pipeline = Pipeline([
        ("prep", lr_preprocessor),
        ("clf", LogisticRegression(max_iter=1000, random_state=42))
    ])
    lr_pipeline.fit(X_train, y_train)
    y_pred_lr = lr_pipeline.predict(X_test)

    # 3. Random Forest Baseline
    rf_preprocessor = ColumnTransformer([
        ("num", StandardScaler(), num_cols),
        ("cat", OrdinalEncoder(), cat_cols)
    ])
    rf_pipeline = Pipeline([
        ("prep", rf_preprocessor),
        ("clf", RandomForestClassifier(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1))
    ])
    rf_pipeline.fit(X_train, y_train)
    y_pred_rf = rf_pipeline.predict(X_test)

    # Feature importances from RF
    rf_model = rf_pipeline.named_steps["clf"]
    feat_importances = dict(zip(num_cols + cat_cols, [float(x) for x in rf_model.feature_importances_]))
    feat_importances_sorted = dict(sorted(feat_importances.items(), key=lambda item: item[1], reverse=True))

    # Save models in experimental directory
    joblib.dump(lr_pipeline, os.path.join(OUTPUT_DIR, "need_maintenance_lr_baseline.joblib"))
    joblib.dump(rf_pipeline, os.path.join(OUTPUT_DIR, "need_maintenance_rf_baseline.joblib"))

    def compute_metrics(y_true, y_pred):
        return {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
            "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
            "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
            "precision_class_1": float(precision_score(y_true, y_pred, pos_label=1, zero_division=0)),
            "recall_class_1": float(recall_score(y_true, y_pred, pos_label=1, zero_division=0)),
            "f1_class_1": float(f1_score(y_true, y_pred, pos_label=1, zero_division=0)),
            "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
            "classification_report": classification_report(y_true, y_pred, output_dict=True)
        }

    return {
        "majority_class_baseline": compute_metrics(y_test, y_pred_dummy),
        "logistic_regression": compute_metrics(y_test, y_pred_lr),
        "random_forest": compute_metrics(y_test, y_pred_rf),
        "feature_importances": feat_importances_sorted
    }


def evaluate_toyota_pricing():
    toyota_path = os.path.join(BASE_DIR, "toyota_car_os_dataset.csv")
    df = pd.read_csv(toyota_path)

    features = ["model", "year", "transmission", "mileage", "fuelType", "tax", "mpg", "engineSize"]
    target = "price"

    X = df[features]
    y = df[target]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    cat_cols = ["model", "transmission", "fuelType"]
    num_cols = ["year", "mileage", "tax", "mpg", "engineSize"]

    preprocessor = ColumnTransformer([
        ("num", StandardScaler(), num_cols),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols)
    ])

    # 1. Ridge Baseline
    ridge_pipe = Pipeline([
        ("prep", preprocessor),
        ("reg", Ridge(alpha=1.0))
    ])
    ridge_pipe.fit(X_train, y_train)
    y_pred_ridge = ridge_pipe.predict(X_test)

    # 2. Gradient Boosting Regressor
    gbr_pipe = Pipeline([
        ("prep", preprocessor),
        ("reg", GradientBoostingRegressor(n_estimators=150, max_depth=5, random_state=42))
    ])
    gbr_pipe.fit(X_train, y_train)
    y_pred_gbr = gbr_pipe.predict(X_test)

    joblib.dump(gbr_pipe, os.path.join(OUTPUT_DIR, "toyota_price_gbr.joblib"))

    return {
        "dataset_currency": "GBP (£) [UK Used Car Market provenance]",
        "dataset_distance_unit": "Miles",
        "dataset_fuel_efficiency_unit": "Imperial MPG",
        "mean_price_gbp": float(y_test.mean()),
        "ridge_regression": {
            "r2": float(r2_score(y_test, y_pred_ridge)),
            "mae_gbp": float(mean_absolute_error(y_test, y_pred_ridge)),
            "rmse_gbp": float(mean_squared_error(y_test, y_pred_ridge)**0.5),
            "mae_pct_of_mean": float(mean_absolute_error(y_test, y_pred_ridge) / y_test.mean() * 100)
        },
        "gradient_boosting": {
            "r2": float(r2_score(y_test, y_pred_gbr)),
            "mae_gbp": float(mean_absolute_error(y_test, y_pred_gbr)),
            "rmse_gbp": float(mean_squared_error(y_test, y_pred_gbr)**0.5),
            "mae_pct_of_mean": float(mean_absolute_error(y_test, y_pred_gbr) / y_test.mean() * 100)
        }
    }


def main():
    print("Executing CAR OS new datasets evaluation...")
    data_summary = inspect_datasets()
    maint_results = evaluate_maintenance_classifiers()
    toyota_results = evaluate_toyota_pricing()

    all_results = {
        "data_summary": data_summary,
        "maintenance_classification": maint_results,
        "toyota_price_prediction": toyota_results
    }

    out_file = os.path.join(OUTPUT_DIR, "evaluation_summary.json")
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"Evaluation complete! Results saved to {out_file}")


if __name__ == "__main__":
    main()
