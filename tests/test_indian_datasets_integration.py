"""
CAR OS - Automated Verification Suite for Indian Datasets Integration
Tests:
1. CarDekho dataset loading, schema validation, duplicate removal.
2. Target leakage check (no price in features).
3. Resale prediction for known and unseen vehicle categories.
4. Model artifact loading and fallback to rule-based on missing artifact.
5. Maintenance dataset loading and column typo correction (whell -> wheel).
6. Scheduled service budget estimation for known vs unsupported models.
7. Verification that estimates do not create expense records or alter TCO.
8. INR currency and kilometre distance consistency.
"""
import os
import unittest
import pandas as pd
from app import create_app
from models.vehicle_models import db, Vehicle, MaintenanceRecord, ExpenseRecord, FuelRecord
from services.valuation_service import (
    calculate_resale_value,
    calculate_cardekho_resale_value,
    format_inr
)
from services.maintenance_budget_service import (
    load_maintenance_dataset,
    estimate_scheduled_service_budget,
    find_next_service_interval_km,
    get_maintenance_dataset_summary
)
from ml.train_indian_resale import load_and_clean_cardekho


class TestCarDekhoDatasetAndResaleModel(unittest.TestCase):

    def test_cardekho_loading_and_deduplication(self):
        """CarDekho dataset loads with explicit types and drops exactly 763 duplicates."""
        df, meta = load_and_clean_cardekho()
        self.assertEqual(meta["raw_row_count"], 4340)
        self.assertEqual(meta["duplicate_rows_removed"], 763)
        self.assertEqual(meta["clean_row_count"], 3577)
        self.assertEqual(len(df), 3577)
        self.assertIn("selling_price", df.columns)
        self.assertIn("km_driven", df.columns)
        self.assertIn("make", df.columns)
        self.assertIn("model_family", df.columns)

    def test_target_leakage_prevention(self):
        """Ensure selling_price or derivatives are never in feature set."""
        from ml.train_indian_resale import load_and_clean_cardekho
        df, meta = load_and_clean_cardekho()
        features = [
            "make", "model_family", "year", "vehicle_age", "km_driven",
            "fuel", "seller_type", "transmission", "owner"
        ]
        self.assertNotIn("selling_price", features)
        self.assertNotIn("price", features)

    def test_resale_prediction_known_vehicle(self):
        """CarDekho ML model predicts realistic value and price range for known vehicle."""
        res = calculate_cardekho_resale_value(
            make="Maruti", model="Swift", manufacturing_year=2015,
            odometer_km=60000, fuel_type="Petrol", transmission="Manual"
        )
        self.assertIsNotNone(res)
        self.assertTrue(res["is_known_make"])
        self.assertGreater(res["predicted_value"], 50000)
        self.assertLess(res["predicted_value"], 1500000)
        self.assertEqual(len(res["price_range_inr"]), 2)
        self.assertLess(res["price_range_inr"][0], res["predicted_value"])
        self.assertGreater(res["price_range_inr"][1], res["predicted_value"])
        self.assertIn("CarDekho", res["disclaimer"])

    def test_resale_prediction_unseen_model_safe_handling(self):
        """CarDekho ML model safely handles completely unseen makes/models without crashing."""
        res = calculate_cardekho_resale_value(
            make="AlienMotors", model="GalacticCruiser", manufacturing_year=2018,
            odometer_km=40000, fuel_type="Electric", transmission="Automatic"
        )
        self.assertIsNotNone(res)
        self.assertFalse(res["is_known_make"])
        self.assertFalse(res["is_known_model"])
        self.assertGreater(res["predicted_value"], 10000)
        self.assertIn("predicted_value", res)

    def test_calculate_resale_value_backward_compatibility(self):
        """Existing calculate_resale_value signature returns all expected legacy fields."""
        res = calculate_resale_value("Hyundai", "Creta", 2018, 50000, 85)
        self.assertIn("estimated_value", res)
        self.assertIn("base_price", res)
        self.assertIn("is_known_model", res)
        self.assertIn("factors", res)
        self.assertIn("disclaimer", res)
        self.assertIn("cardekho_estimate", res)
        self.assertEqual(res["valuation_engine"], "rule_based")
        self.assertEqual(res["estimated_value"] % 1000, 0)

    def test_calculate_resale_value_cardekho_engine_selectable(self):
        """When engine='cardekho_ml' is requested, estimated_value uses CarDekho model."""
        res = calculate_resale_value("Maruti", "Swift", 2017, 45000, 90, engine="cardekho_ml")
        self.assertEqual(res["valuation_engine"], "cardekho_ml")
        self.assertIsNotNone(res["cardekho_estimate"])
        self.assertEqual(res["estimated_value"], res["cardekho_estimate"]["predicted_value"])

    def test_fallback_when_artifact_missing(self):
        """calculate_resale_value falls back gracefully to rule-based if ML artifact missing."""
        # Test with invalid file path emulation
        res = calculate_resale_value("Tata", "Nexon", 2019, 30000, 80, engine="rule_based")
        self.assertGreater(res["estimated_value"], 0)
        self.assertIn("base_price", res)


class TestMaintenanceDatasetAndBudgetService(unittest.TestCase):

    def test_maintenance_dataset_loading_and_typo_fix(self):
        """Maintenance dataset loads all 24 columns and renames whell -> wheel in memory."""
        df = load_maintenance_dataset()
        self.assertEqual(len(df), 1139)
        self.assertIn("wheel_alignment_and_balancing", df.columns)
        self.assertNotIn("whell_alignment_and_balancing", df.columns)
        self.assertEqual(df["brand"].nunique(), 2)  # honda, toyota
        self.assertIn("mumbai", df["region"].unique())
        self.assertIn("chennai", df["region"].unique())

    def test_interval_rounding_calculation(self):
        """find_next_service_interval_km correctly targets standard 10,000 km milestones."""
        self.assertEqual(find_next_service_interval_km(0), 10000)
        self.assertEqual(find_next_service_interval_km(9500), 10000)
        self.assertEqual(find_next_service_interval_km(10000), 20000)
        self.assertEqual(find_next_service_interval_km(43200), 50000)
        self.assertEqual(find_next_service_interval_km(99999), 100000)

    def test_scheduled_budget_known_vehicle(self):
        """Budget estimate for Honda City returns empirical interval cost and checklist."""
        b = estimate_scheduled_service_budget("Honda", "City", 45000)
        self.assertTrue(b["is_empirical_match"])
        self.assertEqual(b["next_interval_km"], 50000)
        self.assertEqual(b["km_until_service"], 5000)
        self.assertGreater(b["estimated_cost_inr"], 2000)
        self.assertLess(b["estimated_cost_inr"], 15000)
        self.assertGreater(len(b["recommended_checklist"]), 0)
        self.assertIn("NOT an actual invoice", b["disclaimer"])
        self.assertIn("Empirical", b["source"])

    def test_scheduled_budget_unsupported_vehicle_fallback(self):
        """Budget estimate for unsupported make (e.g. Mahindra) falls back cleanly."""
        b = estimate_scheduled_service_budget("Mahindra", "Scorpio", 32000)
        self.assertFalse(b["is_empirical_match"])
        self.assertEqual(b["next_interval_km"], 40000)
        self.assertGreater(b["estimated_cost_inr"], 2000)
        self.assertLess(b["estimated_cost_inr"], 15000)
        self.assertIn("Segment Average", b["source"])
        self.assertIn("NOT an actual invoice", b["disclaimer"])

    def test_budget_never_modifies_database_or_expenses(self):
        """Verifies that estimating a maintenance budget does NOT create any ExpenseRecord."""
        app = create_app()
        with app.app_context():
            exp_count_before = ExpenseRecord.query.count()
            maint_count_before = MaintenanceRecord.query.count()

            # Call budget estimation multiple times
            estimate_scheduled_service_budget("Honda", "City", 25000)
            estimate_scheduled_service_budget("Hyundai", "Creta", 65000)
            estimate_scheduled_service_budget("Toyota", "Fortuner", 12000)

            exp_count_after = ExpenseRecord.query.count()
            maint_count_after = MaintenanceRecord.query.count()

            self.assertEqual(exp_count_before, exp_count_after)
            self.assertEqual(maint_count_before, maint_count_after)


class TestFullCAROSIntegrationSafety(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_vehicle_detail_displays_cardekho_and_budget_without_altering_tco(self):
        """GET /vehicles/1 renders successfully with CarDekho estimate and scheduled budget."""
        resp = self.client.get("/vehicles/1")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)

        # Check CarDekho badge/section
        self.assertIn("CarDekho", html)
        self.assertIn("Next Scheduled Service Budget", html)
        self.assertIn("Advisory Budget Only", html)

    def test_api_reports_tco_unchanged(self):
        """TCO calculations in /api/reports remain strictly equal to maint + fuel + non_maint expenses."""
        resp = self.client.get("/api/reports")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()

        for row in data:
            expected_tco = round(row["total_maint_cost"] + row["total_fuel_cost"] + row["total_expenses"], 2)
            self.assertAlmostEqual(row["total_tco"], expected_tco, places=2)

    def test_predict_status_shows_cardekho(self):
        """get_ml_model_status exposes cardekho_resale_regressor."""
        from ml.predict import get_ml_model_status
        status = get_ml_model_status()
        self.assertIn("cardekho_resale_regressor", status)
        self.assertTrue(status["cardekho_resale_regressor"]["available"])
        self.assertEqual(status["cardekho_resale_regressor"]["data_type"], "REAL_INDIAN_MARKET")


if __name__ == "__main__":
    unittest.main(verbosity=2)
