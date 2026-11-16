"""
ML training pipelines for CAR OS.

IMPORTANT: No real-world labelled dataset is available.
The code below uses synthetic demonstration data, clearly labelled as such.
Do not treat model metrics as reflecting real-world performance.
Models are saved only when trained; the rule-based system remains the
primary engine until suitable real data is available.
"""
import os
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    classification_report, confusion_matrix,
    mean_absolute_error, mean_squared_error, r2_score
)

MODELS_DIR = os.path.join(os.path.dirname(__file__), "saved_models")
os.makedirs(MODELS_DIR, exist_ok=True)

SYNTHETIC_DATA_WARNING = (
    "[WARNING] SYNTHETIC DATA: The following model was trained on synthetically generated "
    "demonstration data. Metrics do NOT reflect real-world performance. "
    "Replace with real labelled data before using in production."
)

FUEL_TYPES = ["Petrol", "Diesel", "CNG", "Hybrid", "Electric"]
SERVICE_HISTORIES = ["Full", "Partial", "None", "Unknown"]


def _generate_synthetic_vehicles(n=500, seed=42):
    """Generate synthetic vehicle data for demonstration purposes only."""
    rng = np.random.default_rng(seed)

    # More balanced synthetic fleet distribution (young, mid-age, older cars)
    age = rng.integers(0, 15, n)
    odometer = rng.integers(1000, 180000, n).astype(float)
    reported_issues = rng.choice([0, 1, 2, 3, 4, 5], p=[0.40, 0.25, 0.15, 0.10, 0.05, 0.05], size=n)
    service_history = rng.choice(SERVICE_HISTORIES, p=[0.45, 0.30, 0.15, 0.10], size=n)
    fuel_type = rng.choice(FUEL_TYPES, size=n)

    # Synthetic health score (mirrors rule-based formula)
    sh_penalty = np.array([{"Full": 0, "Partial": 10, "None": 20, "Unknown": 10}[s]
                            for s in service_history])
    age_pen = np.minimum(age * 3, 30)
    mileage_pen = np.minimum((odometer // 10000) * 2, 30)
    issue_pen = np.minimum(reported_issues * 10, 40)
    raw_health = 100 - age_pen - mileage_pen - sh_penalty - issue_pen
    raw_health = raw_health + rng.normal(0, 2, n)  # small measurement noise
    health_score = np.clip(raw_health, 0, 100)

    # Health status labels
    health_status = np.where(health_score >= 80, "Healthy",
                    np.where(health_score >= 50, "Attention", "Critical"))

    # Synthetic resale value
    base_price = rng.choice([700000, 800000, 900000, 1200000, 1500000], n)
    age_factor = np.maximum(0.25, 1 - age * 0.08)
    mil_factor = np.maximum(0.55, 1 - (odometer // 10000) * 0.025)
    cond_factor = 0.60 + (health_score / 100) * 0.40
    resale = base_price * age_factor * mil_factor * cond_factor
    resale += rng.normal(0, 30000, n)
    resale = np.maximum(resale, 50000)

    # Synthetic fuel efficiency
    base_eff = np.where(
        np.isin(fuel_type, ["Petrol", "Diesel"]), rng.uniform(10, 20, n),
        np.where(fuel_type == "CNG", rng.uniform(15, 25, n),
        np.where(fuel_type == "Hybrid", rng.uniform(18, 28, n),
                 rng.uniform(5, 10, n)))  # Electric: km/kWh
    )
    fuel_eff = base_eff - age * 0.2 - reported_issues * 0.5
    fuel_eff = np.maximum(fuel_eff, 1.0)

    return {
        "age": age, "odometer": odometer, "reported_issues": reported_issues,
        "service_history": service_history, "fuel_type": fuel_type,
        "health_score": health_score, "health_status": health_status,
        "resale_value": resale, "fuel_efficiency": fuel_eff,
    }


def _encode_categoricals(service_history, fuel_type):
    """One-hot encode categorical features."""
    sh_le = LabelEncoder().fit(SERVICE_HISTORIES)
    ft_le = LabelEncoder().fit(FUEL_TYPES)
    sh_encoded = sh_le.transform(service_history)
    ft_encoded = ft_le.transform(fuel_type)
    return sh_encoded, ft_encoded, sh_le, ft_le


def train_health_classifier():
    """Train a health status classifier (Healthy/Attention/Critical)."""
    print(SYNTHETIC_DATA_WARNING)
    data = _generate_synthetic_vehicles(n=800)
    sh_enc, ft_enc, sh_le, ft_le = _encode_categoricals(
        data["service_history"], data["fuel_type"]
    )

    X = np.column_stack([
        data["age"], data["odometer"], data["reported_issues"],
        sh_enc, ft_enc,
    ])
    y = data["health_status"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced")),
    ])
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    print("\n=== Health Classifier (SYNTHETIC DATA) ===")
    print(classification_report(y_test, y_pred))
    print("Confusion Matrix:")
    print(confusion_matrix(y_test, y_pred, labels=["Healthy", "Attention", "Critical"]))

    labels = ["Healthy", "Attention", "Critical"]
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    unique_classes, counts = np.unique(y, return_counts=True)
    metrics = {
        "report": classification_report(y_test, y_pred, output_dict=True),
        "confusion_matrix": cm.tolist(),
        "labels": labels,
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "features": ["age", "odometer", "reported_issues", "service_history", "fuel_type"],
        "class_distribution": {str(k): int(v) for k, v in zip(unique_classes, counts)},
    }
    joblib.dump({
        "model": model, "sh_le": sh_le, "ft_le": ft_le,
        "metrics": metrics, "data_type": "SYNTHETIC",
        "features": metrics["features"],
        "target": "health_status",
    }, os.path.join(MODELS_DIR, "health_classifier.pkl"))
    print("Saved: health_classifier.pkl")
    return metrics


def train_resale_regressor():
    """Train a resale value regression model."""
    print(SYNTHETIC_DATA_WARNING)
    data = _generate_synthetic_vehicles(n=800)
    sh_enc, ft_enc, sh_le, ft_le = _encode_categoricals(
        data["service_history"], data["fuel_type"]
    )

    X = np.column_stack([
        data["age"], data["odometer"], data["reported_issues"],
        data["health_score"], sh_enc, ft_enc,
    ])
    y = data["resale_value"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("reg", GradientBoostingRegressor(n_estimators=100, random_state=42)),
    ])
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    mae = mean_absolute_error(y_test, y_pred)
    rmse = mean_squared_error(y_test, y_pred) ** 0.5
    r2 = r2_score(y_test, y_pred)

    print("\n=== Resale Regressor (SYNTHETIC DATA) ===")
    print(f"MAE:  Rs. {mae:,.0f}")
    print(f"RMSE: Rs. {rmse:,.0f}")
    print(f"R2:   {r2:.4f}")

    metrics = {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "features": ["age", "odometer", "reported_issues", "health_score", "service_history", "fuel_type"],
    }
    joblib.dump({
        "model": model, "sh_le": sh_le, "ft_le": ft_le,
        "metrics": metrics, "data_type": "SYNTHETIC",
        "features": metrics["features"],
        "target": "resale_value",
    }, os.path.join(MODELS_DIR, "resale_regressor.pkl"))
    print("Saved: resale_regressor.pkl")
    return metrics


def train_fuel_efficiency_regressor():
    """Train a fuel efficiency regression model."""
    print(SYNTHETIC_DATA_WARNING)
    data = _generate_synthetic_vehicles(n=800)
    sh_enc, ft_enc, sh_le, ft_le = _encode_categoricals(
        data["service_history"], data["fuel_type"]
    )

    X = np.column_stack([
        data["age"], data["odometer"], data["reported_issues"],
        data["health_score"], ft_enc,
    ])
    y = data["fuel_efficiency"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("reg", Ridge(alpha=1.0)),
    ])
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    mae = mean_absolute_error(y_test, y_pred)
    rmse = mean_squared_error(y_test, y_pred) ** 0.5
    r2 = r2_score(y_test, y_pred)

    print("\n=== Fuel Efficiency Regressor (SYNTHETIC DATA) ===")
    print(f"MAE:  {mae:.2f} km/unit")
    print(f"RMSE: {rmse:.2f} km/unit")
    print(f"R2:   {r2:.4f}")

    metrics = {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
        "features": ["age", "odometer", "reported_issues", "health_score", "fuel_type"],
    }
    joblib.dump({
        "model": model, "ft_le": ft_le,
        "metrics": metrics, "data_type": "SYNTHETIC",
        "features": metrics["features"],
        "target": "fuel_efficiency",
    }, os.path.join(MODELS_DIR, "fuel_efficiency_regressor.pkl"))
    print("Saved: fuel_efficiency_regressor.pkl")
    return metrics


def train_indian_resale_model():
    """Train the versioned CarDekho Indian resale regression model."""
    from ml.train_indian_resale import train_cardekho_resale_model
    return train_cardekho_resale_model()


if __name__ == "__main__":
    print("Training all CAR OS ML models...")
    train_health_classifier()
    train_resale_regressor()
    train_fuel_efficiency_regressor()
    print("\nTraining empirical Indian CarDekho resale regression model...")
    train_indian_resale_model()
    print("\nAll models trained and saved.")
