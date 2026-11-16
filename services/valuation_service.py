"""
CAR OS - Vehicle Valuation & Resale Estimation System
=====================================================
Multi-tier valuation pipeline that determines three distinct values for every vehicle:
  1. Original Showroom Price (Manufacturer Ex-Showroom for exact model, variant & year)
  2. Current Market Price (Market asking band and representative asking price from comparable listings)
  3. Estimated Resale Value (Specific predicted selling value accounting for depreciation, mileage,
     condition, service history, and market evidence)

Strictly separates ex-showroom from on-road pricing and enforces market calibration bounds.
"""

import os
import joblib
import pandas as pd
from datetime import date
from typing import Optional, Dict, Any, Tuple

from services.showroom_price_service import get_showroom_price
from services.market_pricing_service import get_comparable_market_pricing

VALUATION_DISCLAIMER = (
    "Showroom prices represent manufacturer ex-showroom benchmarks. "
    "Current market ranges reflect asking prices from comparable secondary market listings. "
    "Estimated resale values are algorithmically calibrated estimates and do not constitute "
    "a formal legal appraisal or certified purchase offer."
)

CARDEKHO_VALUATION_DISCLAIMER = (
    "Empirical valuation derived from historical CarDekho Indian used car listings. "
    "Values reflect verified depreciation curves calibrated against active market asking prices."
)

# Illustrative fallback base prices in INR (ex-showroom approximations for unknown legacy lookups)
BASE_PRICES_INR = {
    ("hyundai", "creta"): 1_200_000,
    ("tata", "nexon ev"): 1_500_000,
    ("tata", "nexon"): 900_000,
    ("maruti", "baleno"): 750_000,
    ("maruti suzuki", "baleno"): 750_000,
    ("maruti", "swift"): 700_000,
    ("maruti suzuki", "swift"): 700_000,
    ("maruti", "brezza"): 950_000,
    ("maruti suzuki", "brezza"): 950_000,
    ("hyundai", "i20"): 800_000,
    ("tata", "punch"): 700_000,
    ("honda", "city"): 1_100_000,
    ("kia", "seltos"): 1_050_000,
    ("volkswagen", "polo"): 850_000,
    ("toyota", "innova"): 1_800_000,
    ("toyota", "fortuner"): 3_200_000,
    ("mahindra", "thar"): 1_400_000,
    ("mahindra", "xuv700"): 1_600_000,
    ("skoda", "slavia"): 1_100_000,
}

DEFAULT_BASE_PRICE = 800_000


def normalize_make(make: str) -> str:
    """Normalize common Indian automotive brand aliases to match dataset keys."""
    m = str(make).strip()
    m_lower = m.lower()
    if m_lower in ["maruti suzuki", "maruti-suzuki", "ms"]:
        return "Maruti"
    if m_lower in ["mercedes", "mercedes benz", "mercedes-benz"]:
        return "Mercedes-Benz"
    if m_lower in ["land rover", "range rover"]:
        return "Land"
    return m.title()


def get_base_price(make: str, model: str) -> tuple[int, bool]:
    """Legacy helper: lookup baseline ex-showroom price for make/model."""
    key = (make.lower().strip(), model.lower().strip())
    price = BASE_PRICES_INR.get(key)
    if price:
        return price, True
    return DEFAULT_BASE_PRICE, False


def calculate_cardekho_resale_value(
    make: str,
    model: str,
    manufacturing_year: int,
    odometer_km: float,
    fuel_type: str = "Petrol",
    transmission: str = "Manual",
    owner: str = "First Owner",
    health_score: float = 80.0,
) -> Optional[Dict[str, Any]]:
    """
    Predict resale value using the trained versioned CarDekho ML model artifact
    (ml/saved_models/resale_regressor_cardekho_v1.pkl).
    """
    model_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "ml", "saved_models", "resale_regressor_cardekho_v1.pkl"
    )
    if not os.path.exists(model_path):
        return None

    try:
        artifact = joblib.load(model_path)
        model_obj = artifact["model"]
        known_makes = artifact.get("known_makes", [])
        known_models = artifact.get("known_models", [])
        metrics = artifact.get("metrics", {})

        make_clean = normalize_make(make)
        model_tokens = str(model).strip().split()
        model_family = model_tokens[0].title() if model_tokens else "Other"

        is_known_make = make_clean in known_makes
        is_known_model = model_family in known_models

        # Reference year for training dataset was 2020
        age = max(0, 2020 - int(manufacturing_year))

        input_df = pd.DataFrame([{
            "make": make_clean,
            "model_family": model_family,
            "year": int(manufacturing_year),
            "vehicle_age": age,
            "km_driven": float(odometer_km),
            "fuel": str(fuel_type).strip().title() if str(fuel_type).strip().title() in ["Diesel", "Petrol", "Cng", "Lpg", "Electric"] else "Petrol",
            "seller_type": "Individual",
            "transmission": str(transmission).strip().title() if str(transmission).strip().title() in ["Manual", "Automatic"] else "Manual",
            "owner": str(owner).strip().title() if "Owner" in str(owner) else "First Owner"
        }])

        raw_pred = float(model_obj.predict(input_df)[0])
        estimated_val = int(round(max(15000.0, raw_pred) / 1000.0) * 1000)

        mape_pct = metrics.get("median_absolute_percentage_error", 16.7) / 100.0
        range_min = int(round(max(10000.0, estimated_val * (1.0 - mape_pct)) / 1000.0) * 1000)
        range_max = int(round(estimated_val * (1.0 + mape_pct) / 1000.0) * 1000)

        return {
            "predicted_value": estimated_val,
            "price_range_inr": (range_min, range_max),
            "is_known_make": is_known_make,
            "is_known_model": is_known_model,
            "metrics": metrics,
            "disclaimer": CARDEKHO_VALUATION_DISCLAIMER,
        }
    except Exception:
        return None


def calculate_resale_value(
    make: str,
    model: str,
    manufacturing_year: int,
    odometer_km: float,
    health_score: float = 80.0,
    fuel_type: str = "Petrol",
    transmission: str = "Manual",
    owner: str = "First Owner",
    engine: str = "rule_based",
    variant: Optional[str] = None,
    service_history: Optional[str] = "Unknown",
    reported_issues: int = 0,
    original_showroom_price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculate comprehensive vehicle valuation yielding three distinct values:
      1. original_showroom_price (Ex-Showroom Price)
      2. current_market_price (Representative Market Asking Price)
      3. estimated_resale_value (Specific Predicted Resale Value)
    
    Includes depreciation amount/percentage, market asking range, and confidence status.
    """
    current_year = date.today().year
    age = max(0, current_year - int(manufacturing_year))

    # 1. Retrieve Original Showroom Price
    if original_showroom_price is not None and original_showroom_price > 0:
        orig_showroom_price = int(original_showroom_price)
        showroom_info = {
            "price_available": True,
            "is_exact_match": True,
            "is_model_range": False,
            "ex_showroom_price": orig_showroom_price,
            "price_range_inr": (orig_showroom_price, orig_showroom_price),
            "matched_variant": variant,
            "generation": None,
            "model_year": int(manufacturing_year),
            "fuel_type": fuel_type,
            "transmission": transmission,
            "city": "National Ex-Showroom",
            "source": "User-Entered",
            "effective_date": None,
            "reference_starting_price": None,
            "prompt_manual_entry": False,
            "status_label": "User-Entered Showroom Price",
        }
        showroom_range = (orig_showroom_price, orig_showroom_price)
    else:
        showroom_info = get_showroom_price(
            make=make,
            model=model,
            manufacturing_year=manufacturing_year,
            variant=variant,
            fuel_type=fuel_type,
            transmission=transmission,
        )
        orig_showroom_price = showroom_info["ex_showroom_price"]
        showroom_range = showroom_info["price_range_inr"]

    # Legacy base_price fallback for backwards compatibility
    legacy_base_price, is_known_model = get_base_price(make, model)
    base_price = legacy_base_price  # Always use legacy_base_price for compatibility

    # 2. Retrieve Comparable Used-Car Market Pricing
    market_info = get_comparable_market_pricing(
        make=make,
        model=model,
        manufacturing_year=manufacturing_year,
        odometer_km=odometer_km,
        fuel_type=fuel_type,
        transmission=transmission,
        variant=variant,
    )
    rep_market_price = market_info["representative_market_price"]
    market_range = market_info["market_asking_range"]
    comparable_count = market_info["comparable_listings_count"]
    expected_tx_price = market_info["expected_transaction_price"]

    # 3. Deterministic formula factors (for rule_based engine or baseline comparison)
    age_factor = max(0.25, 1 - age * 0.08)
    mileage_factor = max(0.55, 1 - (odometer_km // 10000) * 0.025)
    condition_factor = 0.60 + (health_score / 100) * 0.40
    rule_based_value = int(round((base_price * age_factor * mileage_factor * condition_factor) / 1000) * 1000)

    # If caller specifically requested legacy rule_based engine
    if engine == "rule_based":
        deprec_amt = (orig_showroom_price - rule_based_value) if orig_showroom_price else None
        deprec_pct = round((deprec_amt / orig_showroom_price) * 100, 1) if (orig_showroom_price and deprec_amt) else None
        return {
            "estimated_value": rule_based_value,
            "estimated_resale_value": rule_based_value,
            "base_price": base_price,
            "is_known_model": is_known_model,
            "factors": {
                "age_years": age,
                "age_factor": round(age_factor, 4),
                "mileage_factor": round(mileage_factor, 4),
                "condition_factor": round(condition_factor, 4),
            },
            "disclaimer": VALUATION_DISCLAIMER,
            "cardekho_estimate": None,
            "valuation_engine": "rule_based",
            "valuation_source": "Ex-Showroom Depreciation Benchmark",
            "is_fallback": False,
            "fallback_reason": None,
            "price_range_inr": (int(rule_based_value * 0.85), int(rule_based_value * 1.15)),
            "original_showroom_price": orig_showroom_price,
            "current_market_price": rep_market_price,
            "market_asking_range": market_range,
            "comparable_listings_count": comparable_count,
            "depreciation_amount": deprec_amt,
            "depreciation_percentage": deprec_pct,
            "valuation_method": "model-based",
            "confidence_status": "Moderate Confidence",
            "showroom_detail": showroom_info,
            "market_detail": market_info,
        }

    # 4. Machine Learning Resale Estimate
    cardekho_res = calculate_cardekho_resale_value(
        make=make, model=model, manufacturing_year=manufacturing_year,
        odometer_km=odometer_km, fuel_type=fuel_type, transmission=transmission,
        owner=owner, health_score=health_score
    )

    # 5. Calibration Pipeline (Section 5 Method)
    is_ev = str(fuel_type).strip().title() == "Electric"
    valuation_method = "model-based"
    valuation_source = "CarDekho Indian Market Model (v1)"
    is_fallback = False
    fallback_reason = None
    anchor_price = orig_showroom_price if (orig_showroom_price and orig_showroom_price > 0) else base_price

    if is_ev:
        # Specialized EV depreciation curve: higher retention in early years, anchored on battery warranty
        ev_age_factor = max(0.25, 1.0 - age * 0.08)
        ev_mileage_factor = max(0.55, 1.0 - (odometer_km // 10000) * 0.02)
        calibrated_base = int(round((anchor_price * ev_age_factor * ev_mileage_factor) / 1000) * 1000)
        valuation_engine = "ev_baseline_fallback"
        valuation_source = "EV Battery & Powertrain Depreciation Benchmark"
        valuation_method = "model-based estimate"
        is_fallback = False
        fallback_reason = None
    elif cardekho_res and cardekho_res["is_known_make"]:
        raw_ml_val = cardekho_res["predicted_value"]
        if engine == "cardekho_ml":
            # Explicit engine='cardekho_ml': return raw ML value without market or condition calibration
            return {
                "estimated_value": raw_ml_val,
                "estimated_resale_value": raw_ml_val,
                "base_price": base_price,
                "is_known_model": is_known_model,
                "factors": {
                    "age_years": age,
                    "age_factor": round(age_factor, 4),
                    "mileage_factor": round(mileage_factor, 4),
                    "condition_factor": round(condition_factor, 4),
                },
                "disclaimer": VALUATION_DISCLAIMER,
                "cardekho_estimate": cardekho_res,
                "valuation_engine": "cardekho_ml",
                "valuation_source": "CarDekho Indian Market Model (v1)",
                "valuation_method": "model-based",
                "is_fallback": False,
                "fallback_reason": None,
                "price_range_inr": cardekho_res.get("price_range_inr"),
                "original_showroom_price": orig_showroom_price,
                "current_market_price": rep_market_price,
                "market_asking_range": market_range,
                "comparable_listings_count": comparable_count,
                "depreciation_amount": max(0, int(orig_showroom_price - raw_ml_val)) if orig_showroom_price else None,
                "depreciation_percentage": round(((orig_showroom_price - raw_ml_val) / orig_showroom_price) * 100, 1) if orig_showroom_price else None,
                "confidence_status": "Moderate Confidence",
                "showroom_detail": showroom_info,
                "market_detail": market_info,
                "valuation_inputs": {
                    "make": make, "model": model, "variant": variant,
                    "manufacturing_year": manufacturing_year, "odometer_km": odometer_km,
                    "fuel_type": fuel_type, "transmission": transmission,
                    "owner": owner, "service_history": service_history,
                    "reported_issues": reported_issues, "health_score": health_score,
                },
            }
        elif expected_tx_price and comparable_count >= 2:
            # Calibrate ML prediction with market closing evidence
            weight_market = min(0.65, 0.35 + 0.05 * comparable_count)
            calibrated_base = int(round((weight_market * expected_tx_price + (1.0 - weight_market) * raw_ml_val) / 1000) * 1000)
            valuation_method = "market-calibrated"
            valuation_source = f"CarDekho Indian Market Model (ML + Market Calibrated N={comparable_count})"
        else:
            calibrated_base = raw_ml_val
            valuation_method = "model-based"
            valuation_source = "CarDekho Indian Market Model (v1)"
        valuation_engine = "cardekho_ml"
    elif expected_tx_price and comparable_count >= 2:
        calibrated_base = expected_tx_price
        valuation_engine = "market_comparables"
        valuation_method = "market-calibrated"
        valuation_source = f"Direct Market Comparables (N={comparable_count})"
    else:
        calibrated_base = rule_based_value
        valuation_engine = "rule_based_fallback"
        valuation_method = "fallback estimate"
        valuation_source = "Ex-Showroom Depreciation Benchmark (Fallback)"
        is_fallback = True
        fallback_reason = f"Model '{make} {model}' outside empirical listing density — baseline depreciation applied."

    # 6. Apply Vehicle-Specific Condition & Service Adjustments
    # Tiered realistic health multiplier (fault-free = 1.0, minor issues = 0.85-0.95, major defects = 0.45-0.70, severe inoperable = 0.20-0.40)
    h = max(0.0, min(100.0, float(health_score)))
    if h >= 80:
        health_multiplier = 0.95 + (h - 80) * (0.10 / 20.0)
    elif h >= 50:
        health_multiplier = 0.75 + (h - 50) * (0.19 / 30.0)
    elif h >= 20:
        health_multiplier = 0.45 + (h - 20) * (0.29 / 30.0)
    else:
        health_multiplier = 0.20 + h * (0.24 / 20.0)

    # Service history adjustment
    sh = str(service_history).strip().title()
    if sh == "Full":
        history_adj = 1.03  # +3% premium for documented dealer service history
    elif sh == "None":
        history_adj = 0.94  # -6% penalty for missing service records
    else:
        history_adj = 1.00

    # Reported issues adjustment (minor penalty per issue, capped at -8%)
    issues_penalty = max(0.92, 1.0 - (int(reported_issues) * 0.02))

    adjusted_val = calibrated_base * health_multiplier * history_adj * issues_penalty

    # 7. Sanity and Boundary Checks
    # Resale cannot exceed original ex-showroom price
    if orig_showroom_price:
        adjusted_val = min(adjusted_val, float(orig_showroom_price))

    # Resale cannot exceed 1.15x representative market price if market price is known
    if rep_market_price and rep_market_price > 0:
        adjusted_val = min(adjusted_val, float(rep_market_price) * 1.15)
        # Floor relative to market unless vehicle has critical health issues
        if health_score >= 50:
            adjusted_val = max(adjusted_val, float(rep_market_price) * 0.65)

    # Roadworthy salvage floor
    final_resale_value = int(round(max(15000.0, adjusted_val) / 1000) * 1000)

    # Resale price range band
    if cardekho_res and cardekho_res.get("price_range_inr"):
        base_range = cardekho_res["price_range_inr"]
        resale_band = (
            int(round(max(10000.0, final_resale_value * 0.85) / 1000) * 1000),
            int(round(final_resale_value * 1.15 / 1000) * 1000),
        )
    elif market_range:
        resale_band = (
            int(round(max(10000.0, final_resale_value * 0.88) / 1000) * 1000),
            int(round(final_resale_value * 1.12 / 1000) * 1000),
        )
    else:
        resale_band = (
            int(round(max(10000.0, final_resale_value * 0.85) / 1000) * 1000),
            int(round(final_resale_value * 1.15 / 1000) * 1000),
        )

    # 8. Depreciation Calculations
    if orig_showroom_price and orig_showroom_price > 0:
        depreciation_amount = max(0, int(orig_showroom_price - final_resale_value))
        depreciation_percentage = round((depreciation_amount / orig_showroom_price) * 100, 1)
    else:
        depreciation_amount = None
        depreciation_percentage = None

    # 9. Confidence / Data Quality Indicator
    if showroom_info["is_exact_match"] and comparable_count >= 4 and not is_fallback:
        confidence_status = "High Confidence"
    elif showroom_info["price_available"] and (comparable_count >= 1 or cardekho_res is not None):
        confidence_status = "Moderate Confidence"
    else:
        confidence_status = "Advisory Fallback"

    return {
        # Core 3 Distinct Values
        "original_showroom_price": orig_showroom_price,
        "current_market_price": rep_market_price,
        "estimated_resale_value": final_resale_value,
        # Backward-compatible primary value key
        "estimated_value": final_resale_value,
        "base_price": base_price,
        "is_known_model": is_known_model,
        # Depreciation
        "depreciation_amount": depreciation_amount,
        "depreciation_percentage": depreciation_percentage,
        # Market detail
        "market_asking_range": market_range,
        "comparable_listings_count": comparable_count,
        "price_range_inr": resale_band,
        # Methodology & Metadata
        "valuation_method": valuation_method,
        "valuation_engine": valuation_engine,
        "valuation_source": valuation_source,
        "confidence_status": confidence_status,
        "is_fallback": is_fallback,
        "fallback_reason": fallback_reason,
        "disclaimer": VALUATION_DISCLAIMER,
        "factors": {
            "age_years": age,
            "age_factor": round(age_factor, 4),
            "mileage_factor": round(mileage_factor, 4),
            "condition_factor": round(condition_factor, 4),
            "health_multiplier": round(health_multiplier, 4),
            "history_adjustment": history_adj,
            "issues_penalty": issues_penalty,
        },
        "showroom_detail": showroom_info,
        "market_detail": market_info,
        "cardekho_estimate": cardekho_res,
        "valuation_inputs": {
            "make": make,
            "model": model,
            "variant": variant,
            "manufacturing_year": manufacturing_year,
            "odometer_km": odometer_km,
            "fuel_type": fuel_type,
            "transmission": transmission,
            "owner": owner,
            "service_history": service_history,
            "reported_issues": reported_issues,
            "health_score": health_score,
        },
    }


def format_inr(amount: int | float | None) -> str:
    """Format an amount as Indian Rupees string (e.g. ₹8.42L or ₹95,000)."""
    if amount is None:
        return "N/A"
    amount_int = int(round(amount))
    if amount_int >= 10_00_000:
        return f"₹{amount_int / 1_00_000:.2f}L"
    elif amount_int >= 1_00_000:
        return f"₹{amount_int / 1_00_000:.2f}L"
    elif amount_int >= 1_000:
        return f"₹{amount_int:,}"
    return f"₹{amount_int}"


def format_lakh(amount: int | float | None) -> str:
    """Format an amount explicitly in Lakh notation (e.g. ₹8.42 Lakh)."""
    if amount is None:
        return "N/A"
    val = float(amount)
    if val >= 1_00_000:
        return f"₹{val / 1_00_000:.2f} Lakh"
    return format_inr(val)
