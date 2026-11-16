"""
Tests for CAR OS OBD-II diagnostic data during vehicle registration.
Validates:
- Saving a vehicle with no OBD data (optionality)
- Saving a vehicle with valid OBD data and timestamps
- Preservation of missing fields (no fabrication)
- Numeric range validation and rejection with clear messages
- DTC format validation (standard P, C, B, U + 4 hex digits)
- Database association with correct vehicle
- Display of diagnostic telemetry, DTC explanations, and empty-state messaging
- Integration with health scoring, maintenance recommendations, and decision support
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from app import create_app
from models import db, Vehicle, OBDRecord
from services.obd_service import validate_obd_data, analyze_obd_record, explain_dtc
from services.health_service import calculate_health_score
from services.maintenance_service import get_upcoming_maintenance
from services.decision_service import generate_decision


class TestOBDDiagnostics(unittest.TestCase):

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _post_vehicle(self, data_overrides=None):
        data = {
            "registration_number": "KA01AB1111",
            "make": "Toyota",
            "model": "Innova",
            "manufacturing_year": "2021",
            "odometer_km": "45000",
            "fuel_type": "Diesel",
            "service_history": "Full",
            "reported_issues": "0",
            "notes": "Fleet vehicle",
        }
        if data_overrides:
            data.update(data_overrides)
        return self.client.post("/vehicles/add", data=data, follow_redirects=True)

    def test_save_vehicle_with_no_obd_data(self):
        """Vehicle is saved cleanly with no OBD data; no OBDRecord created."""
        resp = self._post_vehicle()
        self.assertEqual(resp.status_code, 200)
        with self.app.app_context():
            v = Vehicle.query.filter_by(registration_number="KA01AB1111").first()
            self.assertIsNotNone(v)
            self.assertIsNone(v.latest_obd)
            self.assertEqual(v.obd_records.count(), 0)

    def test_save_vehicle_with_valid_obd_data(self):
        """Saving a vehicle with valid OBD fields creates associated OBDRecord with timestamp."""
        resp = self._post_vehicle({
            "registration_number": "MH14EF5555",
            "obd_connection_status": "Connected",
            "obd_data_source": "Manual",
            "engine_rpm": "820",
            "vehicle_speed_kmh": "0",
            "coolant_temp_c": "89.5",
            "engine_load_pct": "24.5",
            "throttle_pos_pct": "14.2",
            "fuel_system_status": "Closed loop",
            "battery_voltage": "12.65",
            "dtc_codes": "P0420, P0300",
            "obd_notes": "Scanned with OBDLink MX+",
        })
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            v = Vehicle.query.filter_by(registration_number="MH14EF5555").first()
            self.assertIsNotNone(v)
            obd = v.latest_obd
            self.assertIsNotNone(obd)
            self.assertEqual(obd.vehicle_id, v.id)
            self.assertEqual(obd.connection_status, "Connected")
            self.assertEqual(obd.data_source, "Manual")
            self.assertEqual(obd.engine_rpm, 820.0)
            self.assertEqual(obd.vehicle_speed_kmh, 0.0)
            self.assertEqual(obd.coolant_temp_c, 89.5)
            self.assertEqual(obd.engine_load_pct, 24.5)
            self.assertEqual(obd.throttle_pos_pct, 14.2)
            self.assertEqual(obd.battery_voltage, 12.65)
            self.assertEqual(obd.fuel_system_status, "Closed loop")
            self.assertEqual(obd.notes, "Scanned with OBDLink MX+")
            self.assertEqual(obd.dtc_list, ["P0420", "P0300"])
            self.assertIsNotNone(obd.timestamp)

    def test_missing_readings_remain_none_never_fabricated(self):
        """Omitted OBD fields remain None; system never fabricates placeholder values."""
        resp = self._post_vehicle({
            "registration_number": "DL08CD9999",
            "obd_connection_status": "Connected",
            "engine_rpm": "750",
            "battery_voltage": "12.4",
            # Speed, coolant, load, throttle, DTCs intentionally omitted
        })
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            v = Vehicle.query.filter_by(registration_number="DL08CD9999").first()
            obd = v.latest_obd
            self.assertIsNotNone(obd)
            self.assertEqual(obd.engine_rpm, 750.0)
            self.assertEqual(obd.battery_voltage, 12.4)
            self.assertIsNone(obd.vehicle_speed_kmh)
            self.assertIsNone(obd.coolant_temp_c)
            self.assertIsNone(obd.engine_load_pct)
            self.assertIsNone(obd.throttle_pos_pct)
            self.assertEqual(obd.dtc_list, [])

    def test_reject_negative_rpm(self):
        resp = self._post_vehicle({"engine_rpm": "-100"})
        self.assertIn(b"Engine RPM must be between 0 and 15,000", resp.data)

    def test_reject_excessive_rpm(self):
        resp = self._post_vehicle({"engine_rpm": "18000"})
        self.assertIn(b"Engine RPM must be between 0 and 15,000", resp.data)

    def test_reject_invalid_speed(self):
        resp_neg = self._post_vehicle({"vehicle_speed_kmh": "-5"})
        self.assertIn(b"Vehicle speed must be between 0 and 400", resp_neg.data)

        resp_high = self._post_vehicle({"vehicle_speed_kmh": "450"})
        self.assertIn(b"Vehicle speed must be between 0 and 400", resp_high.data)

    def test_reject_invalid_coolant_temperature(self):
        resp_low = self._post_vehicle({"coolant_temp_c": "-55"})
        self.assertIn(b"temperature must be between -40", resp_low.data)

        resp_high = self._post_vehicle({"coolant_temp_c": "180"})
        self.assertIn(b"temperature must be between -40", resp_high.data)

    def test_reject_invalid_engine_load(self):
        resp = self._post_vehicle({"engine_load_pct": "125"})
        self.assertIn(b"Engine load must be between 0% and 100%", resp.data)

    def test_reject_invalid_throttle_position(self):
        resp = self._post_vehicle({"throttle_pos_pct": "-10"})
        self.assertIn(b"Throttle position must be between 0% and 100%", resp.data)

    def test_reject_invalid_battery_voltage(self):
        resp = self._post_vehicle({"battery_voltage": "35"})
        self.assertIn(b"Battery voltage must be between 0V and 30V", resp.data)

    def test_reject_malformed_dtc_codes(self):
        """Malformed DTCs are rejected with clear formatting instructions."""
        resp = self._post_vehicle({"dtc_codes": "INVALID_CODE, 1234, P12345"})
        self.assertIn(b"Invalid DTC code", resp.data)

    def test_accept_multiple_valid_dtc_formats(self):
        """Standard OBD-II codes with P, C, B, U prefixes are accepted and parsed."""
        has_data, cleaned, errors = validate_obd_data({
            "dtc_codes": "P0420, B0001; C0035  U0100",
        })
        self.assertTrue(has_data)
        self.assertEqual(errors, [])
        self.assertEqual(cleaned["dtc_codes"], ["P0420", "B0001", "C0035", "U0100"])

    def test_display_diagnostic_information_on_detail_page(self):
        """Vehicle details view displays OBD telemetry, connection status, timestamp, and DTC explanations."""
        self._post_vehicle({
            "registration_number": "KA04XY7777",
            "obd_connection_status": "Connected",
            "engine_rpm": "800",
            "coolant_temp_c": "88",
            "battery_voltage": "12.6",
            "dtc_codes": "P0420",
        })
        with self.app.app_context():
            v = Vehicle.query.filter_by(registration_number="KA04XY7777").first()
            vid = v.id

        resp = self.client.get(f"/vehicles/{vid}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"OBD-II Diagnostic Telemetry", resp.data)
        self.assertIn(b"Connected", resp.data)
        self.assertIn(b"P0420", resp.data)
        self.assertIn(b"Catalyst System Efficiency", resp.data)
        self.assertIn(b"Last recorded:", resp.data)

    def test_display_empty_message_when_no_obd_data(self):
        """Vehicle with no OBD data displays clear informative empty-state message."""
        self._post_vehicle({"registration_number": "TN07ZZ1234"})
        with self.app.app_context():
            v = Vehicle.query.filter_by(registration_number="TN07ZZ1234").first()
            vid = v.id

        resp = self.client.get(f"/vehicles/{vid}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"No OBD-II diagnostic data recorded for this vehicle yet", resp.data)

    def test_dtc_explanation_and_condition_analysis(self):
        """analyze_obd_record returns correct DTC breakdown and detects overheating and low voltage."""
        with self.app.app_context():
            v = Vehicle(
                make="Tata", model="Safari", registration_number="MH02GH8888",
                manufacturing_year=2018, odometer_km=85000,
            )
            db.session.add(v)
            db.session.flush()

            obd = OBDRecord(
                vehicle_id=v.id,
                connection_status="Connected",
                coolant_temp_c=109.0,  # Overheating flag
                battery_voltage=11.5,   # Low voltage flag
                dtc_codes='["P0300"]',  # Critical misfire code
            )
            db.session.add(obd)
            db.session.commit()

            analysis = analyze_obd_record(obd)
            self.assertTrue(analysis["has_data"])

            flag_types = [f["type"] for f in analysis["critical_flags"]]
            self.assertIn("Engine Overheating", flag_types)
            self.assertIn("Low Battery Voltage", flag_types)
            self.assertIn("Critical DTC", flag_types)

            dtc_info = explain_dtc("P0300")
            self.assertEqual(dtc_info["severity"], "Critical")
            self.assertIn("Misfire", dtc_info["title"])

    def test_obd_integration_with_health_scoring_and_maintenance(self):
        """OBD active trouble codes and condition flags populate maintenance reminders and advisory penalties."""
        with self.app.app_context():
            v = Vehicle(
                make="Honda", model="Amaze", registration_number="DL03KL5555",
                manufacturing_year=2020, odometer_km=30000, service_history="Full",
            )
            db.session.add(v)
            db.session.flush()

            obd = OBDRecord(
                vehicle_id=v.id,
                connection_status="Connected",
                coolant_temp_c=108.0,
                battery_voltage=12.5,
                dtc_codes='["P0420"]',
            )
            db.session.add(obd)
            db.session.commit()

            # Health scoring incorporates advisory penalty without calculating score from OBD alone
            h = calculate_health_score(v.manufacturing_year, v.odometer_km, v.service_history, 0, obd_record=obd)
            self.assertGreater(h["breakdown"]["obd_penalty"], 0)
            self.assertIn("Elevated coolant temperature", str(h["breakdown"]["obd_advisory_notes"]))

            # Upcoming maintenance includes OBD telemetry recommendations
            reminders = get_upcoming_maintenance(v.id, [], v.odometer_km, obd_record=obd)
            reminder_components = [r["component"] for r in reminders]
            self.assertTrue(any("Overheating" in c for c in reminder_components))
            self.assertTrue(any("P0420" in c for c in reminder_components))

    def test_obd_integration_with_decision_service(self):
        """Decision service includes OBD fault codes in human-readable rationale."""
        with self.app.app_context():
            v = Vehicle(
                make="Mahindra", model="Bolero", registration_number="MH15PQ3333",
                manufacturing_year=2012, odometer_km=180000, service_history="None",
                reported_issues=3, health_score=35.0, estimated_resale_value=120000.0,
            )
            db.session.add(v)
            db.session.flush()

            obd = OBDRecord(
                vehicle_id=v.id,
                connection_status="Connected",
                dtc_codes='["P0300"]',
            )
            db.session.add(obd)
            db.session.commit()

            decision = generate_decision(v, [], [], [])
            self.assertEqual(decision["recommendation"], "Sell")
            reasons_str = " ".join(decision["reasons"])
            self.assertIn("P0300", reasons_str)
            self.assertIn("Critical powertrain", reasons_str)


if __name__ == "__main__":
    unittest.main()
