# CAR OS — Vehicle Autocomplete and OBD-II File Import Report

**Project:** `D:\caros`  
**Date:** October 28, 2026  
**Status:** Implemented, Tested, and Verified  
**Test Suite:** 133 / 133 Tests Passing (`OK`)

---

## 1. Executive Summary

This engineering report documents the architecture, implementation, security safeguards, validation semantics, and verification results for two major capabilities added to CAR OS:
1. **Indian Vehicle Make/Model Autocomplete** in the Add Vehicle form (`/vehicles/add`).
2. **OBD-II CSV File Import & Diagnostics Pipeline** in the Diagnostics module (`/diagnostics` and `/diagnostics/import`).

All changes were implemented to preserve existing application architecture, database records, and routes without requiring destructive schema migrations or retraining machine learning models.

---

## 2. Feature 1: Vehicle Make/Model Autocomplete

### 2.1 User Experience & Interaction Design
- **Accessible Autocomplete Combobox:** Built directly into `templates/add_vehicle.html` following WAI-ARIA combobox guidelines with `role="combobox"`, `role="listbox"`, `role="option"`, and `aria-expanded` attributes.
- **Debounced Asynchronous Search:** Keystrokes query the local catalogue endpoint (`/api/vehicles/catalogue?q=...`) using a 200ms debounce timer, preventing UI lag and client saturation.
- **Keyboard Navigation:** Full arrow key support (`ArrowDown`, `ArrowUp`), selection confirmation via `Enter` or `Tab`, and menu dismissal via `Escape` or clicking outside.
- **Partial & Case-Insensitive Matching:** Matches vehicle makes, models, and compound multi-word queries (e.g., `"Maruti"`, `"Swift"`, `"Tata Nexon"`, `"XUV 700"`, `"Grand Vitara"`).
- **Targeted Field Population:** Selecting a suggestion populates **only** the `make` and `model` fields. It strictly preserves user-entered registration numbers, odometers, purchase years, purchase prices, fuel types, or notes.
- **Unblocked Manual Entry:** If a user types a bespoke or custom vehicle not present in the suggestion list, form submission proceeds smoothly without validation blocks.
- **Anti-Pollution Principle:** Does not auto-populate speculative specifications (e.g., battery kWh, engine displacement, transmission) unless explicitly part of the verified catalog.

### 2.2 Data Source & Catalogue Service
- **Primary Source:** Inspects and parses `dataset/CAR DETAILS FROM CAR DEKHO.csv`.
- **Intelligent Parsing Method:** The `name` column in CarDekho contains messy trim descriptions (e.g., `"Maruti Swift Dzire VDI"`, `"Hyundai Grand i10 Magna AT"`, `"Mahindra Scorpio S10"`). `VehicleCatalogueService` normalizes these into clean (Make, Model) pairs by identifying manufacturer prefixes and standardizing multi-word brand names (`Maruti` $\rightarrow$ `Maruti Suzuki`, `Land Rover`, `Mercedes-Benz`).
- **Comprehensive Modern Indian Catalogue Fallback:** Includes a curated catalog of contemporary Indian market vehicles across ICE, Hybrid, and EV segments:
  - *Maruti Suzuki:* Alto, Swift, Dzire, Baleno, Brezza, Ertiga, Grand Vitara, Fronx, Jimny.
  - *Tata Motors:* Tiago, Tigor, Altroz, Punch, Nexon, Harrier, Safari, Nexon EV, Punch EV, Tiago EV.
  - *Mahindra:* Thar, Scorpio-N, Scorpio Classic, XUV700, XUV300, XUV400 EV, Bolero.
  - *Hyundai:* i20, Grand i10 Nios, Aura, Venue, Creta, Alcazar, Verna, Tucson, Ioniq 5.
  - *Kia:* Seltos, Sonet, Carens, EV6.
  - *Toyota:* Glanza, Urban Cruiser Taisor, Urban Cruiser Hyryder, Innova Crysta, Innova Hycross, Fortuner, Camry, Hilux, Etios.
  - *Honda:* City, Amaze, Elevate.
  - *MG:* Hector, Astor, ZS EV, Comet EV, Gloster.
  - *Volkswagen & Skoda:* Virtus, Taigun, Slavia, Kushaq, Kodiaq.
  - *Renault:* Kwid, Triber, Kiger.
- **Efficiency & In-Memory Caching:** The dataset is parsed and deduplicated once upon service initialization and cached in-memory. Zero external network requests are made. If the CSV file is missing or unreadable, the system automatically falls back to the static curated list without interruption.

---

## 3. Feature 2: OBD-II Data File Upload & Processing

### 3.1 Supported File Formats & Column Aliases
The parser accommodates both standard commercial OBD loggers (e.g., Torque Pro, OBD Fusion, Car Scanner ELM) and academic/research datasets.

#### Standard OBD-II Parameter Mappings
| Target Parameter | Units / Format | Recognized Aliases (Case-Insensitive) |
|---|---|---|
| `timestamp` | ISO-8601, Unix epoch, standard datetime | `time`, `timestamp`, `datetime`, `date_time`, `date`, `recorded_at` |
| `engine_rpm` | RPM ($0 - 16,000$) | `engine_rpm`, `rpm`, `engine speed`, `eng_rpm`, `engine_rpm ()` |
| `vehicle_speed_kmh` | km/h ($0 - 350$) | `vehicle_speed`, `speed`, `veh_speed`, `spd_kmh`, `vehicle_speed_kmh`, `vehicle_speed ()` |
| `coolant_temp_c` | °C ($-40 - 215$) | `coolant_temp`, `coolant_temperature`, `coolant`, `ect`, `temp_c`, `coolant_temperature ()` |
| `engine_load_pct` | % ($0 - 100$) | `engine_load`, `calc_engine_load`, `load`, `eng_load`, `absolute_load` |
| `throttle_pos_pct` | % ($0 - 100$) | `throttle_pos`, `throttle_position`, `throttle`, `tps`, `relative_throttle_position` |
| `battery_voltage` | Volts ($0 - 48$) | `control_module_voltage`, `battery_voltage`, `voltage`, `ecu_voltage`, `vbat`, `control_module_voltage ()` |
| `fuel_system_status` | String enum | `fuel_system_status`, `fuel_status`, `fuel_system`, `fuel_sys_1` |
| `dtc_codes` | OBD-II DTC format (comma/space-separated) | `dtc_codes`, `dtcs`, `trouble_codes`, `diagnostic_trouble_codes`, `fault_codes` |

#### Toyota Etios Research Dataset Support
The service natively parses research logs such as `dataset/drive1.csv`, automatically handling:
- `ENGINE_RPM ()`
- `VEHICLE_SPEED ()`
- `COOLANT_TEMPERATURE ()`
- `CONTROL_MODULE_VOLTAGE ()`
- `TIME_SINCE_TROUBLE_CODES_CLEARED ()`
- `TIME_RUN_WITH_MIL_ON ()`
- `DISTANCE_TRAVELED_WITH_MIL_ON ()`

### 3.2 Critical Trailing-Comma & Column Shift Resolution
- **The Issue:** Research files generated by certain logging hardware append an empty trailing comma at the end of each row (27 header columns vs 28 record values per row). Standard parsers (e.g. basic Pandas or naive CSV splitters) mistakenly treat column 0 as an index row, shifting all 27 sensor columns by one position (e.g. putting RPM into Timestamp, Speed into RPM, etc.).
- **The Solution:** `safe_read_csv()` in `services/obd_import_service.py` detects when row token counts exceed header token counts by 1 with an empty trailing string. It safely discards the trailing empty token without altering column alignment. Furthermore, it strictly rejects treating data columns as index columns.
- **Timer/Counter Filtering:** Columns like `TIME_SINCE_TROUBLE_CODES_CLEARED ()` contain the string `"CODES"`. The alias detector contains explicit exclusion rules for tokens containing `time`, `distance`, `warm_up`, `since`, and `cleared`, preventing timer metrics from being incorrectly mapped to DTC fault codes.

### 3.3 Data Validation & Cleaning Pipeline
1. **Timestamp Normalization:** Supports ISO formats (`YYYY-MM-DDTHH:MM:SS`), human formats (`YYYY-MM-DD HH:MM:SS`), Unix timestamps (seconds and milliseconds), and falls back to auto-sequenced row timestamps when unprovided.
2. **Physical Boundary Checks:**
   - RPM: Valid between $0$ and $16,000$ RPM.
   - Speed: Valid between $0$ and $350$ km/h.
   - Coolant Temp: Valid between $-40$°C and $215$°C.
   - Engine Load & Throttle Position: Clamped between $0\%$ and $100\%$.
   - Battery/ECU Voltage: Valid between $0$V and $48$V.
3. **DTC Format Validation:** Validates DTC syntax according to standard SAE/ISO nomenclature regex: `^[PBUC][0-3][0-9A-F]{3}$`. Unstandardized or conversational strings are rejected or sanitized.
4. **Stable SHA-256 Fingerprint Deduplication:**
   - Generates a deterministic SHA-256 hash using: `vehicle_id`, canonical ISO `timestamp`, normalized `engine_rpm`, `vehicle_speed_kmh`, `coolant_temp_c`, `engine_load_pct`, `throttle_pos_pct`, `battery_voltage`, and sorted `dtc_codes`.
   - Prevents both intra-file duplicate rows and re-upload duplicates against existing database records.
   - Preserves manual diagnostic entries created through the UI.

### 3.4 Domain Disclaimers & Transparency
- **Absence of DTC $\neq$ Proof of Health:** When a CSV file contains no DTC column or has empty DTC entries, the system records `dtc_codes: None` and does **not** generate unwarranted "fault-free" certificates. Mechanical defects (e.g., suspension, brakes, fluid leaks, clutch wear) do not trigger OBD DTCs.
- **EV Auxiliary Battery Notice:** For electric and hybrid vehicles, the 12V Control Module Voltage is an auxiliary control bus metric. The system clearly indicates that 12V auxiliary voltage is **never** an indicator of traction high-voltage battery State of Health (SoH).

### 3.5 Security Controls
- **File Type & Size Restrictions:** Uploads are strictly restricted to `.csv` files. Configured with a default file-size limit of 10 MB and a max row limit of 10,000 rows.
- **CSV Formula Injection Defense:** Malicious cells beginning with spreadsheet formula triggers (`=`, `+`, `-`, `@`, `\t`, `\r`) are automatically escaped with leading single quotes before processing or rendering.
- **Path Traversal & Execution Prevention:** Files are parsed as in-memory streams (`io.StringIO` / `BytesIO`). No temporary files are executed or left behind on the host filesystem.
- **Vehicle Authorization:** Requires a valid, active vehicle ID. Invalid vehicle IDs abort immediately with clean 400/404 messages without exposing SQL or stack traces.
- **HTML Escaping:** All imported text, notes, and error reports are HTML-escaped before display.

### 3.6 Step-by-Step UI Flow
- **Step 1: Upload:** Select vehicle, drag & drop or browse `.csv` file.
- **Step 2: Preview & Map:** Displays detected column mappings with interactive dropdown overrides and a live table preview of the first 5 rows.
- **Step 3: Execution & Results:** Displays Accepted, Rejected, and Duplicate row counts. If any rows were rejected, an interactive error summary is shown along with a one-click **"Download Rejection Report (CSV)"** button.
- **Diagnostics Integration:** All accepted records are tagged with `data_source="Imported CSV"` and displayed in the vehicle's diagnostic history table on `/diagnostics`.

---

## 4. Summary of Code & Template Changes

| File | Action | Purpose |
|---|---|---|
| `services/vehicle_catalogue_service.py` | **Created** | Parses CarDekho CSV, provides Indian make/model catalog with debounced matching. |
| `services/obd_import_service.py` | **Created** | Handles safe CSV reading, trailing-comma correction, column alias mapping, validation, fingerprinting. |
| `templates/import_obd.html` | **Created** | Step-by-step upload, preview/mapping, and results wizard matching CAR OS dark theme. |
| `templates/add_vehicle.html` | **Updated** | Added ARIA autocomplete comboboxes for `#make` and `#model` with keyboard navigation. |
| `templates/diagnostics.html` | **Updated** | Added "Import OBD Data" navigation button and OBD-II Telemetry Records table. |
| `routes/vehicle_routes.py` | **Updated** | Added `/api/vehicles/catalogue` autocomplete search endpoint. |
| `routes/analytics_routes.py` | **Updated** | Added `/diagnostics/import`, `/diagnostics/import/preview`, `/diagnostics/import/execute`, `/diagnostics/import/errors/<token>`, and updated `/diagnostics`. |
| `static/css/style.css` | **Updated** | Added styles for autocomplete dropdowns, keyboard focus states, badges, and wizard components. |
| `tests/test_autocomplete_and_obd_import.py` | **Created** | 22 comprehensive unit and integration tests covering both new features. |

---

## 5. Automated Test Results

The full test suite was executed using the project Python virtual environment:
```powershell
.\venv\Scripts\python.exe -m unittest discover tests
```

### Test Suite Execution Output
```text
Ran 133 tests in 10.361s

OK
```

### Coverage of New Test Cases (`test_autocomplete_and_obd_import.py`)
1. `test_make_model_partial_matching`: Confirms partial and space-tolerant search (e.g., `"Maruti"`, `"Tata Nexon"`).
2. `test_case_insensitive_and_spaces`: Confirms case insensitivity (`"hYUnDai"`, `"xuv 700"`).
3. `test_unknown_models_allowed`: Confirms manual entry of unlisted custom vehicles is not blocked.
4. `test_catalogue_service_fallback`: Confirms graceful fallback to curated catalogue if CarDekho CSV is missing.
5. `test_standard_csv_parsing`: Confirms parsing and mapping of standard OBD-II CSV columns.
6. `test_trailing_comma_handling`: Confirms trailing comma does not shift columns or corrupt sensor values.
7. `test_toyota_etios_research_headers`: Confirms automatic mapping for all Toyota Etios research headers.
8. `test_column_alias_detection_excludes_timers`: Confirms DTC clearance timers are not misclassified as fault codes.
9. `test_invalid_numeric_values_rejected`: Confirms rejection of impossible values (e.g. RPM $> 16,000$, Voltage $> 48$V).
10. `test_malformed_dtc_rejected`: Confirms invalid DTC formats (e.g. `"INVALID_CODE"`) are caught.
11. `test_invalid_timestamps_fallback`: Confirms graceful handling of invalid timestamp entries.
12. `test_missing_dtc_field_does_not_claim_fault_free`: Confirms omission of DTC column does not fabricate a clean bill of health.
13. `test_duplicate_imports_prevention`: Confirms duplicate rows (intra-file and cross-import) are detected and skipped.
14. `test_file_size_and_row_count_limits`: Confirms enforcement of 10 MB and 10,000 row upload caps.
15. `test_formula_injection_sanitization`: Confirms spreadsheet formula injection strings (`=cmd`, `@SUM`) are sanitized.
16. `test_invalid_vehicle_id_handled`: Confirms non-existent vehicle ID returns a clean error without crashing.
17. `test_records_associated_with_selected_vehicle`: Confirms imported records are bound strictly to the selected vehicle.
18. `test_preserves_existing_diagnostic_records`: Confirms existing manual entries remain untouched.
19. `test_api_catalogue_endpoint`: Confirms HTTP 200 and JSON response from `/api/vehicles/catalogue`.
20. `test_import_routes_render_200`: Confirms HTTP 200 for `/diagnostics/import` and `/diagnostics`.
21. `test_full_import_workflow`: Confirms preview $\rightarrow$ execute workflow end-to-end.
22. `test_download_error_report`: Confirms generation and retrieval of CSV rejection error reports.

---

## 6. End-to-End Route Verification

The application routes were verified directly against the running application instance:
- `GET /vehicles/add` $\rightarrow$ **HTTP 200 OK**
- `GET /diagnostics` $\rightarrow$ **HTTP 200 OK**
- `GET /diagnostics/import` $\rightarrow$ **HTTP 200 OK**
- `GET /api/vehicles/catalogue?q=maruti` $\rightarrow$ **HTTP 200 OK**

---

## 7. Remaining Limitations & Future Roadmap

1. **High-Frequency Sensor Downsampling:**
   - *Current Behavior:* Loggers recording at 10 Hz generate 36,000 rows per hour. Imports are capped at 10,000 rows per batch.
   - *Recommendation:* Introduce an optional downsampling toggle (e.g., aggregate every 1s or 5s) during the Preview step for multi-hour logs.
2. **Real-Time ELM327 Bluetooth/WiFi Adapter Streaming:**
   - *Current Behavior:* Data ingestion is file-based via CSV upload.
   - *Recommendation:* Add WebSockets or Web Bluetooth API support for live ELM327 telemetry capture directly inside CAR OS.
3. **Traction Battery Telemetry for EVs:**
   - *Current Behavior:* Standard OBD PID 0x42 reports 12V auxiliary bus voltage; EV traction battery state of charge (SoC) and cell delta voltages require OEM-specific UDS commands.
   - *Recommendation:* Incorporate manufacturer-specific CAN PID databases (e.g., Tata Ziptron, Hyundai E-GMP) to extract traction pack cell balance and SoH.
