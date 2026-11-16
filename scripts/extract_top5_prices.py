"""
Extracts and normalizes starting vehicle prices from Top5_Car_Brands_India_Prices_15plus.pdf
into structured CSV and JSON datasets.

Preserves:
- Exact provenance (Autocar India, 91Wheels, CarDekho, CarOnPhone, CarTrade, Rushlane)
- Date (2026-10-28)
- Starting price status (is_starting_price = True)
- Uncertainty flags (is_approximate)
- Crucial notes (e.g. e Vitara battery extra, Creta N Line sources differ, Tucson facelift, Vellfire/Land Cruiser in crore)
"""

import os
import re
import csv
import json
import pypdf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_PATH = os.path.join(BASE_DIR, "dataset", "Top5_Car_Brands_India_Prices_15plus.pdf")
OUTPUT_CSV_PATH = os.path.join(BASE_DIR, "data", "indian_starting_prices_top5.csv")
OUTPUT_JSON_PATH = os.path.join(BASE_DIR, "data", "indian_starting_prices_top5.json")


def extract_starting_prices(pdf_path: str = PDF_PATH) -> list[dict]:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF reference document not found: {pdf_path}")

    reader = pypdf.PdfReader(pdf_path)
    text = "\n".join(p.extract_text() for p in reader.pages)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    brand_pattern = re.compile(r"^\d+\.\s+([A-Za-z\s]+)\s+\((\d+)\s+models.*?\)")
    header_tokens = {"model", "fuel", "from (rs. lakh)"}

    current_brand = None
    items = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m_brand = brand_pattern.match(line)
        if m_brand:
            current_brand = m_brand.group(1).strip()
            i += 1
            continue
        if (
            current_brand
            and line.lower() not in header_tokens
            and not line.startswith("Top 5")
            and not line.startswith("Popular")
            and not line.startswith("Prices are")
            and not line.startswith("Sources:")
        ):
            if i + 2 < len(lines):
                fuel = lines[i + 1]
                price_line = lines[i + 2]
                if any(c.isdigit() for c in price_line) or "crore" in price_line.lower():
                    items.append({
                        "brand": current_brand,
                        "model": line,
                        "fuel": fuel,
                        "raw_price": price_line,
                    })
                    i += 3
                    continue
        i += 1

    parsed_rows = []
    for it in items:
        brand = it["brand"]
        model = it["model"]
        fuel = it["fuel"]
        raw_p = it["raw_price"]

        is_approx = "about" in raw_p.lower()
        notes = []

        if "battery extra" in raw_p.lower():
            notes.append("Battery extra (subscription or pack separate)")
        if "sources differ" in raw_p.lower():
            notes.append("Sources differ across Autocar, CarDekho, CarTrade (range estimated)")
        if "check availability" in raw_p.lower() or "facelift" in raw_p.lower():
            notes.append("Facelift edition; regional dealer availability varies")
        if "crore" in raw_p.lower():
            notes.append("Luxury flagship vehicle; price quoted in Crore")

        if "crore" in raw_p.lower():
            unit = "Crore"
            nums = re.findall(r"\d+\.?\d*", raw_p)
            val_cr = float(nums[0]) if nums else 1.0
            p_min = p_max = int(round(val_cr * 10_000_000))
        elif "-" in raw_p:  # Range: e.g. About 17.8 - 19.0
            unit = "Lakh"
            nums = re.findall(r"\d+\.?\d*", raw_p)
            v1 = float(nums[0])
            v2 = float(nums[1])
            p_min = int(round(v1 * 100_000))
            p_max = int(round(v2 * 100_000))
        else:
            unit = "Lakh"
            nums = re.findall(r"\d+\.?\d*", raw_p)
            val = float(nums[0]) if nums else 0.0
            p_min = p_max = int(round(val * 100_000))

        parsed_rows.append({
            "brand": brand,
            "model": model,
            "fuel_types": fuel,
            "raw_price_string": raw_p,
            "price_unit": unit,
            "starting_price_lakh_min": round(p_min / 100_000, 2),
            "starting_price_lakh_max": round(p_max / 100_000, 2),
            "starting_price_inr_min": p_min,
            "starting_price_inr_max": p_max,
            "starting_price_inr": p_min,
            "is_starting_price": True,
            "is_approximate": is_approx,
            "notes": "; ".join(notes) if notes else "Starting ex-showroom price for base trim",
            "sources": "Autocar India, 91Wheels, CarDekho, CarOnPhone, CarTrade, Rushlane",
            "effective_date": "2026-10-28",
            "source_document": "Top5_Car_Brands_India_Prices_15plus.pdf",
        })

    return parsed_rows


def save_datasets(rows: list[dict], csv_path: str = OUTPUT_CSV_PATH, json_path: str = OUTPUT_JSON_PATH):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)

    # Save CSV
    if rows:
        fieldnames = list(rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    # Save JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(rows)} rows to {csv_path} and {json_path}")


if __name__ == "__main__":
    extracted = extract_starting_prices()
    save_datasets(extracted)
    print("Sample extracted records:")
    for r in extracted[:5]:
        print(f"  {r['brand']} {r['model']} ({r['fuel_types']}) -> Rs. {r['starting_price_inr']:,} [{r['notes']}]")

