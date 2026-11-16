"""
CAR OS – ML Model Evaluation & Audit Report
Systematically inspects and evaluates saved machine learning models.
Reports prediction target, input features, dataset source, preprocessing,
train/test split, class distribution, and formal metrics.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import joblib

MODELS_DIR = os.path.join(os.path.dirname(__file__), "saved_models")


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Simple ASCII table formatter for CLI output."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(cell)))

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_str = "| " + " | ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers)) + " |"

    lines = [sep, header_str, sep]
    for row in rows:
        line = "| " + " | ".join(f"{str(cell):<{col_widths[i]}}" for i, cell in enumerate(row)) + " |"
        lines.append(line)
    lines.append(sep)
    return "\n".join(lines)


def evaluate_health_classifier() -> dict | None:
    path = os.path.join(MODELS_DIR, "health_classifier.pkl")
    if not os.path.exists(path):
        print("[!] Health classifier model not found. Run python ml/train_models.py to train.")
        return None

    bundle = joblib.load(path)
    metrics = bundle.get("metrics", {})
    report = metrics.get("report", {})
    cm = metrics.get("confusion_matrix", [])
    labels = metrics.get("labels", ["Healthy", "Attention", "Critical"])

    print("\n" + "=" * 70)
    print("1. MODEL AUDIT: Vehicle Health Status Classifier")
    print("=" * 70)
    print(f"Target Variable:       health_status (Healthy | Attention | Critical)")
    print(f"Algorithm:             RandomForestClassifier(n_estimators=100, class_weight='balanced')")
    print(f"Input Features:        {bundle.get('features', ['age', 'odometer', 'reported_issues', 'service_history', 'fuel_type'])}")
    print(f"Training Data Type:    {bundle.get('data_type', 'SYNTHETIC')} DEMONSTRATION DATA")
    print(f"Dataset Size:          {metrics.get('train_samples', 640)} train / {metrics.get('test_samples', 160)} test (80/20 Stratified Split)")
    print(f"Preprocessing:         StandardScaler (numeric), LabelEncoder (service_history, fuel_type)")
    print(f"Saved Model File:      {path}")
    print(f"Inference Endpoint:    ml.predict.predict_health_ml() & /api/ml/status")
    print(f"Primary Application:   Advisory comparison alongside deterministic formula in health_service.py")

    print("\n--- Class Distribution (Dataset-wide) ---")
    dist = metrics.get("class_distribution", {})
    for cls_name, count in dist.items():
        print(f"  - {cls_name:<12}: {count:>4} samples ({count / sum(dist.values()) * 100:.1f}%)")

    print("\n--- Test Set Classification Performance ---")
    headers = ["Class", "Precision", "Recall", "F1-Score", "Support"]
    rows = []
    for lbl in labels:
        if lbl in report:
            rows.append([
                lbl,
                f"{report[lbl]['precision']:.3f}",
                f"{report[lbl]['recall']:.3f}",
                f"{report[lbl]['f1-score']:.3f}",
                str(int(report[lbl]['support'])),
            ])
    if "accuracy" in report:
        rows.append(["Overall Accuracy", "-", "-", f"{report['accuracy']:.3f}", str(int(report['macro avg']['support']))])
    if "macro avg" in report:
        rows.append(["Macro Average", f"{report['macro avg']['precision']:.3f}", f"{report['macro avg']['recall']:.3f}", f"{report['macro avg']['f1-score']:.3f}", str(int(report['macro avg']['support']))])
    if "weighted avg" in report:
        rows.append(["Weighted Average", f"{report['weighted avg']['precision']:.3f}", f"{report['weighted avg']['recall']:.3f}", f"{report['weighted avg']['f1-score']:.3f}", str(int(report['weighted avg']['support']))])
    print(format_table(headers, rows))

    if cm:
        print("\n--- Confusion Matrix ---")
        print(f"Row: Actual, Column: Predicted [Labels: {', '.join(labels)}]")
        for i, row in enumerate(cm):
            print(f"  Actual {labels[i]:<10}: {row}")

    print("\n[NOTE] As disclosed in literature survey paper 12, real automotive failure datasets exhibit severe")
    print("class imbalance. Because this model was trained on synthetic demonstration data, these scores verify")
    print("pipeline execution and convergence, but DO NOT demonstrate real-world diagnostic accuracy.")
    return bundle


def evaluate_resale_regressor() -> dict | None:
    path = os.path.join(MODELS_DIR, "resale_regressor.pkl")
    if not os.path.exists(path):
        print("[!] Resale regressor model not found.")
        return None

    bundle = joblib.load(path)
    metrics = bundle.get("metrics", {})

    print("\n" + "=" * 70)
    print("2. MODEL AUDIT: Used Vehicle Resale Value Regressor")
    print("=" * 70)
    print("Target Variable:       resale_value (Continuous INR Rs.)")
    print(f"Algorithm:             GradientBoostingRegressor(n_estimators=100, random_state=42)")
    print(f"Input Features:        {bundle.get('features', ['age', 'odometer', 'reported_issues', 'health_score', 'service_history', 'fuel_type'])}")
    print(f"Training Data Type:    {bundle.get('data_type', 'SYNTHETIC')} DEMONSTRATION DATA")
    print(f"Dataset Size:          {metrics.get('train_samples', 640)} train / {metrics.get('test_samples', 160)} test (80/20 Random Split)")
    print(f"Preprocessing:         StandardScaler (numeric), LabelEncoder (categoricals)")
    print(f"Saved Model File:      {path}")
    print(f"Inference Integration: Exposed via /api/ml/status for transparency")

    print("\n--- Test Set Regression Performance ---")
    headers = ["Metric", "Value", "Unit / Meaning"]
    rows = [
        ["Mean Absolute Error (MAE)", f"Rs. {metrics.get('mae', 0):,.0f}", "Average absolute valuation error"],
        ["Root Mean Squared Error (RMSE)", f"Rs. {metrics.get('rmse', 0):,.0f}", "Penalizes large outlier valuation errors"],
        ["Coefficient of Determination (R2)", f"{metrics.get('r2', 0):.4f}", "Proportion of variance explained (0.0 to 1.0)"],
    ]
    print(format_table(headers, rows))
    return bundle


def evaluate_fuel_efficiency_regressor() -> dict | None:
    path = os.path.join(MODELS_DIR, "fuel_efficiency_regressor.pkl")
    if not os.path.exists(path):
        print("[!] Fuel efficiency regressor model not found.")
        return None

    bundle = joblib.load(path)
    metrics = bundle.get("metrics", {})

    print("\n" + "=" * 70)
    print("3. MODEL AUDIT: Fuel & Energy Efficiency Regressor")
    print("=" * 70)
    print(f"Target Variable:       fuel_efficiency (km/L for ICE, km/kWh for EV)")
    print(f"Algorithm:             Ridge(alpha=1.0)")
    print(f"Input Features:        {bundle.get('features', ['age', 'odometer', 'reported_issues', 'health_score', 'fuel_type'])}")
    print(f"Training Data Type:    {bundle.get('data_type', 'SYNTHETIC')} DEMONSTRATION DATA")
    print(f"Dataset Size:          {metrics.get('train_samples', 640)} train / {metrics.get('test_samples', 160)} test (80/20 Random Split)")
    print(f"Preprocessing:         StandardScaler, LabelEncoder (fuel_type)")
    print(f"Saved Model File:      {path}")
    print(f"Inference Integration: Exposed via /api/ml/status for transparency")

    print("\n--- Test Set Regression Performance ---")
    headers = ["Metric", "Value", "Unit / Meaning"]
    rows = [
        ["Mean Absolute Error (MAE)", f"{metrics.get('mae', 0):.2f}", "km/unit error"],
        ["Root Mean Squared Error (RMSE)", f"{metrics.get('rmse', 0):.2f}", "km/unit error"],
        ["Coefficient of Determination (R2)", f"{metrics.get('r2', 0):.4f}", "Proportion of variance explained (0.0 to 1.0)"],
    ]
    print(format_table(headers, rows))
    print("\n[CRITICAL ACADEMIC NOTE] With R^2 = 0.0182, this linear regression model demonstrates NEGLIGIBLE")
    print("explanatory power and NO useful predictive capability for real-world fuel economy.")
    print("CAR OS strictly segregates calculated fuel/energy economy (deterministic distance/quantity")
    print("arithmetic in services/fuel_service.py) from ML estimates. This model bundle is maintained")
    print("solely for demonstration of ML pipeline architecture on synthetic data.")
    return bundle


def evaluate_predictive_maintenance_feasibility():
    print("\n" + "=" * 70)
    print("4. AUDIT: Predictive Maintenance Model Training Feasibility")
    print("=" * 70)
    print("Dataset Inspected:     CAR_OS_Dataset_Service_History_VISIBLE.xlsx")
    print("Available Records:     32 service history entries (16 periodic service, 16 repairs)")
    print("Ground-Truth Failures: None (Records are classified only as scheduled service vs generic repair)")
    print("Run-to-failure series: None (No continuous sensor degradation signals or run-to-failure cycles)")
    print("Feasibility Decision:  [UNSUITABLE FOR SUPERVISED FAILURE PREDICTION]")
    print("Scientific Rationale:  Training an ML failure predictor on 32 demonstration rows without valid failure")
    print("                       labels would violate academic integrity. As established in literature survey")
    print("                       papers 1, 12 & 13, predictive maintenance requires either high-frequency")
    print("                       temporal telematics or thousands of labeled maintenance events with severe")
    print("                       class imbalance handling.")
    print("CAR OS Implementation: Rule-based maintenance scheduling (calendar & mileage thresholds + OBD")
    print("                       diagnostic triggers) is retained as the authoritative, explainable engine.")
    print("=" * 70)


if __name__ == "__main__":
    print("CAR OS — Comprehensive Machine Learning Audit & Evaluation Report")
    print("Academic Mini-Project: Intelligent Vehicle System and Cost Management Platform")
    evaluate_health_classifier()
    evaluate_resale_regressor()
    evaluate_fuel_efficiency_regressor()
    evaluate_predictive_maintenance_feasibility()
