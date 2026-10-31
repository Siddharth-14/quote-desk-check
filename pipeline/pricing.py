"""Plain-Python pricing rules with a printed rule trace. ALL NUMBERS ARE ILLUSTRATIVE, not real prices.

price = weight_lb x base $/lb x grade multiplier x tolerance multiplier x qty break x rush multiplier
Only run for RFQs the checker marks ready_to_price. Finish and certs are not priced in this demo.
"""
import datetime as dt
import math
import re

# keyword -> (density lb/in^3, grade multiplier). First match wins, so order is specific -> general.
GRADES = [
    ("17-4", 0.282, 5.2), ("c360", 0.307, 4.1), ("brass", 0.307, 4.1), ("7075", 0.101, 4.4), ("6061", 0.0975, 2.9),
    ("316", 0.289, 3.9), ("303", 0.289, 3.1), ("304", 0.289, 2.9), ("4140", 0.284, 1.35), ("1215", 0.284, 1.2),
    ("1018", 0.284, 1.15), ("a36", 0.284, 1.0),
]
BASE_PER_LB = {"service_center": 0.90, "machine_shop": 12.00}  # machine shop base includes machining time
QTY_BREAKS = [(500, 0.85), (100, 0.90), (25, 0.94), (10, 0.97), (1, 1.00)]
UNIT_RE = re.compile(r"(\d+(?:\.\d+)?(?:/\d+)?)\s*(mm|cm|ft|feet|inches|inch|in|m)?\b", re.I)
TO_IN = {"in": 1, "inch": 1, "inches": 1, "mm": 1 / 25.4, "cm": 1 / 2.54, "m": 39.3701, "ft": 12, "feet": 12}


def num(s):
    if "/" in s:
        a, b = s.split("/")
        return float(a) / float(b)
    return float(s)


def grade_lookup(text):
    t = text.lower()
    for key, dens, mult in GRADES:
        if key in t:
            return key, dens, mult
    return None


def parse_dims(text, default_unit):
    """Return (shape, [inches...]) or None. Shapes: box (t,w,l) | round (d,l) | tube (od,wall,l)."""
    nums = []
    for m in UNIT_RE.finditer(text):
        unit = (m.group(2) or default_unit).lower()
        nums.append(num(m.group(1)) * TO_IN[unit])
    low = text.lower()
    if "wall" in low and len(nums) >= 3:
        return "tube", nums[:3]
    if re.search(r"\bdia|diameter|\bod\b|round", low) and len(nums) >= 2:
        return "round", nums[:2]
    if len(nums) == 3:
        return "box", nums
    return None


def volume(shape, d):
    if shape == "box":
        return d[0] * d[1] * d[2]
    if shape == "round":
        return math.pi / 4 * d[0] ** 2 * d[1]
    od, wall, ln = d
    return math.pi / 4 * (od ** 2 - (od - 2 * wall) ** 2) * ln


def tol_multiplier(text, family):
    """Tightest numeric tolerance (inches) -> multiplier. 'mill standard' / ASTM -> 1.00."""
    nums = re.findall(r"(?:\+/-|±)\s*(\d+(?:\.\d+)?(?:/\d+)?|\.\d+)\s*(mm)?", text)
    if not nums:
        return 1.00, "no numeric tolerance (standard) -> 1.00"
    vals = [num(n if not n.startswith(".") else "0" + n) / (25.4 if u == "mm" else 1) for n, u in nums]
    t = min(vals)
    for limit, mult in ((0.0011, 1.60), (0.0021, 1.35), (0.0051, 1.15), (0.0101, 1.05)):
        if t <= limit:
            return mult, f"tightest tolerance +/-{t:.4f} in -> {mult:.2f}"
    return 1.00, f"tightest tolerance +/-{t:.4f} in (loose) -> 1.00"


def qty_break(q):
    for floor, mult in QTY_BREAKS:
        if q >= floor:
            return mult, f"{q} pcs -> break at {floor}+ = {mult:.2f}"


def rush_multiplier(received, due):
    days = (due - received).days
    if days < 7:
        return 1.30, f"{days} days to delivery (<7) -> 1.30"
    if days < 14:
        return 1.12, f"{days} days to delivery (7-13) -> 1.12"
    return 1.00, f"{days} days to delivery (14+) -> 1.00"


def price(family, grade_text, dims_text, units, tol_text, qty, due, received):
    """Return a PriceTrace dict. Never raises: unparseable inputs return status 'manual'."""
    steps = []

    def step(name, detail, value):
        steps.append({"step": name, "detail": detail, "value": round(float(value), 4)})

    g = grade_lookup(grade_text)
    if not g:
        return manual(f"Grade '{grade_text}' is not in the rule table.")
    parsed = parse_dims(dims_text, "mm" if units == "mm" else "in")
    if not parsed:
        return manual(f"Could not read a weight out of '{dims_text}'.")
    shape, d = parsed
    vol = volume(shape, d)
    if vol <= 0:
        return manual("Computed volume is zero or negative.")
    key, dens, gmult = g
    step("parse dimensions", f"'{dims_text}' read as {shape} {', '.join(f'{x:.3f}' for x in d)} in", vol)
    step("volume (in^3)", f"{shape} formula", vol)
    wt = vol * dens
    step("piece weight (lb)", f"volume x density {dens} lb/in^3 ({key})", wt)
    base = BASE_PER_LB[family]
    step("base $/lb", f"{family.replace('_', ' ')} base rate (illustrative)", base)
    step("grade multiplier", f"{key}", gmult)
    tm, tdetail = tol_multiplier(tol_text, family)
    step("tolerance multiplier", tdetail, tm)
    qm, qdetail = qty_break(qty)
    step("quantity break", qdetail, qm)
    rm, rdetail = rush_multiplier(received, due)
    step("rush multiplier", rdetail, rm)
    unit = wt * base * gmult * tm * qm * rm
    total = unit * qty
    step("unit price ($)", "weight x base x grade x tolerance x qty break x rush", unit)
    step("total ($)", f"unit price x {qty} pcs", total)
    return {"status": "priced", "note": "Illustrative rule-based price, not a real quote. Finish and certs are not priced.",
            "steps": steps, "unit_price": round(unit, 2), "total": round(total, 2)}


def manual(note):
    return {"status": "manual", "note": note + " Needs a human.", "steps": [], "unit_price": None, "total": None}


def withheld(missing):
    return {"status": "withheld", "note": "Pricing withheld: required fields missing (" + ", ".join(missing) + "). Ask the customer first.",
            "steps": [], "unit_price": None, "total": None}


def print_trace(trace):
    for s in trace["steps"]:
        print(f"  {s['step']:<22} {s['value']:>12,.4f}   {s['detail']}")
