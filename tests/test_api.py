"""
Tests for API endpoints and maintenance/fuel/expense operations.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import json
from app import create_app
from models import db, Vehicle, MaintenanceRecord, FuelRecord, ExpenseRecord
from datetime import date


class TestAPIAndModules(unittest.TestCase):

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            # Create a test vehicle
            v = Vehicle(
                make="Tata", model="Nexon", registration_number="TN01AB1111",
                manufacturing_year=2021, odometer_km=25000,
                fuel_type="Petrol", service_history="Full", reported_issues=0,
                health_score=78.0, health_status="Attention",
                estimated_resale_value=720000,
            )
            db.session.add(v)
            db.session.commit()
            self.vehicle_id = v.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ── Dashboard ────────────────────────────────────────────────
    def test_dashboard_shows_vehicle_count(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_api_dashboard(self):
        resp = self.client.get("/api/dashboard")
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        self.assertEqual(data["total_vehicles"], 1)

    # ── Maintenance ──────────────────────────────────────────────
    def test_add_maintenance_record(self):
        resp = self.client.post("/maintenance/add", data={
            "vehicle_id": str(self.vehicle_id),
            "service_date": "2024-06-01",
            "service_category": "Oil & Lubrication",
            "component_name": "Engine Oil Change",
            "cost": "1500",
            "status": "Completed",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            r = MaintenanceRecord.query.filter_by(vehicle_id=self.vehicle_id).first()
            self.assertIsNotNone(r)
            self.assertEqual(r.cost, 1500.0)

    def test_maintenance_requires_vehicle(self):
        resp = self.client.post("/maintenance/add", data={
            "vehicle_id": "",
            "service_date": "2024-06-01",
            "service_category": "Brakes",
            "component_name": "Brake Pads",
            "cost": "2000",
            "status": "Completed",
        }, follow_redirects=True)
        with self.app.app_context():
            count = MaintenanceRecord.query.count()
            self.assertEqual(count, 0)

    def test_negative_maintenance_cost_rejected(self):
        resp = self.client.post("/maintenance/add", data={
            "vehicle_id": str(self.vehicle_id),
            "service_date": "2024-06-01",
            "service_category": "Brakes",
            "component_name": "Brake Fluid",
            "cost": "-500",
            "status": "Completed",
        }, follow_redirects=True)
        with self.app.app_context():
            count = MaintenanceRecord.query.count()
            self.assertEqual(count, 0)

    def test_api_maintenance_list(self):
        resp = self.client.get(f"/api/maintenance?vehicle_id={self.vehicle_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json, list)

    # ── Fuel ─────────────────────────────────────────────────────
    def test_add_fuel_record(self):
        resp = self.client.post("/fuel/add", data={
            "vehicle_id": str(self.vehicle_id),
            "date": "2024-07-10",
            "distance_km": "300",
            "quantity": "20",
            "cost": "2000",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            r = FuelRecord.query.filter_by(vehicle_id=self.vehicle_id).first()
            self.assertIsNotNone(r)
            self.assertEqual(r.distance_km, 300.0)

    def test_fuel_efficiency_calculation(self):
        """Verify efficiency calculated correctly (300 km / 20 L = 15 km/L)."""
        from services.fuel_service import calculate_fuel_efficiency
        result = calculate_fuel_efficiency(300, 20, "Petrol")
        self.assertEqual(result["efficiency"], 15.0)
        self.assertEqual(result["unit"], "km/L")

    def test_fuel_efficiency_ev(self):
        """EV should use km/kWh."""
        from services.fuel_service import calculate_fuel_efficiency
        result = calculate_fuel_efficiency(200, 40, "Electric")
        self.assertEqual(result["efficiency"], 5.0)
        self.assertEqual(result["unit"], "km/kWh")

    def test_fuel_zero_quantity_error(self):
        from services.fuel_service import calculate_fuel_efficiency
        result = calculate_fuel_efficiency(100, 0, "Petrol")
        self.assertIsNone(result["efficiency"])
        self.assertIn("error", result)

    def test_cost_per_km_calculation(self):
        from services.fuel_service import calculate_cost_per_km
        result = calculate_cost_per_km(500, 5000)
        self.assertEqual(result, 10.0)

    def test_cost_per_km_zero_distance(self):
        from services.fuel_service import calculate_cost_per_km
        result = calculate_cost_per_km(0, 1000)
        self.assertIsNone(result)

    # ── Expenses ─────────────────────────────────────────────────
    def test_add_expense(self):
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": str(self.vehicle_id),
            "date": "2024-08-15",
            "category": "Insurance",
            "amount": "12000",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            e = ExpenseRecord.query.filter_by(vehicle_id=self.vehicle_id).first()
            self.assertIsNotNone(e)
            self.assertEqual(e.amount, 12000.0)

    def test_negative_expense_rejected(self):
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": str(self.vehicle_id),
            "date": "2024-08-15",
            "category": "Insurance",
            "amount": "-500",
        }, follow_redirects=True)
        with self.app.app_context():
            count = ExpenseRecord.query.count()
            self.assertEqual(count, 0)

    def test_zero_expense_rejected(self):
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": str(self.vehicle_id),
            "date": "2024-08-15",
            "category": "Other",
            "amount": "0",
        }, follow_redirects=True)
        with self.app.app_context():
            count = ExpenseRecord.query.count()
            self.assertEqual(count, 0)

    # ── Decision Support ─────────────────────────────────────────
    def test_decisions_page_loads(self):
        resp = self.client.get("/decisions")
        self.assertEqual(resp.status_code, 200)

    def test_vehicle_decision_page(self):
        resp = self.client.get(f"/decisions/{self.vehicle_id}")
        self.assertEqual(resp.status_code, 200)

    def test_decision_service_maintain(self):
        from services.decision_service import generate_decision
        with self.app.app_context():
            v = Vehicle.query.get(self.vehicle_id)
            v.health_score = 85.0
            v.health_status = "Healthy"
            v.reported_issues = 0
            v.service_history = "Full"
            v.estimated_resale_value = 900000
            decision = generate_decision(v, v.maintenance_records, v.expense_records, v.fuel_records)
        self.assertIn(decision["recommendation"], ["Maintain", "Repair", "Sell", "Insufficient Data"])

    # ── Valuation ────────────────────────────────────────────────
    def test_valuation_page_loads(self):
        resp = self.client.get("/valuation")
        self.assertEqual(resp.status_code, 200)

    # ── Reports ──────────────────────────────────────────────────
    def test_reports_page_loads(self):
        resp = self.client.get("/reports")
        self.assertEqual(resp.status_code, 200)

    # ── Maintenance reminder service ──────────────────────────────
    def test_overdue_reminder(self):
        from services.maintenance_service import classify_maintenance_status
        from datetime import timedelta
        past_date = date.today() - timedelta(days=10)
        result = classify_maintenance_status(date.today(), past_date, None, 0)
        self.assertEqual(result["status"], "Overdue")

    def test_upcoming_reminder(self):
        from services.maintenance_service import classify_maintenance_status
        from datetime import timedelta
        soon = date.today() + timedelta(days=15)
        result = classify_maintenance_status(date.today(), soon, None, 0)
        self.assertEqual(result["status"], "Upcoming")

    def test_ok_reminder(self):
        from services.maintenance_service import classify_maintenance_status
        from datetime import timedelta
        future = date.today() + timedelta(days=90)
        result = classify_maintenance_status(date.today(), future, None, 0)
        self.assertEqual(result["status"], "OK")

    def test_reminder_is_rule_based_label(self):
        from services.maintenance_service import classify_maintenance_status
        result = classify_maintenance_status(date.today(), None, None, 0)
        self.assertIn("Rule-based", result["reminder_type"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
