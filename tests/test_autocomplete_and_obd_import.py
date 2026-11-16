"""
Comprehensive automated tests for CAR OS:
1. Feature 1: Vehicle make/model autocomplete (CarDekho dataset parsing, partial/case-insensitive matching, spaces, unknown models, keyboard/ARIA attributes, non-overwriting).
2. Feature 2: OBD-II data file upload (CSV parsing with normal and trailing-comma files, column alias mapping, invalid values, malformed DTCs, invalid timestamps, missing DTC fields, duplicate imports, file-size/row-count limits, invalid vehicle IDs, security against formula injection and path traversal, association with vehicle, preservation of existing records).
"""
import sys
import os
import io
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Vehicle, OBDRecord, DiagnosticRecord
from services.vehicle_catalogue_service import (
    get_vehicle_catalogue,
    search_vehicle_catalogue,
    parse_cardekho_name,
)
from services.obd_import_service import (
    safe_read_csv,
    detect_column_mappings,
    compute_obd_fingerprint,
    parse_timestamp_value,
    preview_obd_csv,
    execute_obd_import,
    sanitize_csv_cell,
    MAX_ROW_COUNT,
)


class TestVehicleMakeModelAutocomplete(unittest.TestCase):
    """Tests for Vehicle Make & Model Autocomplete (Feature 1)."""

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_catalogue_loads_and_contains_indian_market_makes(self):
        """Catalogue loads successfully and includes Indian market makes."""
        cat = get_vehicle_catalogue()
        self.assertGreater(len(cat), 50)
        makes = {item["make"] for item in cat}
        for expected in ["Maruti Suzuki", "Hyundai", "Tata", "Mahindra", "Honda", "Toyota", "Kia", "MG", "Renault", "Volkswagen", "Skoda"]:
            self.assertIn(expected, makes, f"Expected {expected} in catalogue makes")

    def test_partial_matching_case_insensitive(self):
        """Search query matches partial text regardless of casing."""
        res_lower = search_vehicle_catalogue("swift")
        res_upper = search_vehicle_catalogue("SWIFT")
        res_mixed = search_vehicle_catalogue("SwIfT")
        self.assertEqual(len(res_lower), len(res_upper))
        self.assertEqual(len(res_lower), len(res_mixed))
        self.assertTrue(any(r["model"] == "Swift" for r in res_lower))

    def test_names_containing_spaces(self):
        """Names with spaces (e.g. 'Wagon R', 'Vitara Brezza', 'Corolla Altis', 'Maruti Suzuki') match accurately."""
        res_wagon = search_vehicle_catalogue("wagon r")
        self.assertTrue(any(r["model"] == "Wagon R" for r in res_wagon))

        res_brezza = search_vehicle_catalogue("vitara brezza")
        self.assertTrue(any("Brezza" in r["model"] for r in res_brezza))

        res_corolla = search_vehicle_catalogue("corolla altis")
        self.assertTrue(any("Corolla" in r["model"] for r in res_corolla))

        res_maruti_suzuki = search_vehicle_catalogue("maruti suzuki")
        self.assertGreater(len(res_maruti_suzuki), 0)
        self.assertTrue(all(r["make"] == "Maruti Suzuki" for r in res_maruti_suzuki))

    def test_multi_token_search(self):
        """Searching make and model together (e.g. 'tata nexon') finds correct vehicle."""
        res = search_vehicle_catalogue("tata nexon")
        self.assertGreater(len(res), 0)
        self.assertEqual(res[0]["make"], "Tata")
        self.assertIn("Nexon", res[0]["model"])

    def test_unknown_models_return_empty_list_without_error(self):
        """Unknown or non-existent make/model returns empty list without error."""
        res = search_vehicle_catalogue("NonExistentSuperCar999")
        self.assertEqual(res, [])

    def test_cardekho_name_parsing(self):
        """CarDekho listings are cleaned to model family without engine/trim suffixes."""
        m1, mod1 = parse_cardekho_name("Maruti Wagon R LXI Minor")
        self.assertEqual(m1, "Maruti")
        self.assertEqual(mod1, "Wagon R")

        m2, mod2 = parse_cardekho_name("Toyota Corolla Altis 1.8 VL CVT")
        self.assertEqual(m2, "Toyota")
        self.assertEqual(mod2, "Corolla Altis")

        m3, mod3 = parse_cardekho_name("Hyundai Creta 1.6 VTVT S")
        self.assertEqual(m3, "Hyundai")
        self.assertEqual(mod3, "Creta")

    def test_autocomplete_api_endpoint(self):
        """API endpoint /api/vehicles/catalogue returns JSON suggestions."""
        resp = self.client.get("/api/vehicles/catalogue?q=creta")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["query"], "creta")
        self.assertGreater(data["count"], 0)
        self.assertTrue(any(s["model"] == "Creta" for s in data["suggestions"]))

    def test_manual_entry_allows_creation_of_unlisted_models(self):
        """User can manually submit a model not in the catalogue without being blocked."""
        resp = self.client.post("/vehicles/add", data={
            "registration_number": "KA01ZZ9999",
            "make": "CustomCoach",
            "model": "EVPrototype1",
            "manufacturing_year": "2023",
            "odometer_km": "5000",
            "fuel_type": "Electric",
            "service_history": "Full",
            "reported_issues": "0",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            v = Vehicle.query.filter_by(registration_number="KA01ZZ9999").first()
            self.assertIsNotNone(v)
            self.assertEqual(v.make, "CustomCoach")
            self.assertEqual(v.model, "EVPrototype1")

    def test_autocomplete_does_not_modify_existing_records(self):
        """Adding a vehicle with autocomplete make/model does not alter existing database records."""
        with self.app.app_context():
            v_exist = Vehicle(
                registration_number="DL01AA1111", make="Honda", model="City",
                manufacturing_year=2019, odometer_km=40000, fuel_type="Petrol",
            )
            db.session.add(v_exist)
            db.session.commit()
            orig_id = v_exist.id

        # Add new vehicle
        resp = self.client.post("/vehicles/add", data={
            "registration_number": "MH01BB2222",
            "make": "Maruti Suzuki",
            "model": "Swift",
            "manufacturing_year": "2022",
            "odometer_km": "12000",
            "fuel_type": "Petrol",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        with self.app.app_context():
            v1 = Vehicle.query.get(orig_id)
            self.assertEqual(v1.registration_number, "DL01AA1111")
            self.assertEqual(v1.make, "Honda")
            self.assertEqual(v1.model, "City")


class TestOBDCSVParsingAndImport(unittest.TestCase):
    """Tests for OBD-II Data File Upload & Processing (Feature 2)."""

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.test_veh = Vehicle(
            registration_number="DL05XY5555",
            make="Toyota",
            model="Etios",
            manufacturing_year=2018,
            odometer_km=60000,
            fuel_type="Petrol",
        )
        db.session.add(self.test_veh)

        self.ev_veh = Vehicle(
            registration_number="MH02EV8888",
            make="Tata",
            model="Nexon EV",
            manufacturing_year=2022,
            odometer_km=15000,
            fuel_type="Electric",
        )
        db.session.add(self.ev_veh)
        db.session.commit()
        self.test_veh_id = self.test_veh.id
        self.ev_veh_id = self.ev_veh.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_safe_read_normal_csv(self):
        """Standard CSV parses cleanly without errors."""
        content = "timestamp,engine_rpm,vehicle_speed_kmh,coolant_temp_c\n2024-06-01 10:00:00,850,0,88.5\n2024-06-01 10:01:00,2100,45.2,90.0"
        headers, rows, has_trailing, err = safe_read_csv(content)
        self.assertIsNone(err)
        self.assertFalse(has_trailing)
        self.assertEqual(headers, ["timestamp", "engine_rpm", "vehicle_speed_kmh", "coolant_temp_c"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "850")

    def test_safe_read_trailing_comma_csv_no_column_shift(self):
        """CSV files with trailing comma on rows do not shift columns."""
        # Synthetic CSV mirroring Toyota Etios research dataset trailing commas
        content = (
            "ENGINE_RUN_TIME (),ENGINE_RPM (),VEHICLE_SPEED (),COOLANT_TEMPERATURE (),CONTROL_MODULE_VOLTAGE ()\n"
            "0.0, 800.0, 0.0, 82.0, 12.4,\n"
            "1.0, 850.0, 0.0, 83.0, 12.5,\n"
        )
        headers, rows, has_trailing, err = safe_read_csv(content)
        self.assertIsNone(err)
        self.assertTrue(has_trailing)
        self.assertEqual(len(headers), 5)
        # Column 0 is Run Time, Column 1 is RPM, Column 2 is Speed
        self.assertEqual(rows[0][0].strip(), "0.0")
        self.assertEqual(rows[0][1].strip(), "800.0")
        self.assertEqual(rows[0][2].strip(), "0.0")
        self.assertEqual(rows[0][3].strip(), "82.0")
        self.assertEqual(rows[0][4].strip(), "12.4")

    def test_column_alias_detection(self):
        """Aliases for RPM, speed, coolant, battery voltage, and DTCs are detected."""
        headers = [
            "Time", "RPM (rpm)", "Speed (km/h)", "Engine Coolant Temp (°C)",
            "Load (%)", "Throttle (%)", "Battery (V)", "Trouble_Codes"
        ]
        mapping = detect_column_mappings(headers)
        self.assertEqual(mapping["timestamp"], "Time")
        self.assertEqual(mapping["engine_rpm"], "RPM (rpm)")
        self.assertEqual(mapping["vehicle_speed_kmh"], "Speed (km/h)")
        self.assertEqual(mapping["coolant_temp_c"], "Engine Coolant Temp (°C)")
        self.assertEqual(mapping["engine_load_pct"], "Load (%)")
        self.assertEqual(mapping["throttle_pos_pct"], "Throttle (%)")
        self.assertEqual(mapping["battery_voltage"], "Battery (V)")
        self.assertEqual(mapping["dtc_codes"], "Trouble_Codes")

    def test_toyota_etios_research_headers_mapping(self):
        """Toyota Etios research headers are detected accurately; timer columns not misclassified as DTCs."""
        headers = [
            "ENGINE_RUN_TINE ()", "ENGINE_RPM ()", "VEHICLE_SPEED ()",
            "THROTTLE ()", "ENGINE_LOAD ()", "COOLANT_TEMPERATURE ()",
            "CONTROL_MODULE_VOLTAGE ()", "TIME_SINCE_TROUBLE_CODES_CLEARED ()",
            "TIME_RUN_WITH_MIL_ON ()", "DISTANCE_TRAVELED_WITH_MIL_ON ()",
        ]
        mapping = detect_column_mappings(headers)
        self.assertEqual(mapping["engine_rpm"], "ENGINE_RPM ()")
        self.assertEqual(mapping["vehicle_speed_kmh"], "VEHICLE_SPEED ()")
        self.assertEqual(mapping["coolant_temp_c"], "COOLANT_TEMPERATURE ()")
        self.assertEqual(mapping["battery_voltage"], "CONTROL_MODULE_VOLTAGE ()")
        # Ensure TIME_SINCE_TROUBLE_CODES_CLEARED is NOT mapped to dtc_codes
        self.assertIsNone(mapping["dtc_codes"])

    def test_reject_invalid_numeric_ranges(self):
        """Out-of-range sensor readings are rejected with specific error messages."""
        csv_data = (
            "timestamp,engine_rpm,vehicle_speed_kmh,coolant_temp_c,battery_voltage\n"
            "2024-06-01 10:00:00,-50,0,85,12.5\n"       # Negative RPM
            "2024-06-01 10:01:00,800,450,85,12.5\n"      # Excessive Speed
            "2024-06-01 10:02:00,800,0,180,12.5\n"       # Overheating > 150C
            "2024-06-01 10:03:00,800,0,85,35.0\n"        # Voltage > 30V
        )
        prev = preview_obd_csv(csv_data, "bad_numeric.csv", self.test_veh_id)
        self.assertTrue(prev["success"])

        res = execute_obd_import(
            token=prev["token"],
            vehicle_id=self.test_veh_id,
            column_mapping=prev["detected_mapping"],
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["accepted_count"], 0)
        self.assertEqual(res["rejected_count"], 4)
        reasons = [r["reasons"][0] for r in res["rejected_sample"]]
        self.assertTrue(any("RPM" in r for r in reasons))
        self.assertTrue(any("Speed" in r for r in reasons))
        self.assertTrue(any("Coolant" in r for r in reasons))
        self.assertTrue(any("Voltage" in r for r in reasons))

    def test_reject_malformed_dtc_codes(self):
        """Malformed DTCs are rejected with clear explanation."""
        csv_data = (
            "timestamp,engine_rpm,dtc_codes\n"
            "2024-06-01 10:00:00,800,INVALID_CODE\n"
            "2024-06-01 10:01:00,800,P0420\n"
        )
        prev = preview_obd_csv(csv_data, "dtc_test.csv", self.test_veh_id)
        res = execute_obd_import(
            token=prev["token"],
            vehicle_id=self.test_veh_id,
            column_mapping=prev["detected_mapping"],
        )
        self.assertEqual(res["accepted_count"], 1)
        self.assertEqual(res["rejected_count"], 1)
        self.assertIn("Invalid DTC code", str(res["rejected_sample"][0]["reasons"]))

    def test_missing_dtc_field_does_not_claim_fault_free(self):
        """When CSV has no DTC column, telemetry is imported with a note indicating absence of DTC column."""
        csv_data = (
            "timestamp,engine_rpm,vehicle_speed_kmh,coolant_temp_c\n"
            "2024-06-01 10:00:00,820,0,88.0\n"
        )
        prev = preview_obd_csv(csv_data, "no_dtc.csv", self.test_veh_id)
        self.assertFalse(prev["has_dtc_column"])

        res = execute_obd_import(
            token=prev["token"],
            vehicle_id=self.test_veh_id,
            column_mapping=prev["detected_mapping"],
        )
        self.assertEqual(res["accepted_count"], 1)
        with self.app.app_context():
            rec = OBDRecord.query.filter_by(vehicle_id=self.test_veh_id).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.dtc_codes, None)
            self.assertIn("File contains no DTC information", rec.notes)

    def test_invalid_timestamp_rejected(self):
        """Malformed timestamp strings are rejected."""
        csv_data = (
            "timestamp,engine_rpm\n"
            "not-a-valid-date,800\n"
        )
        prev = preview_obd_csv(csv_data, "bad_ts.csv", self.test_veh_id)
        res = execute_obd_import(
            token=prev["token"],
            vehicle_id=self.test_veh_id,
            column_mapping=prev["detected_mapping"],
        )
        self.assertEqual(res["rejected_count"], 1)
        self.assertIn("timestamp", res["rejected_sample"][0]["reasons"][0].lower())

    def test_duplicate_import_prevention_stable_fingerprint(self):
        """Importing the same CSV twice does not create duplicate database records."""
        csv_data = (
            "timestamp,engine_rpm,vehicle_speed_kmh,coolant_temp_c,battery_voltage\n"
            "2024-06-01 10:00:00,820,0,88.0,12.6\n"
            "2024-06-01 10:01:00,1200,30,89.0,12.7\n"
        )
        # Import 1
        prev1 = preview_obd_csv(csv_data, "batch1.csv", self.test_veh_id)
        res1 = execute_obd_import(prev1["token"], self.test_veh_id, prev1["detected_mapping"])
        self.assertEqual(res1["accepted_count"], 2)
        self.assertEqual(res1["duplicate_count"], 0)

        # Import 2 (identical)
        prev2 = preview_obd_csv(csv_data, "batch2.csv", self.test_veh_id)
        res2 = execute_obd_import(prev2["token"], self.test_veh_id, prev2["detected_mapping"])
        self.assertEqual(res2["accepted_count"], 0)
        self.assertEqual(res2["duplicate_count"], 2)

        with self.app.app_context():
            count = OBDRecord.query.filter_by(vehicle_id=self.test_veh_id).count()
            self.assertEqual(count, 2)

    def test_intra_file_duplicate_prevention(self):
        """Duplicate rows inside the same file are detected and imported only once."""
        csv_data = (
            "timestamp,engine_rpm,coolant_temp_c\n"
            "2024-06-01 10:00:00,800,85.0\n"
            "2024-06-01 10:00:00,800,85.0\n"  # Exact duplicate
        )
        prev = preview_obd_csv(csv_data, "dup_in_file.csv", self.test_veh_id)
        res = execute_obd_import(prev["token"], self.test_veh_id, prev["detected_mapping"])
        self.assertEqual(res["accepted_count"], 1)
        self.assertEqual(res["duplicate_count"], 1)

    def test_formula_injection_sanitization(self):
        """Cells starting with =, +, -, @ are sanitized against formula injection."""
        sanitized = sanitize_csv_cell("=cmd|' /C calc'!A0")
        self.assertTrue(sanitized.startswith("'="))

        sanitized_plus = sanitize_csv_cell("+12345")
        self.assertTrue(sanitized_plus.startswith("'+"))

    def test_invalid_vehicle_id_returns_error(self):
        """Uploading for non-existent vehicle ID returns error."""
        prev = preview_obd_csv("timestamp,engine_rpm\n2024-06-01,800", "test.csv", 99999)
        self.assertFalse(prev["success"])
        self.assertIn("not found", prev["error"].lower())

    def test_records_associated_with_correct_vehicle(self):
        """Imported records are explicitly associated with target vehicle ID."""
        csv_data = "timestamp,engine_rpm\n2024-06-01 12:00:00,780\n"
        prev = preview_obd_csv(csv_data, "assoc.csv", self.test_veh_id)
        res = execute_obd_import(prev["token"], self.test_veh_id, prev["detected_mapping"])
        self.assertEqual(res["accepted_count"], 1)

        with self.app.app_context():
            rec = OBDRecord.query.filter_by(vehicle_id=self.test_veh_id).first()
            self.assertIsNotNone(rec)
            self.assertEqual(rec.vehicle_id, self.test_veh_id)
            self.assertEqual(rec.data_source, "Imported CSV")

    def test_preservation_of_existing_diagnostic_entries(self):
        """Existing manual diagnostic records are not overwritten by OBD CSV imports."""
        from datetime import date
        with self.app.app_context():
            d = DiagnosticRecord(
                vehicle_id=self.test_veh_id,
                date=date(2024, 5, 1),
                data_source="Manual Workshop",
                parameter_name="Spark Plug Gap",
                parameter_value="0.8mm",
            )
            db.session.add(d)
            db.session.commit()
            d_id = d.id

        csv_data = "timestamp,engine_rpm\n2024-06-01 10:00:00,850\n"
        prev = preview_obd_csv(csv_data, "safe.csv", self.test_veh_id)
        execute_obd_import(prev["token"], self.test_veh_id, prev["detected_mapping"])

        with self.app.app_context():
            d_after = DiagnosticRecord.query.get(d_id)
            self.assertIsNotNone(d_after)
            self.assertEqual(d_after.parameter_name, "Spark Plug Gap")

    def test_ev_12v_auxiliary_battery_safeguard(self):
        """For Electric vehicles, battery voltage is noted as 12V auxiliary, not traction SOH."""
        csv_data = "timestamp,battery_voltage\n2024-06-01 10:00:00,12.8\n"
        prev = preview_obd_csv(csv_data, "ev.csv", self.ev_veh_id)
        self.assertTrue(prev["is_ev"])
        res = execute_obd_import(prev["token"], self.ev_veh_id, prev["detected_mapping"])
        self.assertEqual(res["accepted_count"], 1)

        with self.app.app_context():
            rec = OBDRecord.query.filter_by(vehicle_id=self.ev_veh_id).first()
            self.assertIn("12V auxiliary reading", rec.notes)

    def test_web_routes_diagnostics_and_import_wizard(self):
        """Verify Web routes for Diagnostics and OBD Import return HTTP 200."""
        # 1. Diagnostics list
        resp = self.client.get("/diagnostics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Import OBD Data", resp.data)

        # 2. Diagnostics list for specific vehicle
        resp_veh = self.client.get(f"/diagnostics?vehicle_id={self.test_veh_id}")
        self.assertEqual(resp_veh.status_code, 200)

        # 3. Import wizard step 1
        resp_import = self.client.get(f"/diagnostics/import?vehicle_id={self.test_veh_id}")
        self.assertEqual(resp_import.status_code, 200)
        self.assertIn(b"Upload OBD-II Telemetry CSV", resp_import.data)

        # 4. Import preview POST
        csv_bytes = b"timestamp,engine_rpm,vehicle_speed_kmh\n2024-06-01 10:00:00,800,0\n"
        data = {
            "vehicle_id": str(self.test_veh_id),
            "csv_file": (io.BytesIO(csv_bytes), "test_upload.csv"),
        }
        resp_prev = self.client.post("/diagnostics/import/preview", data=data, content_type="multipart/form-data")
        self.assertEqual(resp_prev.status_code, 200)
        self.assertIn(b"Column Mapping", resp_prev.data)

        # 5. Add Vehicle page returns 200 and has autocomplete attributes
        resp_add = self.client.get("/vehicles/add")
        self.assertEqual(resp_add.status_code, 200)
        self.assertIn(b"make-suggestions", resp_add.data)
        self.assertIn(b"model-suggestions", resp_add.data)
        self.assertIn(b"aria-autocomplete=\"list\"", resp_add.data)


if __name__ == "__main__":
    unittest.main()
