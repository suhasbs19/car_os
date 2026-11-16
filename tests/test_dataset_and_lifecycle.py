"""
CAR OS - Test Suite for Dataset Ingestion, EV Telemetry, and End-to-End Lifecycle
Covers:
- Dataset inspection, sheet parsing, and data profile verification
- Safe vehicle mapping and candidate suggestions
- Dry-run validation simulation (zero database side-effects)
- Live service history ingestion and field preservation
- Import idempotency (duplicate prevention on repeated runs)
- Total ownership cost deduplication via linked_maintenance_id
- Rejection of invalid records (dates, negative costs, unmapped vehicles)
- Electric Vehicle (EV) auxiliary battery vs High-Voltage SOH safeguards
- Complete End-to-End Vehicle Lifecycle workflow
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from datetime import date
from app import create_app
from models import db, Vehicle, MaintenanceRecord, FuelRecord, ExpenseRecord, OBDRecord
from services.dataset_service import (
    inspect_dataset_workbook,
    suggest_candidate_mappings,
    preview_or_import_service_history,
)
from services.obd_service import analyze_obd_record
from services.decision_service import generate_decision
from services.fuel_service import calculate_fuel_efficiency, aggregate_fuel_records


class TestDatasetAndLifecycle(unittest.TestCase):

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.workbook_path = os.path.join(self.app.root_path, "CAR_OS_Dataset_Service_History_VISIBLE.xlsx")
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    # ── 1. Dataset Inspection & Profiling ───────────────────────────────────

    def test_dataset_inspection_structure(self):
        """Verifies that the reference Excel workbook contains all 4 sheets and valid metadata."""
        info = inspect_dataset_workbook(self.workbook_path)
        self.assertTrue(info["valid"])
        self.assertIn("Service_History", info["sheet_names"])
        self.assertIn("Vehicle_Profile_Demo", info["sheet_names"])
        self.assertIn("OBD_Data_Catalog", info["sheet_names"])
        self.assertIn("Vehicle_Master", info["sheet_names"])

        sh_summary = info["service_history_summary"]
        self.assertEqual(sh_summary["total_records"], 32)
        self.assertEqual(len(sh_summary["vehicle_ids"]), 16)
        self.assertEqual(sh_summary["service_types"].get("Periodic service"), 16)
        self.assertEqual(sh_summary["service_types"].get("Repair"), 16)

    def test_candidate_mapping_suggestions(self):
        """Verifies candidate mapping suggestions against registered vehicles."""
        with self.app.app_context():
            v = Vehicle(
                make="Hyundai",
                model="Creta",
                registration_number="MH12AB1234",
                manufacturing_year=2022,
                odometer_km=42000,
                fuel_type="Petrol",
            )
            db.session.add(v)
            db.session.commit()

            suggestions = suggest_candidate_mappings(self.workbook_path)
            self.assertGreater(len(suggestions), 0)

            # V002 is Hyundai Creta in Vehicle_Profile_Demo
            v002_cand = next((s for s in suggestions if s["dataset_vehicle_id"] == "V002"), None)
            self.assertIsNotNone(v002_cand)
            self.assertEqual(v002_cand["candidate_vehicle_id"], v.id)
            self.assertIn("High Confidence", v002_cand["match_confidence"])

    # ── 2. Dry-Run Simulation & Live Ingestion ──────────────────────────────

    def test_dry_run_leaves_database_untouched(self):
        """Dry-run simulation must validate rows without inserting records into the DB."""
        with self.app.app_context():
            v = Vehicle(
                make="Maruti Suzuki",
                model="Swift",
                registration_number="DL01XY9876",
                manufacturing_year=2022,
                odometer_km=35000,
                fuel_type="Petrol",
            )
            db.session.add(v)
            db.session.commit()
            vid = v.id

            result = preview_or_import_service_history(
                self.workbook_path,
                vehicle_mapping={"V001": vid},
                dry_run=True,
                create_expense_records=True,
            )
            self.assertTrue(result["success"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["inserted"], 2)  # 2 records for V001
            self.assertEqual(result["skipped"], 30)  # 30 records for V002-V016 unmapped

            # Verify DB was NOT modified
            self.assertEqual(MaintenanceRecord.query.count(), 0)
            self.assertEqual(ExpenseRecord.query.count(), 0)

    def test_live_ingestion_and_field_preservation(self):
        """Live ingestion must store records with source_record_id, parts, labour, and workshop."""
        with self.app.app_context():
            v = Vehicle(
                make="Maruti Suzuki",
                model="Swift",
                registration_number="DL01XY9876",
                manufacturing_year=2022,
                odometer_km=35000,
                fuel_type="Petrol",
            )
            db.session.add(v)
            db.session.commit()
            vid = v.id

            result = preview_or_import_service_history(
                self.workbook_path,
                vehicle_mapping={"V001": vid},
                dry_run=False,
                create_expense_records=True,
            )
            self.assertTrue(result["success"])
            self.assertFalse(result["dry_run"])
            self.assertEqual(result["inserted"], 2)

            records = MaintenanceRecord.query.filter_by(vehicle_id=vid).order_by(MaintenanceRecord.service_date).all()
            self.assertEqual(len(records), 2)
            for r in records:
                self.assertTrue(r.source_record_id.startswith("SH"))
                self.assertEqual(r.evidence_status, "Synthetic demo record")
                self.assertEqual(r.workshop, "Demo workshop")
                self.assertIsNotNone(r.cost)

    def test_idempotent_ingestion_prevents_duplicate_records(self):
        """Repeating ingestion with the same dataset records must detect duplicates and insert 0."""
        with self.app.app_context():
            v = Vehicle(
                make="Maruti Suzuki",
                model="Swift",
                registration_number="DL01XY9876",
                manufacturing_year=2022,
                odometer_km=35000,
                fuel_type="Petrol",
            )
            db.session.add(v)
            db.session.commit()
            vid = v.id

            # First run: inserts 2
            r1 = preview_or_import_service_history(
                self.workbook_path,
                vehicle_mapping={"V001": vid},
                dry_run=False,
                create_expense_records=True,
            )
            self.assertEqual(r1["inserted"], 2)
            self.assertEqual(r1["duplicates"], 0)
            count_after_first = MaintenanceRecord.query.count()

            # Second run: 0 inserted, 2 duplicates detected
            r2 = preview_or_import_service_history(
                self.workbook_path,
                vehicle_mapping={"V001": vid},
                dry_run=False,
                create_expense_records=True,
            )
            self.assertEqual(r2["inserted"], 0)
            self.assertEqual(r2["duplicates"], 2)
            self.assertEqual(MaintenanceRecord.query.count(), count_after_first)

    def test_expense_deduplication_via_linked_maintenance_id(self):
        """Expense records created from maintenance must be linked to prevent double counting in TCO."""
        with self.app.app_context():
            v = Vehicle(
                make="Hyundai",
                model="Creta",
                registration_number="MH12AB1234",
                manufacturing_year=2022,
                odometer_km=42000,
                fuel_type="Petrol",
            )
            db.session.add(v)
            db.session.commit()

            result = preview_or_import_service_history(
                self.workbook_path,
                vehicle_mapping={"V002": v.id},
                dry_run=False,
                create_expense_records=True,
            )
            self.assertEqual(result["inserted"], 2)

            maint_records = MaintenanceRecord.query.filter_by(vehicle_id=v.id).all()
            for m in maint_records:
                self.assertIsNotNone(m.expense_id)
                linked_exp = ExpenseRecord.query.get(m.expense_id)
                self.assertIsNotNone(linked_exp)
                self.assertEqual(linked_exp.linked_maintenance_id, m.id)
                self.assertEqual(linked_exp.amount, m.cost)

    def test_tco_deduplication_audit_no_double_counting(self):
        """Audit regression test: confirms Total Cost of Ownership (TCO) never double-counts auto-linked maintenance."""
        with self.app.app_context():
            v = Vehicle(
                make="Hyundai",
                model="Creta",
                registration_number="MH12TCO001",
                manufacturing_year=2023,
                odometer_km=15000,
                fuel_type="Petrol",
            )
            db.session.add(v)
            db.session.commit()
            vid = v.id

            # Ingest 2 service records with auto-created expenses
            res = preview_or_import_service_history(
                self.workbook_path,
                vehicle_mapping={"V002": vid},
                dry_run=False,
                create_expense_records=True,
            )
            self.assertEqual(res["inserted"], 2)

            # Add a standalone operational expense (Insurance)
            ins = ExpenseRecord(
                vehicle_id=vid,
                date=date.today(),
                category="Insurance",
                amount=15000.0,
                description="Comprehensive Policy",
                linked_maintenance_id=None,
            )
            db.session.add(ins)

            # Add a fuel record
            fuel = FuelRecord(
                vehicle_id=vid,
                date=date.today(),
                distance_km=450.0,
                quantity=30.0,
                cost=3150.0,
                fuel_type="Petrol",
            )
            db.session.add(fuel)
            db.session.commit()

        # Query /api/reports and verify TCO deduplication
        resp = self.client.get("/api/reports")
        self.assertEqual(resp.status_code, 200)
        v_rep = next(r for r in resp.json if r["vehicle_id"] == vid)

        # Ingested maintenance total: SH003 (5100) + SH004 (2800) = 7900
        self.assertEqual(v_rep["total_maint_cost"], 7900.0)
        self.assertEqual(v_rep["total_fuel_cost"], 3150.0)

        # Standalone expenses must strictly exclude the 7900 auto-linked maintenance
        self.assertEqual(v_rep["total_expenses"], 15000.0)
        self.assertEqual(v_rep["gross_expenses"], 22900.0)  # 15000 + 7900
        self.assertEqual(v_rep["linked_maint_expenses"], 7900.0)

        # True TCO must be exactly 7900 + 3150 + 15000 = 26050 (NOT 33950)
        expected_tco = 7900.0 + 3150.0 + 15000.0
        self.assertEqual(v_rep["total_tco"], expected_tco)
        self.assertNotEqual(v_rep["total_tco"], v_rep["total_maint_cost"] + v_rep["gross_expenses"] + v_rep["total_fuel_cost"])

        # Cost per km must reflect running costs (maint + fuel) / distance: (7900 + 3150) / 450 = 24.56
        self.assertEqual(v_rep["cost_per_km"], round((7900.0 + 3150.0) / 450.0, 2))

    def test_web_routes_for_dataset_import(self):
        """Tests the web GET and POST routes for dataset import."""
        with self.app.app_context():
            v = Vehicle(
                make="Tata",
                model="Nexon",
                registration_number="TN01XY1111",
                manufacturing_year=2022,
                odometer_km=25000,
                fuel_type="Petrol",
            )
            db.session.add(v)
            db.session.commit()
            vid = v.id

        # GET import page
        resp_get = self.client.get("/maintenance/import")
        self.assertEqual(resp_get.status_code, 200)
        self.assertIn(b"Dataset Ingestion", resp_get.data)

        # POST with dry_run simulation
        resp_post = self.client.post("/maintenance/import", data={
            "mapping_V003": str(vid),
            "dry_run": "1",
            "create_expense_records": "1",
        }, follow_redirects=True)
        self.assertEqual(resp_post.status_code, 200)
        self.assertIn(b"Dry run complete", resp_post.data)

        # API inspection endpoint
        resp_api = self.client.get("/api/dataset/inspect")
        self.assertEqual(resp_api.status_code, 200)
        data = resp_api.json
        self.assertTrue(data["inspection"]["valid"])

    # ── 3. EV Telemetry Safeguards ──────────────────────────────────────────

    def test_ev_traction_battery_soh_safeguard(self):
        """OBD analysis for Electric Vehicles must explicitly safeguard 12V auxiliary readings."""
        with self.app.app_context():
            ev = Vehicle(
                make="Tata",
                model="Nexon EV",
                registration_number="KA03EV1234",
                manufacturing_year=2023,
                odometer_km=15000,
                fuel_type="Electric",
            )
            db.session.add(ev)
            db.session.commit()

            obd = OBDRecord(
                vehicle_id=ev.id,
                connection_status="Not connected",
                data_source="Manual",
                battery_voltage=12.1,
                engine_rpm=None,
                coolant_temp_c=45.0,
            )
            db.session.add(obd)
            db.session.commit()

            analysis = analyze_obd_record(obd)
            self.assertTrue(analysis["is_ev"])
            adv_types = [a["type"] for a in analysis["advisories"]]
            self.assertIn("EV High-Voltage Traction Battery Safeguard", adv_types)

    # ── 4. End-to-End Complete Vehicle Lifecycle ────────────────────────────

    def test_complete_end_to_end_lifecycle_workflow(self):
        """
        Executes complete user journey:
        1. Register a multi-powertrain vehicle
        2. Ingest service history
        3. Record OBD diagnostic readings
        4. Log fuel/energy fill-ups
        5. Log non-maintenance operational expenses
        6. Validate vehicle health and maintenance reminders
        7. Validate resale valuation
        8. Validate explainable Maintain-Repair-Sell decision
        """
        with self.app.app_context():
            # Step 1: Register vehicle
            resp = self.client.post("/vehicles/add", data={
                "registration_number": "MH 14 AB 9999",
                "make": "Hyundai",
                "model": "Creta",
                "manufacturing_year": str(date.today().year - 3),
                "odometer_km": "32000",
                "fuel_type": "Petrol",
                "service_history": "Full",
                "reported_issues": "0",
                "notes": "End-to-End Test Vehicle",
            }, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)

            v = Vehicle.query.filter_by(registration_number="MH 14 AB 9999").first()
            self.assertIsNotNone(v)
            self.assertGreater(v.health_score, 70.0)

            # Step 2: Ingest service history records
            res_ingest = preview_or_import_service_history(
                self.workbook_path,
                vehicle_mapping={"V002": v.id},  # V002 is Creta
                dry_run=False,
                create_expense_records=True,
            )
            self.assertEqual(res_ingest["inserted"], 2)
            self.assertEqual(v.maintenance_records.count(), 2)

            # Step 3: Record OBD diagnostic data
            obd = OBDRecord(
                vehicle_id=v.id,
                connection_status="Not connected",
                data_source="Manual",
                battery_voltage=12.4,
                engine_rpm=800.0,
                coolant_temp_c=88.0,
                dtc_codes='["P0420"]',
            )
            db.session.add(obd)
            db.session.commit()
            self.assertEqual(len(v.latest_obd.dtc_list), 1)

            # Step 4: Record fuel log
            fuel = FuelRecord(
                vehicle_id=v.id,
                date=date.today(),
                distance_km=450.0,
                quantity=30.0,
                cost=3150.0,
                fuel_type="Petrol",
            )
            db.session.add(fuel)
            db.session.commit()

            eff = calculate_fuel_efficiency(fuel.distance_km, fuel.quantity, fuel.fuel_type)
            self.assertEqual(eff["efficiency"], 15.0)  # 450 / 30 = 15.0 km/L

            # Step 5: Record independent expense (e.g. FASTag Tolls)
            toll = ExpenseRecord(
                vehicle_id=v.id,
                date=date.today(),
                category="Parking & Tolls",
                amount=500.0,
                description="Highway toll charges",
            )
            db.session.add(toll)
            db.session.commit()

            # Step 6: Verify health and decision support
            decision = generate_decision(v, v.maintenance_records, v.expense_records, v.fuel_records)
            self.assertIn(decision["recommendation"], ["Maintain", "Repair", "Sell"])
            self.assertIn(decision["confidence"], ["Low", "Medium", "High"])
            self.assertGreater(len(decision["reasons"]), 0)

            # Step 7: Verify total fleet reports API
            resp_reports = self.client.get("/api/reports")
            self.assertEqual(resp_reports.status_code, 200)
            rep_data = next((r for r in resp_reports.json if r["vehicle_id"] == v.id), None)
            self.assertIsNotNone(rep_data)
            self.assertEqual(rep_data["maint_count"], 2)
            self.assertEqual(rep_data["fuel_records_count"], 1)


if __name__ == "__main__":
    unittest.main()
