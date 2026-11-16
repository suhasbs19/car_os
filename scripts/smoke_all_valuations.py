"""Quick smoke test — print tri-tier valuations for all 8 demo vehicles."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app

app = create_app()
client = app.test_client()

print("=== All 8 Vehicles — Tri-Tier Valuation ===")
for vid in range(1, 9):
    resp = client.get(f"/api/vehicles/{vid}/valuation")
    if resp.status_code == 200:
        d = json.loads(resp.data)
        sp = d.get("original_showroom_price") or 0
        mp = d.get("current_market_price") or 0
        rv = d.get("estimated_resale_value") or 0
        vm = d.get("valuation_method", "?")
        cs = d.get("confidence_status", "?")
        make = d.get("make", "")
        model = d.get("model", "")
        variant = d.get("variant", "")
        mp_str = f"{mp/1e5:.2f}L" if mp else "N/A"
        print(f"  [{vid}] {make} {model} {variant}")
        print(f"       SP=Rs{sp/1e5:.2f}L  MP=Rs{mp_str}  RV=Rs{rv/1e5:.2f}L  | {vm} | {cs}")
    else:
        print(f"  [{vid}] ERROR {resp.status_code}")
