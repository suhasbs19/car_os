"""
Tests for vehicle CRUD, validation, and database persistence.
Uses in-memory SQLite test database.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from app import create_app
from models import db, Vehicle
from datetime import date


class TestVehicleModel(unittest.TestCase):

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _add_vehicle(self, reg="MH12AB1234", make="Hyundai", model="Creta",
                     year=2020, odo=15000, fuel="Petrol"):
        return self.client.post("/vehicles/add", data={
            "registration_number": reg,
            "make": make,
            "model": model,
            "manufacturing_year": str(year),
            "odometer_km": str(odo),
            "fuel_type": fuel,
            "service_history": "Full",
            "reported_issues": "0",
        }, follow_redirects=True)

    def test_add_vehicle_success(self):
        resp = self._add_vehicle()
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            v = Vehicle.query.filter_by(registration_number="MH12AB1234").first()
            self.assertIsNotNone(v)
            self.assertEqual(v.make, "Hyundai")

    def test_health_score_calculated_automatically(self):
        self._add_vehicle()
        with self.app.app_context():
            v = Vehicle.query.filter_by(registration_number="MH12AB1234").first()
            self.assertIsNotNone(v.health_score)
            self.assertIsNotNone(v.health_status)
            self.assertIn(v.health_status, ["Healthy", "Attention", "Critical"])

    def test_resale_value_calculated_automatically(self):
        self._add_vehicle()
        with self.app.app_context():
            v = Vehicle.query.filter_by(registration_number="MH12AB1234").first()
            self.assertIsNotNone(v.estimated_resale_value)
            self.assertGreater(v.estimated_resale_value, 0)

    def test_duplicate_registration_rejected(self):
        self._add_vehicle(reg="DL01AA0001")
        resp = self._add_vehicle(reg="DL01AA0001")
        self.assertIn(b"already exists", resp.data)
        with self.app.app_context():
            count = Vehicle.query.filter_by(registration_number="DL01AA0001").count()
            self.assertEqual(count, 1)

    def test_invalid_year_rejected(self):
        resp = self._add_vehicle(year=1800)
        self.assertIn(b"1900", resp.data)

    def test_negative_odometer_rejected(self):
        resp = self._add_vehicle(odo=-100)
        self.assertIn(b"negative", resp.data.lower())

    def test_vehicle_list_page(self):
        self._add_vehicle()
        resp = self.client.get("/vehicles")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"MH12AB1234", resp.data)

    def test_vehicle_detail_page(self):
        self._add_vehicle()
        with self.app.app_context():
            v = Vehicle.query.first()
            vid = v.id
        resp = self.client.get(f"/vehicles/{vid}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Hyundai", resp.data)

    def test_delete_vehicle(self):
        self._add_vehicle(reg="KA05CD5678")
        with self.app.app_context():
            v = Vehicle.query.filter_by(registration_number="KA05CD5678").first()
            vid = v.id
        resp = self.client.post(f"/vehicles/{vid}/delete", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            v = Vehicle.query.get(vid)
            self.assertIsNone(v)

    def test_404_for_nonexistent_vehicle(self):
        resp = self.client.get("/vehicles/99999")
        self.assertEqual(resp.status_code, 404)

    def test_empty_vehicle_list(self):
        resp = self.client.get("/vehicles")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No vehicles", resp.data)

    def test_dashboard_empty_state(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"0", resp.data)  # Total vehicles = 0

    def test_api_vehicles_empty(self):
        resp = self.client.get("/api/vehicles")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json, [])

    def test_api_vehicles_returns_vehicle(self):
        self._add_vehicle()
        resp = self.client.get("/api/vehicles")
        self.assertEqual(resp.status_code, 200)
        data = resp.json
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["registration_number"], "MH12AB1234")


if __name__ == "__main__":
    unittest.main(verbosity=2)
