"""
ML prediction module for CAR OS.

Model status indicators clearly distinguish:
- rule_based: deterministic formula (primary system)
- ml_synthetic: trained on synthetic data (demonstration only)
- ml_real: would indicate real trained model (not yet available)
"""
import os
import numpy as np

MODELS_DIR = os.path.join(os.path.dirname(__file__), "saved_models")

MODEL_STATUS = {
    "health": "rule_based",       # Primary: deterministic formula
    "resale": "rule_based",       # Primary: deterministic formula
    "fuel_efficiency": "rule_based",
}


def _load_model(filename: str):
    """Load a saved model, returning None if not found."""
    path = os.path.join(MODELS_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        import joblib
        return joblib.load(path)
    except Exception:
        return None


def get_ml_model_status() -> dict:
    """Return the current status of all ML models."""
    health_bundle = _load_model("health_classifier.pkl")
    resale_bundle = _load_model("resale_regressor.pkl")
    fuel_bundle = _load_model("fuel_efficiency_regressor.pkl")

    cardekho_bundle = _load_model("resale_regressor_cardekho_v1.pkl")

    return {
        "health_classifier": {
            "available": health_bundle is not None,
            "data_type": health_bundle.get("data_type", "N/A") if health_bundle else "N/A",
            "metrics": health_bundle.get("metrics", {}) if health_bundle else {},
            "status_label": "ML (Synthetic Demo)" if health_bundle else "Rule-Based",
        },
        "resale_regressor": {
            "available": resale_bundle is not None,
            "data_type": resale_bundle.get("data_type", "N/A") if resale_bundle else "N/A",
            "metrics": resale_bundle.get("metrics", {}) if resale_bundle else {},
            "status_label": "ML (Synthetic Demo)" if resale_bundle else "Rule-Based",
        },
        "cardekho_resale_regressor": {
            "available": cardekho_bundle is not None,
            "data_type": cardekho_bundle.get("data_type", "N/A") if cardekho_bundle else "N/A",
            "metrics": cardekho_bundle.get("metrics", {}) if cardekho_bundle else {},
            "status_label": "ML (Trained on CarDekho Indian Market Data)" if cardekho_bundle else "Not Available",
            "version": cardekho_bundle.get("version", "1.0.0") if cardekho_bundle else "N/A",
            "temporal_limitation": "Trained on historical CarDekho Indian used car listings (up to 2020)."
        },
        "fuel_efficiency_regressor": {
            "available": fuel_bundle is not None,
            "data_type": fuel_bundle.get("data_type", "N/A") if fuel_bundle else "N/A",
            "metrics": fuel_bundle.get("metrics", {}) if fuel_bundle else {},
            "status_label": "Synthetic ML Demo (Negligible Predictive Power R²=0.018)",
            "academic_limitation": "R²=0.0182 indicates negligible explanatory power. Primary fuel/energy economy is strictly calculated via deterministic arithmetic (distance / quantity).",
        },
        "primary_engine": "Rule-Based (deterministic formulas) with Empirical CarDekho ML option",
        "notice": (
            "Empirical CarDekho resale model trained on verified Indian used car listings. "
            "Rule-based formulas remain available as fallback and verification baseline."
        ),
    }


def predict_resale_cardekho_ml(make: str, model: str, year: int, odometer_km: float,
                               fuel_type: str = "Petrol", transmission: str = "Manual",
                               owner: str = "First Owner", health_score: float = 80.0) -> dict | None:
    """
    Predict resale value using the empirical CarDekho Indian ML regression model.
    Returns None if the artifact is missing or an error occurs.
    """
    from services.valuation_service import calculate_cardekho_resale_value
    return calculate_cardekho_resale_value(
        make=make, model=model, manufacturing_year=year,
        odometer_km=odometer_km, fuel_type=fuel_type, transmission=transmission,
        owner=owner, health_score=health_score
    )


def predict_health_ml(age: int, odometer: float, reported_issues: int,
                       service_history: str, fuel_type: str) -> dict | None:
    """
    Predict health status using the ML classifier, if available.
    Returns None if model not available.
    """
    bundle = _load_model("health_classifier.pkl")
    if bundle is None:
        return None

    try:
        sh_le = bundle["sh_le"]
        ft_le = bundle["ft_le"]
        model = bundle["model"]

        sh_enc = sh_le.transform([service_history])[0]
        ft_enc = ft_le.transform([fuel_type])[0]
        X = np.array([[age, odometer, reported_issues, sh_enc, ft_enc]])
        prediction = model.predict(X)[0]
        proba = model.predict_proba(X)[0]

        return {
            "prediction": prediction,
            "confidence": float(max(proba)),
            "data_type": bundle.get("data_type", "SYNTHETIC"),
            "warning": "Prediction based on synthetic demonstration data — not validated on real data.",
        }
    except Exception as e:
        return {"error": str(e)}
