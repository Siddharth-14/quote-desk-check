"""Join extraction -> checker -> pricing -> retrieval -> draft into data/outputs/results.json.

Run order for a fresh clone:
  python pipeline/generate_rfqs.py   (local Ollama; skip to reuse data/rfqs.json)
  python pipeline/past_jobs.py
  python pipeline/extract.py         (local Ollama)
  python pipeline/run_all.py         (local Ollama for drafts)
  python eval/run_eval.py
"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from checker import check  # noqa: E402
from draft import make_draft  # noqa: E402
from pricing import price, withheld  # noqa: E402
from retrieve import Retriever  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "outputs"


def query_text(rfq, ex, flags):
    parts = [rfq["family"].replace("_", " ")]
    for f in ("material_grade", "dimensions", "quantity", "tolerance", "finish", "certs"):
        if f in flags["present"]:
            parts.append(f"{f.replace('_', ' ')} {ex[f]['value']}")
    return ", ".join(parts)


def main():
    rfqs = json.loads((ROOT / "data" / "rfqs.json").read_text())
    labels = {l["id"]: l for l in json.loads((ROOT / "data" / "labels.json").read_text())}
    ext_file = json.loads((OUT / "extractions.json").read_text())
    ext = ext_file["extractions"]
    retr = Retriever()
    results = []
    for r in rfqs:
        ex = ext[r["id"]]
        flags = check(r, ex)
        if flags["ready_to_price"]:
            v = {k: ex[k]["value"] for k in ex}
            due = dt.date.fromisoformat(v["delivery_date"]) if v["delivery_date"][:2] == "20" else None
            if due is None:
                from checker import parse_date
                due = parse_date(v["delivery_date"], dt.date.fromisoformat(r["received"]))
            qty = int(v["quantity"].replace(",", ""))
            p = price(r["family"], v["material_grade"], v["dimensions"], v["units"].lower()[:2], v["tolerance"], qty, due,
                      dt.date.fromisoformat(r["received"]))
            draft = {"text": None, "covers_all_missing": None}
        else:
            p = withheld(flags["missing"])
            draft = make_draft(r, flags["missing"])
        sims = retr.top3(r["family"], query_text(r, ex, flags))
        results.append({
            "id": r["id"], "family": r["family"], "received": r["received"], "subject": r["subject"], "body": r["body"],
            "attachments": r["attachments"], "ambiguity": r["ambiguity"], "extraction": ex, "flags": flags,
            "draft": draft, "price": p, "similar_jobs": sims, "truth_missing": labels[r["id"]]["missing"],
        })
        print(r["id"], "ready" if flags["ready_to_price"] else "missing=" + ",".join(flags["missing"]), "|", p["status"], flush=True)
    meta = {"model": ext_file["model"], "prompt_version": ext_file["prompt_version"], "temperature": ext_file["temperature"],
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2", "index": "faiss IndexFlatIP, per family, top-3"}
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")


if __name__ == "__main__":
    main()
