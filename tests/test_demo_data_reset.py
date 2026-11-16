"""
Unit tests for CAR OS Demo Data Reset and Seeding Engine.
"""
import unittest
from datetime import date
from app import create_app
from models import (
    db, Vehicle, MaintenanceRecord, FuelRecord, ExpenseRecord,
    DiagnosticRecord, OBDRecord
)
from scripts.reset_demo_data import (
    build_seed_dataset,
    validate_seed_data_against_schema,
    execute_reset_and_seeding,
)


class TestDemoDataReset(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_seed_dataset_structure_and_validation(self):
        data = build_seed_dataset()
        self.assertIn("vehicles", data)
        self.assertIn("fuel_specs", data)
        self.assertIn("maintenance_specs", data)
        self.assertIn("standalone_expenses", data)
        self.assertIn("obd_specs", data)
        self.assertIn("diagnostic_specs", data)

        self.assertEqual(len(data["vehicles"]), 8)
        errors = validate_seed_data_against_schema(data)
        self.assertEqual(errors, [])

    def test_dry_run_does_not_modify_database(self):
        result = execute_reset_and_seeding(self.app, apply_changes=False)
        self.assertEqual(result["mode"], "dry-run")
        self.assertEqual(Vehicle.query.count(), 0)

    def test_apply_seeding_creates_all_records_and_maintains_integrity(self):
        result = execute_reset_and_seeding(self.app, apply_changes=True)
        self.assertEqual(result["mode"], "applied")
        self.assertEqual(Vehicle.query.count(), 8)
        self.assertEqual(MaintenanceRecord.query.count(), 15)
        self.assertEqual(FuelRecord.query.count(), 26)
        self.assertEqual(ExpenseRecord.query.count(), 25)
        self.assertEqual(OBDRecord.query.count(), 7)
        self.assertEqual(DiagnosticRecord.query.count(), 7)

        # Check vehicle registrations
        creta = Vehicle.query.filter_by(registration_number="DEMO-MH-001").first()
        self.assertIsNotNone(creta)
        self.assertEqual(creta.fuel_type, "Petrol")
        self.assertGreater(creta.health_score, 80)
        self.assertEqual(creta.health_status, "Healthy")

        # Check EV vehicle
        nexon = Vehicle.query.filter_by(registration_number="DEMO-KA-002").first()
        self.assertIsNotNone(nexon)
        self.assertEqual(nexon.fuel_type, "Electric")
        for f in nexon.fuel_records.all():
            self.assertEqual(f.fuel_type, "Electric")

        # Check anti-double-counting expense linkage
        linked_expenses = ExpenseRecord.query.filter(ExpenseRecord.linked_maintenance_id.isnot(None)).all()
        self.assertGreater(len(linked_expenses), 0)
        for exp in linked_expenses:
            maint = MaintenanceRecord.query.get(exp.linked_maintenance_id)
            self.assertIsNotNone(maint)
            self.assertEqual(maint.cost, exp.amount)
            self.assertEqual(maint.expense_id, exp.id)


if __name__ == "__main__":
    unittest.main()

