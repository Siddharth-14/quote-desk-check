"""Stage 2: deterministic checker. Sets `missing` and `ready_to_price`. No model involved.

A field counts as present only if ALL hold:
  1. the model returned a non-blank value;
  2. the value is not itself a reference to another order ("same as last time");
  3. the evidence quote exists verbatim (whitespace/case-insensitive) in the email subject or body
     (so attachment filenames and invented quotes do not count);
  4. the value passes a light format check for that field.
"""
import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE = json.loads((ROOT / "data" / "required_fields.json").read_text())
FIELDS = TABLE["fields"]

REF_RE = re.compile(r"same as|as before|last (time|order)|previous order|prior order|\bPO\s*#?\d+", re.I)
UNIT_RE = re.compile(r"\d\s*(?:in\b|inch|mm\b|ft\b|\")|\b(?:inch|inches|mm|millimet\w+)\b", re.I)
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def parse_date(value, received):
    """Return a date or None. Accepts ISO, m/d/yyyy, 'April 18', or 'in N days/weeks'."""
    v = value.strip()
    m = re.fullmatch(r"(20\d\d)-(\d\d)-(\d\d)", v)
    try:
        if m:
            return dt.date(int(m[1]), int(m[2]), int(m[3]))
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(20\d\d)", v)
        if m:
            return dt.date(int(m[3]), int(m[1]), int(m[2]))
        m = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2})", v, re.I)
        if m:
            return dt.date(received.year, MONTHS.index(m[1].lower()) + 1, int(m[2]))
        m = re.search(r"(\d+)\s*(day|week)s?", v, re.I)
        if m:
            return received + dt.timedelta(days=int(m[1]) * (7 if m[2].lower() == "week" else 1))
    except ValueError:
        return None
    return None


def check_field(field, ex, haystack, received):
    """Return None if present, else a reason string."""
    val, ev = ex.get("value"), ex.get("evidence")
    if not val or not str(val).strip():
        return "model returned no value"
    val = str(val).strip()
    if REF_RE.search(val):
        return "value is a reference to another order, not a stated spec"
    if not ev or norm(ev) not in haystack:
        return "evidence quote not found in the email body"
    if field == "quantity":
        if not re.fullmatch(r"\d{1,6}", val.replace(",", "")) or int(val.replace(",", "")) < 1:
            return "quantity is not a positive integer"
    elif field == "delivery_date":
        d = parse_date(val, received)
        if d is None:
            return "delivery date is not a calendar date"
        if d <= received:
            return "delivery date is not after the received date"
    elif field == "units":
        if val.lower() not in ("in", "inch", "inches", "mm", "millimeters", "millimetres"):
            return "units value is not in/mm"
        if not UNIT_RE.search(ev):
            return "units evidence quote contains no unit token"
    elif field == "dimensions":
        if not re.search(r"\d", val):
            return "dimensions contain no number"
    elif field == "tolerance":
        if not re.search(r"\d|standard|commercial|astm|per mill", val, re.I):
            return "tolerance has no number or standard"
    return None


def check(rfq, extraction):
    haystack = norm(rfq["subject"] + " " + rfq["body"])
    received = dt.date.fromisoformat(rfq["received"])
    present, missing, reasons = [], [], {}
    for f in FIELDS:
        why = check_field(f, extraction.get(f, {}), haystack, received)
        if why is None:
            present.append(f)
        else:
            missing.append(f)
            reasons[f] = why
    return {"present": present, "missing": missing, "reasons": reasons, "ready_to_price": not missing}
