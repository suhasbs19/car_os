# CAR OS — Comprehensive Audit Report of Candidate Datasets
**Audit Date:** October 28, 2026  
**Auditor:** Senior Automotive Systems & ML Engineering Audit Team  
**Target Path:** `d:\caros\dataset`  
**Application Scope:** CAR OS (Intelligent Vehicle System and Cost Management Platform)  
**Safety Mandate:** Read-only inspection; zero production modification; zero database modification.

---

## Executive Summary & Final Recommendations

A comprehensive audit was performed across all 44 data files located in `d:\caros\dataset`. Four distinct datasets were identified, parsed, verified for provenance, and evaluated for CAR OS architectural compatibility:

| Dataset | File(s) / Count | Total Size | Provenance & Nature | Recommendation for CAR OS |
| :--- | :--- | :--- | :--- | :--- |
| **1. CarDekho Used Car Dataset** | `CAR DETAILS FROM CAR DEKHO.csv` (1 file) | 346.3 KB (354,635 bytes) | **Empirical Real-world (India)**; 4,340 listings across 29 brands; INR (₹) prices. | **RECOMMENDED FOR PRODUCTION INTEGRATION** (Resale Valuation Model) |
| **2. Vehicle Maintenance Records** | `Vehicle Maintenance- Service Records.csv` (1 file) | 95.4 KB (97,707 bytes) | **Empirical / Benchmark (India)**; 1,139 records; Mumbai & Chennai; INR (₹) costs. | **RECOMMENDED FOR PRODUCTION INTEGRATION** (Service Cost Forecasting & Component Schedules) |
| **3. India EV Range Dataset** | `india_ev_range_dataset.csv` (1 file) | 851.7 KB (872,160 bytes) | **Synthetic / Physics Simulation (India)**; 7,291 rows; Indian EV models & cities. | **USE FOR EXPERIMENTS ONLY** (EV Range & Energy Simulator; not real telemetry) |
| **4. carOBD / Toyota Etios OBD-II** | `drive*.csv`, `idle*.csv`, `live*.csv` (41 files) | 24.3 MB (25,487,249 bytes) | **Empirical Real-world (Brazil)**; 90,676 records; 2014 Toyota Etios 1.5L; 1 Hz. | **USE FOR EXPERIMENTS ONLY** (Live OBD Telemetry Benchmarking; Normal Engine Operation) |

---

## 1. Complete Dataset Inventory

The `dataset` directory contains **44 files** totaling **27,066,381 bytes ($\approx 25.81\text{ MB}$)**. No compressed archives (`.zip`, `.tar.gz`, `.rar`) are present; all files are uncompressed CSV files.

### Inventory Breakdown by Category

```
d:\caros\dataset\
├── CAR DETAILS FROM CAR DEKHO.csv                           [354,635 bytes]  (CarDekho Used Car)
├── Vehicle Maintenance- Service Records.csv                 [ 97,707 bytes]  (Vehicle Maintenance)
├── india_ev_range_dataset.csv                               [872,160 bytes]  (India EV Range)
│
├── Drive Telemetry Group (13 files - 11,818,448 bytes):
│   ├── drive1.csv   [815,569 bytes]   ├── drive6.csv   [1,046,803 bytes]  ├── drive11.csv  [  981,736 bytes]
│   ├── drive2.csv   [699,203 bytes]   ├── drive7.csv   [  167,114 bytes]  ├── drive12.csv  [1,152,757 bytes]
│   ├── drive3.csv   [880,916 bytes]   ├── drive8.csv   [  843,801 bytes]  ├── drive13.csv  [1,229,351 bytes]
│   ├── drive4.csv [1,323,514 bytes]   ├── drive9.csv   [1,006,115 bytes]
│   ├── drive5.csv   [188,801 bytes]   ├── drive10.csv  [1,618,903 bytes]
│
├── Idle Telemetry Group (18 files - 7,495,149 bytes):
│   ├── idle1.csv    [362,122 bytes]   ├── idle8.csv    [  236,637 bytes]  ├── idle16.csv   [  327,746 bytes]
│   ├── idle3.csv    [405,896 bytes]   ├── idle9.csv    [  219,831 bytes]  ├── idle17.csv   [  569,460 bytes]
│   ├── idle4.csv    [402,784 bytes]   ├── idle10.csv   [  438,539 bytes]  ├── idle18.csv   [  632,543 bytes]
│   ├── idle5.csv    [420,810 bytes]   ├── idle11.csv   [  290,875 bytes]  ├── idle19.csv   [  418,381 bytes]
│   ├── idle6.csv    [320,924 bytes]   ├── idle12.csv   [  381,713 bytes]  ├── idle20.csv   [  441,537 bytes]
│   ├── idle7.csv    [576,971 bytes]   ├── idle13.csv   [  378,088 bytes]
│   │                                  ├── idle15.csv   [  359,741 bytes]  (Note: idle2, idle14 missing)
│
└── Live Commute Telemetry Group (10 files - 5,972,709 bytes):
    ├── live1.csv  [1,160,035 bytes]   ├── live5.csv    [  319,010 bytes]  ├── live8.csv    [  314,953 bytes]
    ├── live2.csv  [  850,301 bytes]   ├── live6.csv    [  281,225 bytes]  ├── live9.csv    [  287,865 bytes]
    ├── live3.csv  [  910,591 bytes]   ├── live6 (1).csv[  281,225 bytes]  (Exact byte duplicate of live6.csv)
    ├── live4.csv  [  957,852 bytes]   ├── live7.csv    [  323,048 bytes]
```

---

## 2. Detailed Data Quality & Schema Audit

### Dataset 1: CarDekho Used Car Dataset (`CAR DETAILS FROM CAR DEKHO.csv`)

- **File Path:** `dataset/CAR DETAILS FROM CAR DEKHO.csv`
- **File Size:** 354,635 bytes
- **Rows & Columns:** 4,340 rows $\times$ 8 columns
- **Missing Values:** **0** across all columns.
- **Duplicate Rows:** **763 duplicate rows** (17.58%). These are repeated marketplace listings of common models; deduplication yields 3,577 unique vehicle instances.
- **Market Provenance:** **India (Domestic Used Car Market)**
- **Currency:** **Indian Rupees (INR, ₹)**
- **Distance Unit:** **Kilometres (`km_driven`)**
- **Manufacturers Represented (29 Brands):** Maruti (1,280), Hyundai (821), Honda (252), Tata (186), Mahindra (365), Toyota (206), Ford (238), Chevrolet (188), Renault (146), Volkswagen (107), Skoda (68), Nissan (64), Audi (60), BMW (39), Mercedes-Benz (35), Datsun (37), Fiat (37), etc.
- **Schema & Value Ranges:**
  - `name` (string): e.g., `"Maruti 800 AC"`, `"Hyundai Verna 1.6 SX"`, `"Honda City 1.5 V AT"`.
  - `year` (int64): 1992 to 2020 (Median: 2014, Mean: 2013.09).
  - `selling_price` (int64): ₹20,000 to ₹89,00,000 (Median: **₹3,50,000**; Mean: **₹5,04,127**; 75th percentile: ₹6,00,000).
  - `km_driven` (int64): 1 km to 8,06,599 km (Median: **60,000 km**; Mean: **66,215 km**).
  - `fuel` (string): Diesel (2,153), Petrol (2,123), CNG (40), LPG (23), Electric (1).
  - `seller_type` (string): Individual (3,244), Dealer (994), Trustmark Dealer (102).
  - `transmission` (string): Manual (3,892), Automatic (448).
  - `owner` (string): First Owner (2,832), Second Owner (1,106), Third Owner (304), Fourth & Above Owner (81), Test Drive Car (17).
- **Data Integrity Assessment:** **High**. Clean, empirical marketplace transactions representing Indian automotive depreciation curves.

---

### Dataset 2: Vehicle Maintenance Records (`Vehicle Maintenance- Service Records.csv`)

- **File Path:** `dataset/Vehicle Maintenance- Service Records.csv`
- **File Size:** 97,707 bytes
- **Rows & Columns:** 1,139 rows $\times$ 24 columns
- **Missing Values:** **0** across all columns.
- **Duplicate Rows:** **0** duplicates.
- **Market Provenance:** **India** (Urban Authorized / Independent Service Centers in **Mumbai** and **Chennai**).
- **Currency:** **Indian Rupees (INR, ₹)**
- **Distance Unit:** **Kilometres (`mileage`)**
- **Manufacturers & Models:**
  - **Honda (979 records):** Jazz (342), Amaze (321), City (316).
  - **Toyota (160 records):** Fortuner (160).
- **Engine Types:** Diesel (659), Petrol (480).
- **Make Years:** 2016 (658), 2017 (480), 2018 (1).
- **Mileage Intervals:** 10,000 km periodic service intervals up to 137,822 km (min: 9,021 km; mean: 46,561 km; median: 45,000 km).
- **Cost Distribution:** ₹1,099 to ₹14,000 (Median: **₹5,199**; Mean: **₹5,231**; Standard Deviation: ₹2,191).
- **Component Replacement Flags (0 or 1 binary):**
  - Standard periodic service items: `oil_filter` (100%), `engine_oil` (100%), `washer_plug_drain` (88.1%).
  - Mid-interval wear items: `air_clean_filter` (38.3%), `fuel_filter` (28.7%), `dust_and_pollen_filter` (27.9%), `whell_alignment_and_balancing` (25.9%).
  - Major wear items: `brake_fluid` (15.2%), `transmission_fluid` (14.2%), `brake_pads` (14.1%), `clutch` (13.3%), `spark_plug` (6.3%), `coolant` (5.5%).
- **Data Quality Anomaly:**
  - Column name typo: `whell_alignment_and_balancing` (misspelling of `wheel`).
  - Model pricing paradox: Toyota Fortuner average service cost is recorded at ₹4,596 (lower than Honda Amaze at ₹5,831), likely reflecting fixed periodic labor coupons or capped standard interval packages rather than heavy unscheduled repairs.

---

### Dataset 3: India EV Range Dataset (`india_ev_range_dataset.csv`)

- **File Path:** `dataset/india_ev_range_dataset.csv`
- **File Size:** 872,160 bytes
- **Rows & Columns:** 7,291 rows $\times$ 25 columns
- **Missing Values:** **0** across all columns.
- **Duplicate Rows:** **0** duplicates.
- **Market Provenance:** **India (Domestic EV Market Specifications)**
- **Currency:** **Lakh INR (`price_lakh_INR`)**, ranging from 7.0 Lakh (MG Comet) to 750.0 Lakh (Porsche Taycan / Lotus).
- **Distance Unit:** **Kilometres (`ARAI_certified_range_km`, `real_world_range_km`)**
- **Makes Represented (18 Brands):** Tata (1,435), BYD (709), MG (609), Mahindra (601), BMW (590), Mercedes (486), Hyundai (482), Kia (361), Audi (356), Volvo (355), Citroen (251), Porsche (234), Maruti Suzuki (233), Smart (125), Jaguar (120)...
- **Models Represented (45 Models):** Nexon EV, Tiago EV, Tigor EV, Punch EV, Curvv EV, XUV400, ZS EV, Comet EV, Ioniq 5, EV6, Atto 3, Seal, etc., plus announced concepts (Sierra EV, Harrier EV, XEV 9e).
- **Geographic Profiles:** 12 Indian urban driving contexts ($\approx 600$ rows each): Mumbai, Delhi, Bangalore, Chennai, Kolkata, Pune, Hyderabad, Expressway, Highway_NH, Ghat_Road, Hill_Station, Rural_Road.
- **Critical Quality Finding: Synthetic Physics Simulation:**
  - `energy_consumption_kWh_per_km` is an **exact mathematical formula**: $\frac{\text{battery\_capacity\_kWh}}{\text{real\_world\_range\_km}}$ (absolute mean difference: $0.000025\text{ kWh/km}$).
  - `real_world_range_km` is computed via longitudinal vehicle dynamics simulation (rolling resistance, aerodynamic drag, gradient resistance, motor efficiency, AC power load, passenger mass, and ambient temperature degradation) rather than real on-board BMS telemetry.
  - The ratio of real-world range to ARAI certified range averages **49.05%** (range: 10.0% in extreme ghat/hot/AC scenarios to 95.0% on flat eco cruising).

---

### Dataset 4: carOBD / Toyota Etios OBD-II Telemetry Dataset (`drive*.csv`, `idle*.csv`, `live*.csv`)

- **File Paths:** 41 CSV files (`drive1.csv`–`drive13.csv`, `idle1.csv`–`idle20.csv`, `live1.csv`–`live9.csv`, `live6 (1).csv`)
- **Combined Size:** 25,487,249 bytes ($\approx 24.3\text{ MB}$)
- **Rows & Columns:** **90,676 total records** across 41 files; **27 columns** per file.
- **Original Source & Provenance:**
  - **Source Repository:** `eron93br/carOBD` (GitHub).
  - **Academic Author:** Eronides Barbosa Neto, Federal University of Pernambuco (UFPE), Recife, Pernambuco, **Brazil**.
  - **Vehicle Under Test:** **2014 Toyota Etios Hatchback/Sedan 1.5L Flex-Fuel Petrol (1,496 cc)**.
  - **Hardware Interface:** Carloop CAN-bus/OBD-II microcontroller logging standard OBD-II PIDs at **1 Hz (1 sample per second)**.
- **File Naming Protocol:**
  - `driveX.csv` (13 files): Highway and arterial road travel.
  - `idleX.csv` (18 files): Engine idling in parking / stationary mode (Vehicle speed $= 0$).
  - `liveX.csv` (10 files): Real urban commute runs (e.g. UFPE campus to residential areas).
- **Critical Structural Bug Discovered: Trailing Comma Header Shift:**
  - *Symptom:* In all 41 CSV files, each data line ends with an unquoted trailing comma `,` (28 fields) while the header line contains only 27 parameter names.
  - *Impact:* Naive `pandas.read_csv("drive1.csv")` shifts all column names one position to the left (treating `ENGINE_RUN_TINE` as the row index, assigning vehicle speed to RPM, and leaving the final column as `NaN`).
  - *Fix:* Must be parsed strictly with **`index_col=False`** (e.g., `pd.read_csv(filepath, index_col=False)`).
- **Critical Diagnostic & Quality Findings:**
  1. **Duplicate File:** `live6 (1).csv` is a byte-identical duplicate of `live6.csv`.
  2. **Header Typo:** Column 1 is misspelled as `ENGINE_RUN_TINE ()` instead of `ENGINE_RUN_TIME ()`.
  3. **Zero Active Trouble Codes (DTCs):**
     - `TIME_RUN_WITH_MIL_ON ()`: **0.00** across all 90,676 records.
     - `DISTANCE_TRAVELED_WITH_MIL_ON ()`: **0.00** across all 90,676 records.
     - `TIME_SINCE_TROUBLE_CODES_CLEARED ()`: Maximum 12,709 seconds ($\approx 3.5$ hours of continuous trouble-free engine operation).
  4. **Health Assessment:** The readings reflect completely normal, healthy engine parameters:
     - Engine RPM: 0 to 2,966 RPM (idle: $\approx 750\text{--}850\text{ RPM}$).
     - Coolant Temperature: 23°C (ambient start) to 95°C (thermostat regulated operating temperature).
     - Battery / Control Module Voltage: 11.89V to 14.41V (normal alternator charging).
     - Speed: 0 to 103 km/h.
  5. **Diagnostic Inference:** **An OBD reading does NOT prove a mechanical failure.** None of these 90,676 records represent engine failure or active fault codes; they represent baseline operational telemetry.

---

## 3. CAR OS Architectural Feature Compatibility Matrix

| CAR OS Production Feature | CarDekho Dataset | Vehicle Maintenance Records | India EV Range Dataset | carOBD (Toyota Etios) |
| :--- | :--- | :--- | :--- | :--- |
| **Resale Valuation Engine**<br>([`services/vehicle_service.py`](file:///d:/caros/services/vehicle_service.py)) | **Direct Fit (100%)**<br>Provides empirical INR depreciation by make, model, age, km, and fuel. | **Partial / Indirect**<br>Provides maintenance spend history to compute condition penalties. | **Contextual**<br>Provides showroom ex-showroom prices in Lakh INR for EVs. | **Incompatible**<br>Does not contain vehicle transaction prices. |
| **Maintenance Cost Forecasting**<br>([`routes/maintenance_routes.py`](file:///d:/caros/routes/maintenance_routes.py)) | **Incompatible**<br>No service line items or maintenance bills. | **Direct Fit (95%)**<br>Periodic service costs, replacement parts, and labor schedules for Honda & Toyota. | **Incompatible**<br>EV operational range only; no maintenance records. | **Incompatible**<br>Sensor telemetry only; no service invoices or repair costs. |
| **OBD-II Live Telemetry & Viewer**<br>([`templates/vehicle_detail.html`](file:///d:/caros/templates/vehicle_detail.html)) | **Incompatible**<br>No sensor telemetry. | **Incompatible**<br>No live OBD sensor readings. | **Incompatible**<br>Simulated trip parameters, not CAN/OBD PIDs. | **Direct Fit (100%)**<br>Real RPM, speed, coolant temp, engine load, throttle %, and module voltage. |
| **Fuel / Energy Economy**<br>([`services/analytics_service.py`](file:///d:/caros/services/analytics_service.py)) | **Incompatible**<br>Only indicates fuel type. | **Incompatible**<br>Does not record fuel fill volumes. | **Direct Fit (100%)**<br>Specific $kWh/km$ consumption and real-world range across driving styles. | **Partial**<br>Contains fuel trims (`LTFT`, `STFT`) and air-fuel equivalence ratio. |
| **Total Cost of Ownership (TCO)**<br>([`routes/analytics_routes.py`](file:///d:/caros/routes/analytics_routes.py)) | **Core Asset**<br>Provides base acquisition price and asset depreciation curve. | **Core Asset**<br>Provides scheduled annual service cost ($\approx ₹5,200/\text{year}$). | **Core Asset for EVs**<br>Provides electricity consumption per km ($kWh/km$). | **Incompatible**<br>No cost variables. |

---

## 4. Integration Risks & Required Transformations

### Risk 1: Currency & Geographic Unit Harmonization
- **CarDekho:** Clean INR (₹) and km. Transformation required: normalize vehicle `name` string to separate `make` (e.g. `"Maruti"`) from `model` (e.g. `"Wagon R"`).
- **Vehicle Maintenance:** Clean INR (₹) and km. Transformation required: rename typo `whell_alignment_and_balancing` to `wheel_alignment_and_balancing`.
- **India EV Range:** Currency is in **Lakh INR** (e.g., $17.5 \to ₹17,50,000$). Transformation required: multiply `price_lakh_INR * 100000` when comparing against standard CAR OS currency fields.
- **carOBD:** Recorded in **Brazil** on a flex-fuel Etios. Driving speeds and temperatures are metric (km/h, °C). Telemetry is universal OBD-II PID standard, but must NOT be mislabeled as an Indian fleet deployment.

### Risk 2: Trailing Comma Parsing in carOBD
- Standard CSV loaders will corrupt columns unless `index_col=False` is passed. Any integration pipeline must include:
  ```python
  df = pd.read_csv(filepath, index_col=False)
  df.columns = [c.replace(" ()", "").strip() for c in df.columns]
  ```

### Risk 3: Synthetic vs Ground Truth Distinction
- `india_ev_range_dataset.csv` must be labeled as a **"Physics-based Simulation Model"** in the CAR OS UI, not "Live Vehicle BMS Data".
- carOBD data represents a **healthy baseline vehicle**; it must NOT be used to simulate engine failures or trigger false diagnostic alarms.

---

## 5. Final Strategic Recommendations for CAR OS

```
                                CAR OS DATASET ROADMAP
 ┌───────────────────────────────────────────┬───────────────────────────────────────────┐
 │       RECOMMENDED FOR PRODUCTION          │         RECOMMENDED FOR EXPERIMENTS       │
 ├───────────────────────────────────────────┼───────────────────────────────────────────┤
 │ 1. CarDekho Used Car Dataset              │ 3. India EV Range Dataset                 │
 │    • Replace synthetic resale regressor   │    • Physics-based EV trip simulator      │
 │    • Grounded in 4,340 real INR sales     │    • Multi-city ambient temperature model │
 │                                           │                                           │
 │ 2. Vehicle Maintenance Service Records    │ 4. carOBD (Toyota Etios OBD-II)           │
 │    • Grounded scheduled service pricing   │    • Real-time 1 Hz telemetry playback    │
 │    • 14 component replacement schedules   │    • Normal operating parameter baselines │
 └───────────────────────────────────────────┴───────────────────────────────────────────┘
```

1. **CarDekho Used Car Dataset $\to$ APPROVE FOR INTEGRATION:**
   - Retrain CAR OS's `resale_regressor.pkl` using deduplicated CarDekho data. This will transition CAR OS resale valuation from synthetic heuristics to real-world Indian market empirical pricing.
2. **Vehicle Maintenance Records $\to$ APPROVE FOR INTEGRATION:**
   - Incorporate periodic service costs into CAR OS's maintenance recommendation engine, giving users realistic maintenance expense forecasts for Indian hatchbacks, sedans, and SUVs.
3. **India EV Range Dataset $\to$ RESTRICT TO EXPERIMENTAL SIMULATOR:**
   - Do not claim empirical on-road fleet telemetry. Retain in `experiments/` to power an optional "EV Range What-If Scenario Calculator" for electric vehicles in the CAR OS fleet.
4. **carOBD (Toyota Etios) $\to$ RESTRICT TO EXPERIMENTAL TELEMETRY STREAMER:**
   - Use as a realistic 1 Hz hardware streaming test vector for CAR OS's live OBD dashboard viewer, keeping Brazilian origin clearly documented.
