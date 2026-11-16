# CAR OS — Indian Resale Valuation Model Report (CarDekho Dataset)

**Date of Report:** October 28, 2026  
**Dataset Reference:** `dataset/CAR DETAILS FROM CAR DEKHO.csv`  
**Model Artifact:** `ml/saved_models/resale_regressor_cardekho_v1.pkl`  
**Training Pipeline:** `ml/train_indian_resale.py`  

---

## 1. Executive Summary

As part of the CAR OS Indian market dataset integration, the CarDekho used-car dataset was integrated into CAR OS as a versioned, selectable secondary resale valuation engine. It operates alongside the primary rule-based / baseline resale valuation pipeline without displacing or overwriting existing production models.

The dataset provides empirical depreciation, age, mileage, transmission, and fuel-type relationships across 29 distinct automotive brands sold in India.

---

## 2. Dataset Ingestion & Preprocessing

### 2.1 File & Schema Verification
- **Source File:** `dataset/CAR DETAILS FROM CAR DEKHO.csv`
- **File Size:** 232,042 bytes
- **Raw Row Count:** 4,340 rows
- **Columns (8):**
  - `name`: string (e.g., `"Maruti Swift Dzire VDI"`, `"Hyundai i20 Magna 1.2"`)
  - `year`: integer (1992 to 2020)
  - `selling_price`: float/int (Target variable, INR ₹)
  - `km_driven`: integer (Odometer reading in kilometres)
  - `fuel`: categorical (`Diesel`, `Petrol`, `CNG`, `LPG`, `Electric`)
  - `seller_type`: categorical (`Individual`, `Dealer`, `Trustmark Dealer`)
  - `transmission`: categorical (`Manual`, `Automatic`)
  - `owner`: categorical (`First Owner`, `Second Owner`, `Third Owner`, `Fourth & Above Owner`, `Test Drive Car`)

### 2.2 Deduplication & Data Quality
- **Exact Duplicate Rows:** 763 duplicate rows identified during the audit and confirmed during ingestion.
- **Deduplication Policy:** All 763 duplicates are removed in-memory in the processing layer; the original CSV is left untouched.
- **Cleaned Dataset Size:** 3,577 rows.
- **Missing / Null Values:** 0 missing values across all 8 columns.
- **Outliers & High-Value Vehicles:** High-value vehicles (e.g., luxury brands such as Audi, BMW, Mercedes-Benz, Land Rover, Volvo with selling prices up to ₹89,00,000) were retained because they represent genuine luxury vehicle transactions in the Indian secondary market.

---

## 3. Feature Engineering & Leakage Prevention

1. **Brand Extraction:** Vehicle brand is parsed from the first token of the `name` column (e.g., `"Maruti"`, `"Hyundai"`, `"Toyota"`). Rare brands (< 5 occurrences) are grouped under `"Other"`.
2. **Vehicle Age:** Computed as `reference_year - year` (anchored at `reference_year = 2020` to reflect the dataset collection timeframe).
3. **Usage Intensity:** Log-transformed `log1p(km_driven)`.
4. **Categorical Encoding:** One-hot encoding for `fuel`, `seller_type`, `transmission`, and `owner` with `handle_unknown='ignore'` to guarantee zero runtime failures when unseen categories appear in user input.
5. **Target Leakage Prevention:** Features strictly utilize pre-sale vehicle specifications (`brand`, `age`, `km_driven`, `fuel`, `transmission`, `seller_type`, `owner`). The target `selling_price` is log-transformed (`log1p(selling_price)`) strictly for target modeling and never utilized as an input feature.
6. **Data Partitioning:** Fixed 80/20 train/test split with `random_state=42`. All preprocessing pipelines and scaler transformations are fit exclusively on the training set (2,861 records) and evaluated on the held-out test set (716 records).

---

## 4. Model Training & Benchmark Comparison

Three architectures were trained and benchmarked on the held-out test set (716 records):

| Model Architecture | Target Space | MAE (₹ INR) | RMSE (₹ INR) | R² Score | Median APE (%) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Dummy Regressor (Median Baseline)** | Linear Price | ₹2,83,304.75 | ₹6,00,209.68 | -0.0632 | 68.6% |
| **Ridge Regression (L2 Linear)** | Log-Price (`log1p`) | ₹1,40,451.44 | ₹3,66,743.02 | 0.6020 | 25.1% |
| **Gradient Boosting Regressor (GBR)** | Log-Price (`log1p`) | **₹1,12,600.84** | **₹3,36,926.39** | **0.6642** | **16.69%** |

### Selected Model Specifications
- **Algorithm:** Gradient Boosting Regressor (GBR)
- **Hyperparameters:** `n_estimators=180`, `max_depth=4`, `learning_rate=0.08`, `subsample=0.85`, `random_state=42`.
- **Primary Metric:** Held-out $R^2 = 0.6642$ with a Median Absolute Percentage Error (MAPE) of **16.69%**.
- **Error Bounds / Confidence Interval:** The model returns a point estimate along with an empirical uncertainty range of $\pm 16.7\%$, informing users of the price band expected across Indian secondary markets.

---

## 5. Artifact & Integration Architecture

- **Artifact Path:** `ml/saved_models/resale_regressor_cardekho_v1.pkl`
- **Payload Metadata:** Includes the scikit-learn pipeline, brand list, feature names, held-out evaluation metrics, and uncertainty bounds.
- **Service Layer (`services/valuation_service.py`):**
  - Exposes `calculate_cardekho_resale_value(...)` which automatically extracts brand, maps unknown makes to `"Other"`, runs the GBR pipeline, inverts the log target, and returns the point estimate with lower and upper confidence bounds.
  - Exposes `calculate_resale_value(vehicle, engine='cardekho_ml')` as an independently selectable valuation backend while retaining `engine='rule_based'` as default/fallback.
- **UI Integration (`templates/vehicle_detail.html`):**
  - Displays the CarDekho Indian Valuation estimate card alongside the standard CAR OS valuation.
  - Clearly tags the estimate as an empirical ML model trained on Indian used-car transactions with an uncertainty price band.

---

## 6. Limitations & Market Disclaimers

1. **Temporal Horizon (2020 Data vs. 2026 Local Market):** The CarDekho records were gathered up to 2020. Post-2020 inflationary trends, semiconductor supply constraints, and Bharat Stage VI (BS6 Phase II) norms are not captured in the raw transactional records.
2. **Odometer Tampering & Condition Blindness:** The dataset contains no records of accidental history, paint thickness, or tyre condition. Predictions assume average cosmetic and mechanical condition.
3. **Regional Pricing Variations:** Prices reflect pan-Indian aggregations and do not differentiate high-tax states (e.g., Karnataka) from lower-tax states (e.g., Delhi, Chandigarh).
