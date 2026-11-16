"""
Tests for CAR OS UI, Data Quality, and Calculation Improvements.
Validates:
- INR & Lakh formatting helpers
- Make normalization (e.g. Maruti Suzuki -> Maruti)
- CarDekho ML valuation engine integration and EV benchmark fallback
- Valuation fleet consistency between dashboard and valuation page
- Maintenance budget separation from actual recorded expenses (no TCO contamination)
- Health score diagnostic status differentiation
- Decision confidence and evidence-grounded rationales
- Indian fuel & electricity tariff calculations
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from app import create_app
from models import db, Vehicle, MaintenanceRecord, ExpenseRecord, OBDRecord
from services.valuation_service import (
    normalize_make,
    calculate_resale_value,
    format_inr,
    format_lakh,
)
from services.maintenance_budget_service import get_model_maintenance_benchmarks
from services.health_service import calculate_health_score
from services.decision_service import generate_decision
from services.fuel_service import calculate_fuel_efficiency, calculate_cost_per_km, INDIAN_FUEL_BENCHMARKS


class TestUICalculationImprovements(unittest.TestCase):

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_inr_and_lakh_formatting(self):
        """Test proper Indian rupee Lakh formatting without mislabeling as K."""
        # Under 1,000
        self.assertEqual(format_inr(750), "₹750")
        # Under 1 Lakh
        self.assertEqual(format_inr(45000), "₹45,000")
        # 1 Lakh and above should format as Lakh
        self.assertEqual(format_inr(100000), "₹1.00L")
        self.assertEqual(format_inr(842000), "₹8.42L")
        self.assertEqual(format_inr(3900000), "₹39.00L")
        # Explicit format_lakh
        self.assertEqual(format_lakh(842000), "₹8.42 Lakh")
        self.assertEqual(format_lakh(65000), "₹65,000")
        self.assertEqual(format_lakh(150000), "₹1.50 Lakh")

    def test_make_normalization(self):
        """Test Indian brand alias mapping to CarDekho training distribution."""
        self.assertEqual(normalize_make("Maruti Suzuki"), "Maruti")
        self.assertEqual(normalize_make("maruti"), "Maruti")
        self.assertEqual(normalize_make("Mercedes"), "Mercedes-Benz")
        self.assertEqual(normalize_make("Land Rover"), "Land")
        self.assertEqual(normalize_make("Hyundai"), "Hyundai")
        self.assertEqual(normalize_make("Tata"), "Tata")

    def test_valuation_engine_auto_with_cardekho_and_ev_fallback(self):
        """Test auto engine selects ML for ICE and EV fallback for electric vehicles."""
        # ICE CarDekho supported make
        ice_val = calculate_resale_value(
            make="Hyundai",
            model="Creta",
            manufacturing_year=2021,
            odometer_km=35000,
            health_score=85.0,
            fuel_type="Petrol",
            transmission="Manual",
            owner="First Owner",
            engine="auto"
        )
        self.assertEqual(ice_val["valuation_engine"], "cardekho_ml")
        self.assertIsNotNone(ice_val["price_range_inr"])
        self.assertGreater(ice_val["price_range_inr"][1], ice_val["estimated_value"])
        self.assertLess(ice_val["price_range_inr"][0], ice_val["estimated_value"])
        self.assertIn("CarDekho Indian Market Model", ice_val["valuation_source"])

        # EV Vehicle fallback
        ev_val = calculate_resale_value(
            make="Tata",
            model="Nexon EV",
            manufacturing_year=2022,
            odometer_km=22000,
            health_score=92.0,
            fuel_type="Electric",
            engine="auto"
        )
        self.assertEqual(ev_val["valuation_engine"], "ev_baseline_fallback")
        self.assertIsNotNone(ev_val["price_range_inr"])

        # Unseen / unsupported brand fallback
        exotic_val = calculate_resale_value(
            make="Tesla",
            model="Model 3",
            manufacturing_year=2023,
            odometer_km=10000,
            engine="auto"
        )
        self.assertEqual(exotic_val["valuation_engine"], "rule_based_fallback")
        self.assertIsNotNone(exotic_val["fallback_reason"])

    def test_maintenance_benchmarks_and_budget_separation(self):
        """Ensure maintenance benchmarks exist and upcoming estimates do NOT become expenses."""
        benchmarks = get_model_maintenance_benchmarks()
        self.assertTrue(isinstance(benchmarks, list))
        self.assertTrue(any(b.get("make") == "Honda" for b in benchmarks))
        self.assertTrue(any(b.get("make") == "Toyota" for b in benchmarks))
        self.assertTrue(any(b.get("segment") == "EV" for b in benchmarks))

        # Create a test vehicle
        from datetime import date
        v = Vehicle(
            registration_number="MH01AB1234",
            make="Honda",
            model="City",
            manufacturing_year=2020,
            odometer_km=40000,
            fuel_type="Petrol"
        )
        db.session.add(v)
        db.session.commit()

        # Add 1 completed recorded maintenance
        m = MaintenanceRecord(
            vehicle_id=v.id,
            service_date=date(2024, 1, 15),
            service_category="Scheduled Maintenance",
            component_name="Engine Oil & Filter",
            odometer_at_service=38000,
            cost=6500.0,
            status="Completed"
        )
        db.session.add(m)
        db.session.commit()

        # Ensure expense records count is 0 (unless explicitly created)
        expenses = ExpenseRecord.query.filter_by(vehicle_id=v.id).all()
        self.assertEqual(len(expenses), 0)

    def test_health_score_diagnostic_status_differentiation(self):
        """Test health score distinguishes missing diagnostics from fault-free diagnostics."""
        v = Vehicle(
            registration_number="DL01XY9999",
            make="Maruti",
            model="Swift",
            manufacturing_year=2019,
            odometer_km=50000
        )
        db.session.add(v)
        db.session.commit()

        # Case 1: No OBD diagnostics recorded
        hs_no_obd = calculate_health_score(2019, 50000, "Full", 0, obd_record=None)
        self.assertEqual(hs_no_obd["diagnostic_status"], "No diagnostic data recorded")
        self.assertIn("score_label", hs_no_obd)

        # Case 2: OBD record with no DTCs
        rec_clean = OBDRecord(
            vehicle_id=v.id,
            engine_rpm=1200,
            vehicle_speed_kmh=40,
            coolant_temp_c=88,
            dtc_codes=""
        )
        hs_clean = calculate_health_score(2019, 50000, "Full", 0, obd_record=rec_clean)
        self.assertEqual(hs_clean["diagnostic_status"], "No diagnostic faults detected")

        # Case 3: OBD record with active DTCs
        rec_fault = OBDRecord(
            vehicle_id=v.id,
            engine_rpm=1500,
            vehicle_speed_kmh=55,
            coolant_temp_c=95,
            dtc_codes='["P0300", "P0420"]'
        )
        hs_fault = calculate_health_score(2019, 50000, "Full", 0, obd_record=rec_fault)
        self.assertEqual(hs_fault["diagnostic_status"], "2 active fault code(s) recorded")

    def test_decision_confidence_and_sparse_history_transparency(self):
        """Test decision logic uses transparent confidence rationales and never claims full history when sparse."""
        v = Vehicle(
            registration_number="KA01MN4567",
            make="Hyundai",
            model="Creta",
            manufacturing_year=2021,
            odometer_km=32000
        )
        db.session.add(v)
        db.session.commit()


        decision = generate_decision(v, [], [], [])
        self.assertIn(decision["confidence"], ["High", "Medium", "Low"])
        self.assertIn("confidence_rationale", decision)
        # Since 0 service records exist, reasons must NOT state "Full service history recorded"
        reasons_text = " ".join(decision["reasons"])
        self.assertNotIn("Full service history recorded", reasons_text)

    def test_indian_fuel_and_ev_tariffs(self):
        """Test fuel efficiency calculations and Indian benchmark rates."""
        # ICE fuel efficiency (400 km on 25 L, total cost Rs. 2587.5 at Rs 103.5/L)
        ice_res = calculate_fuel_efficiency(400.0, 25.0, "Petrol", cost=2587.5)
        self.assertEqual(ice_res["efficiency"], 16.0)  # 16 km/L
        self.assertEqual(ice_res["unit"], "km/L")
        self.assertAlmostEqual(ice_res["cost_per_km"], 6.47, places=2)

        # Cost per km calculation directly
        cost_km = calculate_cost_per_km(400.0, 2587.5)
        self.assertAlmostEqual(cost_km, 6.47, places=2)

        # EV efficiency (200 km on 30 kWh, cost Rs. 270 at Rs 9.0/kWh)
        ev_res = calculate_fuel_efficiency(200.0, 30.0, "Electric", cost=270.0)
        self.assertAlmostEqual(ev_res["efficiency"], 6.67, places=2)  # 6.67 km/kWh
        self.assertEqual(ev_res["unit"], "km/kWh")
        self.assertAlmostEqual(ev_res["cost_per_km"], 1.35, places=2)

        # Indian benchmark tariff verification
        self.assertEqual(INDIAN_FUEL_BENCHMARKS["Petrol"]["price_per_unit"], 103.5)
        self.assertEqual(INDIAN_FUEL_BENCHMARKS["Electric"]["price_per_unit"], 9.0)


if __name__ == "__main__":
    unittest.main()
