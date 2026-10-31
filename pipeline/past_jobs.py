"""Invent 80 past jobs (synthetic) priced with the same rules plus noise, so retrieval has something to find.
Output: data/past_jobs.json
"""
import datetime as dt
import sys
import json
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_rfqs import MS_CERTS, MS_ITEMS, MS_TOL, SC_CERTS, SC_ITEMS, SC_TOL, gen_dims
from pricing import price

ROOT = Path(__file__).resolve().parent.parent


def main():
    rng = random.Random(4242)
    jobs = []
    for i in range(1, 81):
        fam = "service_center" if i % 2 else "machine_shop"
        item = rng.choice(SC_ITEMS if fam == "service_center" else MS_ITEMS)
        dims, _ = gen_dims(rng, item["form"], False, False)
        tol = rng.choice(SC_TOL if fam == "service_center" else MS_TOL)
        qty = rng.choice([4, 6, 10, 12, 20, 25, 40, 60] if fam == "service_center" else [25, 50, 100, 150, 250, 500, 1000])
        cert = rng.choice(SC_CERTS if fam == "service_center" else MS_CERTS)
        finish = rng.choice(item["finish"])
        lead = rng.choice([5, 8, 12, 15, 21, 28, 35])
        t = price(fam, item["grade"], dims, "in", tol, qty, dt.date(2026, 1, 1) + dt.timedelta(days=lead), dt.date(2026, 1, 1))
        base = t["total"] if t["status"] == "priced" else 1000.0
        sold = round(base * rng.uniform(0.92, 1.10), 2)
        summary = (f"{fam.replace('_', ' ')}: {item['grade']} {item['form'].replace('_', ' ')} {dims}, qty {qty}, "
                   f"tolerance {tol}, finish {finish}, certs {cert}")
        jobs.append({"job_id": f"JOB-{i:03d}", "family": fam, "summary": summary, "qty": qty,
                     "unit_price": round(sold / qty, 2), "total_price": sold, "lead_days": lead})
    (ROOT / "data" / "past_jobs.json").write_text(json.dumps(jobs, indent=2) + "\n")
    print(len(jobs), "past jobs written")


if __name__ == "__main__":
    main()
