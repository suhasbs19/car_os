"""
Tests for Expenses Module: Add Expense Button, Modal, Form, Server Validation,
AJAX/JSON endpoints, and Anti-Double-Counting Accounting in CAR OS.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from datetime import date
from app import create_app
from models import db, Vehicle, ExpenseRecord, MaintenanceRecord


class TestExpensesModule(unittest.TestCase):

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            # Seed a test vehicle
            v = Vehicle(
                make="Hyundai",
                model="Creta",
                variant="SX (O)",
                registration_number="MH12AB9999",
                manufacturing_year=2022,
                odometer_km=18000,
                fuel_type="Petrol",
                transmission="Manual",
                service_history="Full",
                reported_issues=0,
                health_score=88.0,
                health_status="Good",
                original_showroom_price=1750000.0,
                current_market_price=1500000.0,
                estimated_resale_value=1420000.0,
            )
            db.session.add(v)
            db.session.commit()
            self.vehicle_id = v.id

            # Seed a maintenance record for testing linked maintenance
            m = MaintenanceRecord(
                vehicle_id=v.id,
                service_date=date(2024, 5, 10),
                service_category="Routine Service",
                component_name="Engine Oil & Filters",
                cost=4500.0,
                status="Completed",
                description="Authorized service center",
            )
            db.session.add(m)
            db.session.commit()
            self.maintenance_id = m.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ── Page Loading & UI Elements ──────────────────────────────

    def test_expenses_page_loads_and_has_add_button_and_modal(self):
        """Verify GET /expenses loads (200) and contains the Add Expense buttons and modal."""
        resp = self.client.get("/expenses")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        # Header and card buttons
        self.assertIn("btn-header-add-expense", html)
        self.assertIn("btn-card-add-expense", html)
        self.assertIn("+ Add Expense", html)
        # Modal and form
        self.assertIn('id="expense-modal"', html)
        self.assertIn('id="add-expense-form"', html)
        self.assertIn("openExpenseModal()", html)
        self.assertIn("closeExpenseModal()", html)
        # Standard categories present in modal options
        self.assertIn("Insurance", html)
        self.assertIn("Registration/Tax", html)
        self.assertIn("Cleaning", html)
        self.assertIn("Tyres", html)
        self.assertTrue("Parking &amp; Tolls" in html or "Parking & Tolls" in html)

    def test_add_expense_standalone_page_loads(self):
        """Verify GET /expenses/add loads (200) and has necessary form fields."""
        resp = self.client.get("/expenses/add")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("New Expense Record", html)
        self.assertIn('name="vehicle_id"', html)
        self.assertIn('name="date"', html)
        self.assertIn('name="category"', html)
        self.assertIn('name="amount"', html)
        self.assertIn('name="linked_maintenance_id"', html)
        self.assertIn('name="description"', html)

    # ── Standard Form Submission ────────────────────────────────

    def test_add_expense_form_success(self):
        """Standard form POST creates an expense record in the database."""
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": str(self.vehicle_id),
            "date": "2024-09-15",
            "category": "Tyres",
            "amount": "8500.50",
            "description": "Replaced two front tyres",
            "from_page": "expenses",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            exp = ExpenseRecord.query.filter_by(vehicle_id=self.vehicle_id, category="Tyres").first()
            self.assertIsNotNone(exp)
            self.assertEqual(exp.amount, 8500.50)
            self.assertEqual(exp.description, "Replaced two front tyres")
            self.assertIsNone(exp.linked_maintenance_id)

    def test_add_expense_with_linked_maintenance(self):
        """Expense can be linked to an existing maintenance record."""
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": str(self.vehicle_id),
            "date": "2024-05-10",
            "category": "Maintenance/Repair",
            "amount": "4500.00",
            "description": "Invoice for Service #1",
            "linked_maintenance_id": str(self.maintenance_id),
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            exp = ExpenseRecord.query.filter_by(linked_maintenance_id=self.maintenance_id).first()
            self.assertIsNotNone(exp)
            self.assertEqual(exp.amount, 4500.00)
            self.assertEqual(exp.linked_maintenance_id, self.maintenance_id)

    # ── Server-Side Validation ──────────────────────────────────

    def test_reject_missing_vehicle_id(self):
        """Missing vehicle_id is rejected without inserting."""
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": "",
            "date": "2024-09-15",
            "category": "Insurance",
            "amount": "12000",
        }, follow_redirects=True)
        with self.app.app_context():
            count = ExpenseRecord.query.count()
            self.assertEqual(count, 0)

    def test_reject_nonexistent_vehicle_id(self):
        """Non-existent vehicle_id is rejected by server."""
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": "99999",
            "date": "2024-09-15",
            "category": "Insurance",
            "amount": "12000",
        }, follow_redirects=True)
        with self.app.app_context():
            count = ExpenseRecord.query.count()
            self.assertEqual(count, 0)

    def test_reject_zero_amount(self):
        """Zero amount is rejected."""
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": str(self.vehicle_id),
            "date": "2024-09-15",
            "category": "Cleaning",
            "amount": "0",
        }, follow_redirects=True)
        with self.app.app_context():
            count = ExpenseRecord.query.count()
            self.assertEqual(count, 0)

    def test_reject_negative_amount(self):
        """Negative amount is rejected."""
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": str(self.vehicle_id),
            "date": "2024-09-15",
            "category": "Fuel",
            "amount": "-1500",
        }, follow_redirects=True)
        with self.app.app_context():
            count = ExpenseRecord.query.count()
            self.assertEqual(count, 0)

    def test_reject_empty_category(self):
        """Empty category is rejected."""
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": str(self.vehicle_id),
            "date": "2024-09-15",
            "category": "",
            "amount": "1000",
        }, follow_redirects=True)
        with self.app.app_context():
            count = ExpenseRecord.query.count()
            self.assertEqual(count, 0)

    def test_reject_invalid_date(self):
        """Invalid date string is rejected per specification."""
        resp = self.client.post("/expenses/add", data={
            "vehicle_id": str(self.vehicle_id),
            "date": "invalid-date-string",
            "category": "Parking & Tolls",
            "amount": "250",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            exp = ExpenseRecord.query.filter_by(category="Parking & Tolls").first()
            self.assertIsNone(exp)

    # ── AJAX / Modal JSON API ───────────────────────────────────

    def test_ajax_add_expense_success(self):
        """AJAX request with X-Requested-With header returns 201 JSON with created expense."""
        resp = self.client.post(
            "/expenses/add",
            data={
                "vehicle_id": str(self.vehicle_id),
                "date": "2024-10-01",
                "category": "Registration/Tax",
                "amount": "3200",
                "description": "Annual road tax",
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["expense"]["registration_number"], "MH12AB9999")
        self.assertEqual(data["expense"]["category"], "Registration/Tax")
        self.assertEqual(data["expense"]["amount"], 3200.0)
        self.assertIn("₹", data["expense"]["amount_formatted"])

        with self.app.app_context():
            count = ExpenseRecord.query.filter_by(category="Registration/Tax").count()
            self.assertEqual(count, 1)

    def test_ajax_validation_error_response(self):
        """AJAX request with invalid data returns 400 JSON with error list."""
        resp = self.client.post(
            "/expenses/add",
            data={
                "vehicle_id": str(self.vehicle_id),
                "date": "2024-10-01",
                "category": "Insurance",
                "amount": "-5000",
            },
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("errors", data)
        self.assertTrue(any("greater than zero" in err for err in data["errors"]))

    # ── Anti-Double-Counting Rules ──────────────────────────────

    def test_anti_double_counting_tco_calculation(self):
        """
        Verify that an expense linked to maintenance is excluded from
        non_maint_expenses in TCO calculations to prevent double-counting.
        """
        with self.app.app_context():
            # 1. Add an independent expense (e.g. Insurance ₹10,000)
            exp1 = ExpenseRecord(
                vehicle_id=self.vehicle_id,
                date=date(2024, 1, 1),
                category="Insurance",
                amount=10000.0,
                linked_maintenance_id=None,
            )
            # 2. Add an expense that matches the maintenance invoice (₹4,500)
            exp2 = ExpenseRecord(
                vehicle_id=self.vehicle_id,
                date=date(2024, 5, 10),
                category="Maintenance/Repair",
                amount=4500.0,
                linked_maintenance_id=self.maintenance_id,
            )
            db.session.add_all([exp1, exp2])
            db.session.commit()

        # Call list_expenses or analytics endpoint to check calculations
        resp = self.client.get(f"/expenses?vehicle_id={self.vehicle_id}")
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            all_expenses = ExpenseRecord.query.filter_by(vehicle_id=self.vehicle_id).all()
            non_maint = [e for e in all_expenses if e.linked_maintenance_id is None]
            maint_linked = [e for e in all_expenses if e.linked_maintenance_id is not None]

            self.assertEqual(len(non_maint), 1)
            self.assertEqual(non_maint[0].amount, 10000.0)
            self.assertEqual(len(maint_linked), 1)
            self.assertEqual(maint_linked[0].amount, 4500.0)

    # ── Delete Expense ──────────────────────────────────────────

    def test_delete_expense(self):
        """Delete an expense record."""
        with self.app.app_context():
            exp = ExpenseRecord(
                vehicle_id=self.vehicle_id,
                date=date(2024, 6, 1),
                category="Cleaning",
                amount=600.0,
            )
            db.session.add(exp)
            db.session.commit()
            exp_id = exp.id

        resp = self.client.post(f"/expenses/{exp_id}/delete", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            self.assertIsNone(ExpenseRecord.query.get(exp_id))


if __name__ == "__main__":
    unittest.main()
