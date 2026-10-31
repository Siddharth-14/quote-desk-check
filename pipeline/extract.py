"""Stage 1: the local model extracts the 8 fields from each RFQ as JSON (temperature 0).

The model only extracts. It never decides readiness: that is pipeline/checker.py.
PROMPT_VERSION is frozen before the first run; any change is a new version and gets reported as such.
Output: data/outputs/extractions.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import MODEL, chat  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_VERSION = "v1"
FIELDS = ["material_grade", "dimensions", "tolerance", "quantity", "finish", "certs", "delivery_date", "units"]

SYSTEM = """You extract quote-request details from a customer email for a metals quote desk.
Return JSON with exactly these 8 keys: material_grade, dimensions, tolerance, quantity, finish, certs, delivery_date, units.
Each key maps to {"value": ..., "evidence": ...}.

Rules:
- value is copied or normalised from what THIS email states. If the email does not state it, value is null and evidence is null. Never guess, never fill in a typical value.
- evidence is an exact quote (a short span copied character-for-character) from the email body that supports the value.
- "Same as last time", "same as PO 1234", "as before" are references to another order, not a value. Use null unless the email also states the actual value.
- Attachment names are listed for context only. A spec that appears only in an attachment name, or "see attached", is not stated in the email. Use null.
- material_grade: material and grade, e.g. "6061-T6", "304 stainless".
- dimensions: the size as written, e.g. "0.5 in x 12 in x 96 in".
- tolerance: the tolerance as written, including "mill standard" if that is what is said.
- quantity: the piece count as digits only, e.g. "250".
- finish: surface condition or coating as written.
- certs: the certification requirement as written. If the email says no certs are needed, value is "none".
- delivery_date: the need-by date as YYYY-MM-DD, using the received date to infer the year. "ASAP" or "rush" is not a date: use null.
- units: "in" or "mm", only if a unit of length is actually written in the email. If dimensions are bare numbers with no unit, use null.
Output JSON only."""


def build_user(rfq):
    att = ", ".join(rfq["attachments"]) if rfq["attachments"] else "none"
    return (
        f"Product family: {rfq['family'].replace('_', ' ')}\n"
        f"Received: {rfq['received']}\n"
        f"Subject: {rfq['subject']}\n"
        f"Attachment names (contents not available): {att}\n\n"
        f"Email body:\n{rfq['body']}"
    )


def field_schema():
    f = {"type": "object", "properties": {"value": {"type": ["string", "null"]}, "evidence": {"type": ["string", "null"]}},
         "required": ["value", "evidence"]}
    return {"type": "object", "properties": {k: f for k in FIELDS}, "required": FIELDS}


def extract_one(rfq):
    raw = chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": build_user(rfq)}],
        temperature=0.0, seed=7, fmt=field_schema(), num_predict=900,
    )
    data = json.loads(raw)
    out = {}
    for k in FIELDS:
        v = data.get(k) or {}
        val, ev = v.get("value"), v.get("evidence")
        val = val.strip() if isinstance(val, str) else val
        ev = ev.strip() if isinstance(ev, str) else ev
        out[k] = {"value": val or None, "evidence": ev or None}
    return out


def main():
    rfqs = json.loads((ROOT / "data" / "rfqs.json").read_text())
    outs = {}
    for r in rfqs:
        outs[r["id"]] = extract_one(r)
        print(r["id"], "ok", flush=True)
    (ROOT / "data" / "outputs").mkdir(exist_ok=True)
    (ROOT / "data" / "outputs" / "extractions.json").write_text(
        json.dumps({"model": MODEL, "prompt_version": PROMPT_VERSION, "temperature": 0, "extractions": outs}, indent=2) + "\n")


if __name__ == "__main__":
    main()
