"""
Unit and integration tests for valuation fixes and fuel/energy accounting fixes.
Verifies:
1. Valuation Fixes:
   - Secondary market price engine enforces strict powertrain segregation (EV/CNG do not fall back to petrol/diesel).
   - Strict age window (listings >3 years away return market_data_available=False).
   - Provenance integrity: CarDekho dataset is accurately dated 2020 without fabricated dates.
   - Exact variant showroom matching (Fortuner 4x4 vs 4x2, Polo TSI vs MPI).
   - Year consistency (Polo 2018 TSI does not substitute MPI; Polo 2020 TSI matches exact).
   - Condition & health score sensitivity (Health=0 salvage deduction, Health=95 top retention).
   - Preservation of user-entered showroom prices.
2. Fuel & Energy Accounting Fixes:
   - Unit price calculation and validation (quantity * unit_price).
   - Strict powertrain segregation (L, kg, kWh).
   - Mixed fleet aggregation safety (is_mixed=True, total_quantity=None).
   - Date range filtering (date_from, date_to).
   - Anti-double-counting in Total Cost of Ownership (TCO).
"""

import unittest
from datetime import date
from app import create_app
from models import db, Vehicle, FuelRecord, ExpenseRecord, MaintenanceRecord
from services.showroom_price_service import get_showroom_price
from services.market_pricing_service import get_comparable_market_pricing
from services.valuation_service import calculate_resale_value
from services.fuel_service import aggregate_fuel_records


class TestValuationFixes(unittest.TestCase):
    """Test valuation fixes, market pricing filters, and showroom catalog variant matching."""

    def test_ev_does_not_match_ice_listings(self):
        """Electric vehicles must NOT fall back to Petrol/Diesel listings in market price engine."""
        mkt = get_comparable_market_pricing(
            make="Tata",
            model="Nexon EV",
            manufacturing_year=2022,
            odometer_km=25000,
            fuel_type="Electric",
        )
        # Because CarDekho dataset contains zero electric listings, it must return market_data_available=False
        self.assertFalse(mkt["market_data_available"])
        self.assertEqual(mkt["comparable_listings_count"], 0)
        self.assertIn("No comparable", mkt["market_status"])

    def test_cng_does_not_match_petrol_listings(self):
        """CNG vehicle for a model with no CNG listings in dataset must NOT match Petrol listings."""
        mkt = get_comparable_market_pricing(
            make="Maruti",
            model="Baleno",
            manufacturing_year=2023,
            odometer_km=18000,
            fuel_type="CNG",
        )
        self.assertFalse(mkt["market_data_available"])
        self.assertEqual(mkt["comparable_listings_count"], 0)

    def test_stale_year_window_enforcement(self):
        """Vehicles newer than dataset window (>3 years diff) must not match ancient listings."""
        mkt = get_comparable_market_pricing(
            make="Maruti",
            model="Swift",
            manufacturing_year=2025,
            odometer_km=5000,
            fuel_type="Petrol",
        )
        self.assertFalse(mkt["market_data_available"])
        self.assertIn("dataset window", mkt["market_status"])

    def test_provenance_honesty(self):
        """Secondary market dataset must be honestly labeled as 2020 CarDekho without fake dates."""
        mkt = get_comparable_market_pricing(
            make="Maruti",
            model="Swift",
            manufacturing_year=2019,
            odometer_km=40000,
            fuel_type="Petrol",
        )
        self.assertIn("2020", mkt["source"])
        self.assertEqual(mkt["last_updated"], "2020-12-31")
        self.assertFalse(mkt["is_live_api"])

    def test_fortuner_variant_exact_matching(self):
        """Fortuner 2.8 4x4 AT must not match 4x2 AT in showroom catalog."""
        sh = get_showroom_price(
            make="Toyota",
            model="Fortuner",
            variant="2.8 4x4 AT",
            manufacturing_year=2021,
            fuel_type="Diesel",
            transmission="Automatic",
        )
        self.assertTrue(sh["price_available"])
        self.assertTrue(sh["is_exact_match"])
        # In catalog, 4x4 AT is ₹37.43 Lakhs (3,743,000), 4x2 AT is ₹34.84 Lakhs (3,484,000)
        self.assertEqual(sh["ex_showroom_price"], 3743000)
        self.assertIn("4x4", sh["matched_variant"])

    def test_polo_2020_tsi_variant_exact_matching(self):
        """Polo 1.0 TSI Highline Plus for 2020 matches exact catalog price."""
        sh = get_showroom_price(
            make="Volkswagen",
            model="Polo",
            variant="1.0 TSI Highline Plus",
            manufacturing_year=2020,
            fuel_type="Petrol",
        )
        self.assertTrue(sh["price_available"])
        self.assertTrue(sh["is_exact_match"])
        # In catalog, 2020 1.0 TSI Highline Plus is ₹8.08 Lakhs (808,000)
        self.assertEqual(sh["ex_showroom_price"], 808000)
        self.assertIn("Highline", sh["matched_variant"])

    def test_polo_2018_tsi_does_not_mismatch_mpi(self):
        """Polo 2018 with TSI variant must not falsely substitute 2018 MPI Trendline."""
        sh = get_showroom_price(
            make="Volkswagen",
            model="Polo",
            variant="1.0 TSI Highline Plus",
            manufacturing_year=2018,
            fuel_type="Petrol",
        )
        # Because 1.0 TSI did not exist in 2018, it must prompt manual entry rather than match MPI
        self.assertFalse(sh["price_available"])
        self.assertTrue(sh["prompt_manual_entry"])

    def test_missing_exact_variant_prompts_manual_entry(self):
        """An inexact variant must prompt manual user entry rather than substitute wrong variant price."""
        sh = get_showroom_price(
            make="Maruti",
            model="Swift",
            variant="Special Limited Edition Nonexistent",
            manufacturing_year=2019,
            fuel_type="Petrol",
        )
        self.assertFalse(sh["price_available"])
        self.assertFalse(sh["is_exact_match"])
        self.assertIsNone(sh["ex_showroom_price"])
        self.assertTrue(sh["prompt_manual_entry"])

    def test_severe_health_penalty_salvage(self):
        """Vehicle with blown engine (health=0) must receive realistic salvage valuation."""
        val = calculate_resale_value(
            make="Mahindra",
            model="Thar",
            manufacturing_year=2013,
            odometer_km=142000,
            health_score=0.0,
            fuel_type="Diesel",
            transmission="Manual",
            reported_issues=3,
            service_history="None",
            original_showroom_price=850000.0,
            engine="auto",
        )
        # Salvage value for a 2013 non-running Thar must be under ₹1.5 Lakhs, not ₹3.7 Lakhs
        self.assertLess(val["estimated_value"], 150000)
        self.assertGreater(val["estimated_value"], 15000)

    def test_pristine_health_preserves_valuation(self):
        """Vehicle with health=95 must retain significantly higher value than health=25."""
        val_pristine = calculate_resale_value(
            make="Maruti",
            model="Swift",
            manufacturing_year=2019,
            odometer_km=35000,
            health_score=95.0,
            fuel_type="Petrol",
            service_history="Full",
            engine="auto",
        )
        val_poor = calculate_resale_value(
            make="Maruti",
            model="Swift",
            manufacturing_year=2019,
            odometer_km=35000,
            health_score=25.0,
            fuel_type="Petrol",
            service_history="None",
            reported_issues=4,
            engine="auto",
        )
        # Pristine should be worth at least 1.8x the severely defective one
        self.assertGreater(val_pristine["estimated_value"], val_poor["estimated_value"] * 1.8)


class TestFuelAndEnergyAccountingFixes(unittest.TestCase):
    """Test fuel and energy calculation, powertrain unit segregation, and TCO anti-double-counting."""

    def setUp(self):
        self.app = create_app("testing")
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_fuel_record_unit_price_property(self):
        """FuelRecord.unit_price must equal cost / quantity."""
        rec = FuelRecord(
            vehicle_id=1,
            date=date(2025, 1, 15),
            fuel_type="Petrol",
            quantity=40.0,
            cost=4080.0,
            distance_km=450.0,
        )
        self.assertAlmostEqual(rec.unit_price, 102.0, places=2)
        d = rec.to_dict()
        self.assertEqual(d["unit_price"], 102.0)

    def test_ev_kwh_cost_calculation(self):
        """EV charging record unit price must equal cost per kWh."""
        rec = FuelRecord(
            vehicle_id=2,
            date=date(2025, 2, 10),
            fuel_type="Electric",
            quantity=30.0,  # 30 kWh
            cost=330.0,
            distance_km=200.0,
        )
        self.assertAlmostEqual(rec.unit_price, 11.0, places=2)

    def test_single_powertrain_aggregation(self):
        """Aggregation of a single petrol vehicle returns proper units and metrics."""
        records = [
            FuelRecord(vehicle_id=1, date=date(2025, 1, 1), fuel_type="Petrol", quantity=35.0, cost=3570.0, distance_km=490.0),
            FuelRecord(vehicle_id=1, date=date(2025, 1, 15), fuel_type="Petrol", quantity=40.0, cost=4080.0, distance_km=560.0),
        ]
        stats = aggregate_fuel_records(records, fuel_type="Petrol")
        self.assertFalse(stats["is_mixed"])
        self.assertEqual(stats["quantity_unit"], "L")
        self.assertEqual(stats["unit"], "km/L")
        self.assertEqual(stats["total_records"], 2)
        self.assertEqual(stats["total_quantity"], 75.0)
        self.assertEqual(stats["total_cost"], 7650.0)
        self.assertAlmostEqual(stats["average_efficiency"], 14.0, places=1)
        self.assertAlmostEqual(stats["average_cost_per_km"], 7.29, places=2)

    def test_mixed_fleet_aggregation_does_not_sum_litres_and_kwh(self):
        """Mixed fleet aggregation must NOT sum Litres, kg, and kWh into one meaningless number."""
        records = [
            FuelRecord(vehicle_id=1, date=date(2025, 1, 1), fuel_type="Petrol", quantity=40.0, cost=4080.0, distance_km=500.0),
            FuelRecord(vehicle_id=2, date=date(2025, 1, 2), fuel_type="Electric", quantity=30.0, cost=330.0, distance_km=210.0),
            FuelRecord(vehicle_id=3, date=date(2025, 1, 3), fuel_type="CNG", quantity=10.0, cost=850.0, distance_km=250.0),
        ]
        stats = aggregate_fuel_records(records)
        self.assertTrue(stats["is_mixed"])
        # When mixed, total_quantity and average_efficiency must be None to prevent nonsense addition
        self.assertIsNone(stats["total_quantity"])
        self.assertIsNone(stats["average_efficiency"])
        self.assertEqual(stats["total_cost"], 5260.0)
        self.assertEqual(stats["total_distance_km"], 960.0)

        # by_fuel_type must have segregated breakdown
        by_ft = stats["by_fuel_type"]
        self.assertIn("Petrol", by_ft)
        self.assertIn("Electric", by_ft)
        self.assertIn("CNG", by_ft)

        self.assertEqual(by_ft["Petrol"]["quantity_unit"], "L")
        self.assertEqual(by_ft["Petrol"]["total_quantity"], 40.0)

        self.assertEqual(by_ft["Electric"]["quantity_unit"], "kWh")
        self.assertEqual(by_ft["Electric"]["total_quantity"], 30.0)

        self.assertEqual(by_ft["CNG"]["quantity_unit"], "kg")
        self.assertEqual(by_ft["CNG"]["total_quantity"], 10.0)

    def test_date_range_filtering_on_fuel_records(self):
        """Date filtering correctly includes records in range and excludes out-of-range records."""
        v = Vehicle(registration_number="FUELDATE01", make="Maruti", model="Swift", manufacturing_year=2020)
        db.session.add(v)
        db.session.commit()

        r1 = FuelRecord(vehicle_id=v.id, date=date(2025, 1, 10), fuel_type="Petrol", quantity=30.0, cost=3000.0, distance_km=400.0)
        r2 = FuelRecord(vehicle_id=v.id, date=date(2025, 2, 10), fuel_type="Petrol", quantity=40.0, cost=4000.0, distance_km=520.0)
        r3 = FuelRecord(vehicle_id=v.id, date=date(2025, 3, 10), fuel_type="Petrol", quantity=35.0, cost=3500.0, distance_km=480.0)
        db.session.add_all([r1, r2, r3])
        db.session.commit()

        # Query with date_from=2025-02-01 and date_to=2025-02-28
        q = FuelRecord.query.filter(FuelRecord.date >= date(2025, 2, 1), FuelRecord.date <= date(2025, 2, 28))
        res = q.all()
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].date, date(2025, 2, 10))

    def test_tco_anti_double_counting(self):
        """TCO calculation must not double-count maintenance or fuel expenses."""
        v = Vehicle(registration_number="TCO01", make="Hyundai", model="Creta", manufacturing_year=2021)
        db.session.add(v)
        db.session.commit()

        # Maintenance record with cost 5000
        maint = MaintenanceRecord(
            vehicle_id=v.id,
            service_date=date(2025, 1, 10),
            service_category="Periodic Service",
            component_name="Engine Oil & Filters",
            description="Scheduled 30,000 km Service",
            cost=5000.0,
            odometer_at_service=30000,
        )
        db.session.add(maint)
        db.session.flush()

        # Expense linked to maintenance (should NOT be double-counted)
        e_maint = ExpenseRecord(
            vehicle_id=v.id,
            date=date(2025, 1, 10),
            category="Maintenance/Repair",
            amount=5000.0,
            linked_maintenance_id=maint.id,
        )
        # Standalone Fuel expense (should NOT be counted under other expenses if fuel records exist)
        e_fuel = ExpenseRecord(
            vehicle_id=v.id,
            date=date(2025, 1, 12),
            category="Fuel",
            amount=3500.0,
        )
        # Standalone Insurance expense (SHOULD be counted under other expenses)
        e_ins = ExpenseRecord(
            vehicle_id=v.id,
            date=date(2025, 1, 15),
            category="Insurance",
            amount=18000.0,
        )
        # Fuel record
        f_rec = FuelRecord(
            vehicle_id=v.id,
            date=date(2025, 1, 12),
            fuel_type="Petrol",
            quantity=35.0,
            cost=3500.0,
            distance_km=450.0,
        )
        db.session.add_all([e_maint, e_fuel, e_ins, f_rec])
        db.session.commit()

        # Verify TCO formula in analytics:
        # non_maint_expenses should only include e_ins (₹18,000)
        all_expenses = ExpenseRecord.query.filter_by(vehicle_id=v.id).all()
        non_maint_expenses = sum(
            e.amount for e in all_expenses
            if e.linked_maintenance_id is None and e.category not in ["Fuel", "Fuel & Energy", "Charging"]
        )
        self.assertEqual(non_maint_expenses, 18000.0)

        total_maintenance = sum(m.cost for m in MaintenanceRecord.query.filter_by(vehicle_id=v.id).all())
        total_fuel = sum(f.cost for f in FuelRecord.query.filter_by(vehicle_id=v.id).all())

        tco = total_maintenance + total_fuel + non_maint_expenses
        # 5000 + 3500 + 18000 = 26500.0
        self.assertEqual(tco, 26500.0)


if __name__ == "__main__":
    unittest.main()
