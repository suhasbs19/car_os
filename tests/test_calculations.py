"""
Tests for vehicle health score calculation.
Covers boundary cases and formula correctness.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from datetime import date
from services.health_service import calculate_health_score


class TestHealthScore(unittest.TestCase):

    def test_perfect_vehicle(self):
        """Brand new, zero km, full history, no issues → near-100."""
        result = calculate_health_score(
            manufacturing_year=date.today().year,
            odometer_km=0,
            service_history="Full",
            reported_issues=0,
        )
        self.assertEqual(result["score"], 100.0)
        self.assertEqual(result["status"], "Healthy")

    def test_old_high_mileage_no_history_many_issues(self):
        """Very old, high mileage, no history, max issues → 0 (Critical)."""
        result = calculate_health_score(
            manufacturing_year=date.today().year - 20,
            odometer_km=200_000,
            service_history="None",
            reported_issues=10,
        )
        # age_pen=30, mileage_pen=30, service_pen=20, issues_pen=40 → 100-120=-20 → clamped to 0
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["status"], "Critical")

    def test_age_penalty_cap(self):
        """Age penalty capped at 30."""
        r1 = calculate_health_score(date.today().year - 10, 0, "Full", 0)
        r2 = calculate_health_score(date.today().year - 20, 0, "Full", 0)
        # 10*3=30; 20*3=60 but capped at 30
        self.assertEqual(r1["breakdown"]["age_penalty"], 30)
        self.assertEqual(r2["breakdown"]["age_penalty"], 30)

    def test_mileage_penalty_cap(self):
        """Mileage penalty capped at 30."""
        r = calculate_health_score(date.today().year, 200_000, "Full", 0)
        self.assertEqual(r["breakdown"]["mileage_penalty"], 30)

    def test_issues_penalty_cap(self):
        """Issues penalty capped at 40."""
        r = calculate_health_score(date.today().year, 0, "Full", 10)
        self.assertEqual(r["breakdown"]["issues_penalty"], 40)

    def test_status_healthy_boundary(self):
        """Score 80 → Healthy."""
        # Arrange to get exactly 80: 100 - 0 - 0 - 20 - 0 = 80 (no service history)
        r = calculate_health_score(date.today().year, 0, "None", 0)
        self.assertEqual(r["score"], 80.0)
        self.assertEqual(r["status"], "Healthy")

    def test_status_attention_boundary(self):
        """Score 50 → Attention."""
        # 100 - 0 - 0 - 10 - 40 = 50
        r = calculate_health_score(date.today().year, 0, "Unknown", 4)
        self.assertEqual(r["score"], 50.0)
        self.assertEqual(r["status"], "Attention")

    def test_status_critical_below_50(self):
        """Score 49 → Critical."""
        # 100 - 0 - 0 - 20 - 40 = 40
        r = calculate_health_score(date.today().year, 0, "None", 4)
        self.assertEqual(r["score"], 40.0)
        self.assertEqual(r["status"], "Critical")

    def test_service_history_full_no_penalty(self):
        r = calculate_health_score(date.today().year, 0, "Full", 0)
        self.assertEqual(r["breakdown"]["service_penalty"], 0)

    def test_service_history_partial_penalty(self):
        r = calculate_health_score(date.today().year, 0, "Partial", 0)
        self.assertEqual(r["breakdown"]["service_penalty"], 10)

    def test_service_history_none_penalty(self):
        r = calculate_health_score(date.today().year, 0, "None", 0)
        self.assertEqual(r["breakdown"]["service_penalty"], 20)

    def test_disclaimer_present(self):
        r = calculate_health_score(date.today().year, 0, "Full", 0)
        self.assertIn("disclaimer", r)
        self.assertTrue(len(r["disclaimer"]) > 10)

    def test_score_never_exceeds_100(self):
        r = calculate_health_score(date.today().year + 5, 0, "Full", 0)
        self.assertLessEqual(r["score"], 100.0)

    def test_score_never_below_zero(self):
        r = calculate_health_score(1900, 999_999, "None", 99)
        self.assertGreaterEqual(r["score"], 0.0)


class TestValuationService(unittest.TestCase):

    def setUp(self):
        from services.valuation_service import calculate_resale_value
        self.calc = calculate_resale_value

    def test_known_model_hyundai_creta(self):
        r = self.calc("Hyundai", "Creta", date.today().year, 0, 100)
        self.assertTrue(r["is_known_model"])
        self.assertEqual(r["base_price"], 1_200_000)

    def test_unknown_model_uses_default(self):
        r = self.calc("Unknown", "XYZ", date.today().year, 0, 100)
        self.assertFalse(r["is_known_model"])
        self.assertEqual(r["base_price"], 800_000)

    def test_age_factor_floor(self):
        """Very old car — age factor floors at 0.25."""
        r = self.calc("Hyundai", "Creta", 1990, 0, 50)
        self.assertGreaterEqual(r["factors"]["age_factor"], 0.25)

    def test_mileage_factor_floor(self):
        """Very high mileage — mileage factor floors at 0.55."""
        r = self.calc("Hyundai", "Creta", date.today().year, 500_000, 50)
        self.assertGreaterEqual(r["factors"]["mileage_factor"], 0.55)

    def test_value_rounded_to_nearest_1000(self):
        r = self.calc("Maruti", "Swift", date.today().year - 3, 30_000, 75)
        self.assertEqual(r["estimated_value"] % 1000, 0)

    def test_value_positive(self):
        r = self.calc("Tata", "Nexon", 2000, 200_000, 10)
        self.assertGreater(r["estimated_value"], 0)

    def test_disclaimer_present(self):
        r = self.calc("Maruti", "Swift", date.today().year, 0, 90)
        self.assertIn("disclaimer", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
