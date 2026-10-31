"""Data QA for the seed set (`--seed`) and the precomputed outputs (`--outputs`).

Checks: JSON-schema conformance, blanks/placeholders, impossible values, duplicates, id
reconciliation, label-vs-text cross-checks, label-vs-generator-plan drift, class balance.
Exit code 1 if any ERROR is found; WARN/INFO never fail the run.
"""
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIELDS = ["material_grade", "dimensions", "tolerance", "quantity", "finish", "certs", "delivery_date", "units"]
errors, warns, infos = [], [], []


def load(p):
    return json.loads(Path(p).read_text())


SCHEMA = load(DATA / "schema.json")


def validator(name):
    return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]}, format_checker=FormatChecker())


MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}


def find_dates(text):
    out = []
    for m in re.finditer(r"\b(20\d\d)-(\d\d)-(\d\d)\b", text):
        out.append(dt.date(int(m[1]), int(m[2]), int(m[3])))
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b", text):
        out.append(dt.date(int(m[3]), int(m[1]), int(m[2])))
    for m in re.finditer(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})\b", text, re.I):
        out.append(dt.date(2026, MONTHS[m[1].lower()], int(m[2])))
    return out


# independent regex cues used ONLY to cross-check hand labels (not the pipeline's checker)
CUES = {
    "units": re.compile(r"\d\s*(?:in\b|inch|mm\b|ft\b|\")|\b(?:inch|inches|mm)\b", re.I),
    "certs": re.compile(r"\bcerts?\b|certificat|mtr|coc|rohs|3\.1", re.I),
    "quantity": re.compile(r"\b(?:qty|quantity|pieces|pcs)\b|\b\d+\s+(?:pieces|turned|of them)|\bneed \d+|\bfor \d+\b|\b\d+\s+\S+\s+\S*\s*\(turned\)|\d+ (?:grade|turned|pieces)|\d+ pieces", re.I),
    "finish": re.compile(r"finish|surface|condition|anodiz|passivat|black oxide|zinc|nickel|as machined|cold drawn|hot rolled|ground|polish", re.I),
    "tolerance": re.compile(r"toler|tol:|\btol\b|\+/-|±", re.I),
}


def seed():
    rfqs, labels = load(DATA / "rfqs.json"), load(DATA / "labels.json")
    plan = load(DATA / "generation_plan.json")
    v_rfq, v_lab = validator("RFQ"), validator("Label")
    for r in rfqs:
        for e in v_rfq.iter_errors(r):
            errors.append(f"{r.get('id')}: schema: {e.message}")
    for l in labels:
        for e in v_lab.iter_errors(l):
            errors.append(f"{l.get('id')}: label schema: {e.message}")

    ids = [r["id"] for r in rfqs]
    if len(rfqs) != 30:
        errors.append(f"expected 30 RFQs, found {len(rfqs)}")
    if len(set(ids)) != len(ids):
        errors.append("duplicate RFQ ids")
    if sorted(ids) != sorted(l["id"] for l in labels):
        errors.append("RFQ ids and label ids do not match one-to-one")
    bodies = [re.sub(r"\s+", " ", r["body"]).strip().lower() for r in rfqs]
    if len(set(bodies)) != len(bodies):
        errors.append("duplicate email bodies")

    lab = {l["id"]: set(l["missing"]) for l in labels}
    for r in rfqs:
        rid, body = r["id"], r["body"]
        # blanks / template leftovers
        if re.search(r"\[|\]|\{|\}|TODO|lorem|None|null|nan", body):
            errors.append(f"{rid}: placeholder or template leftover in body")
        if not r["subject"].strip():
            errors.append(f"{rid}: blank subject")
        # impossible values
        rec = dt.date.fromisoformat(r["received"])
        if not dt.date(2026, 3, 1) <= rec <= dt.date(2026, 3, 31):
            errors.append(f"{rid}: received date {rec} outside the March 2026 window")
        dates = find_dates(body)
        stated_date = bool(dates)
        for d in dates:
            lead = (d - rec).days
            if lead < 1:
                errors.append(f"{rid}: delivery date {d} is not after received date {rec}")
            elif lead > 60:
                warns.append(f"{rid}: delivery lead time {lead} days is unusually long")
        nums = [float(x) for x in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", body)]
        if any(n <= 0 for n in nums):
            errors.append(f"{rid}: zero or negative number in body")
        # label-vs-text cross-checks (independent heuristics; flag for human review)
        miss = lab[rid]
        if "delivery_date" in miss and stated_date:
            warns.append(f"{rid}: labelled delivery_date missing but a calendar date appears in the text")
        if "delivery_date" not in miss and not stated_date:
            errors.append(f"{rid}: labelled delivery_date present but no calendar date found")
        has_unit = bool(CUES["units"].search(body))
        if "units" in miss and has_unit:
            errors.append(f"{rid}: labelled units missing but a unit token appears")
        if "units" not in miss and not has_unit:
            errors.append(f"{rid}: labelled units present but no unit token found")
        for f in ("certs", "finish", "tolerance"):
            cue = bool(CUES[f].search(body))
            if f in miss and cue:
                rule = "reference-only / attachment-only" if r["ambiguity"] in ("same_as_last_time", "attachment_filename") or "same as" in body.lower() or "attached" in body.lower() else "UNEXPLAINED"
                (infos if rule != "UNEXPLAINED" else warns).append(f"{rid}: {f} labelled missing but text has a cue ({rule})")
            if f not in miss and not cue:
                errors.append(f"{rid}: {f} labelled present but no cue found")
        # attachment-only labels need an attachment or an explicit reference
        if r["ambiguity"] == "attachment_filename" and not miss:
            infos.append(f"{rid}: attachment-filename DECOY (spec repeated in body, nothing missing)")

    # drift: generator plan vs hand label
    drift = []
    for rid in ids:
        planned = set(plan[rid]["intended_missing"])
        if planned != lab[rid]:
            drift.append((rid, sorted(planned), sorted(lab[rid])))
    infos.append(f"label vs generator-plan drift on {len(drift)}/30 RFQs (labels follow the final text): " +
                 "; ".join(f"{a} plan={b} label={c}" for a, b, c in drift))

    # balance
    fam = Counter(r["family"] for r in rfqs)
    amb = Counter(r["ambiguity"] for r in rfqs)
    if not (13 <= fam["service_center"] <= 17 and 13 <= fam["machine_shop"] <= 17):
        errors.append(f"family split is {dict(fam)}, expected each family between 13 and 17")
    if sum(v for k, v in amb.items() if k != "none") != 10:
        errors.append(f"expected 10 ambiguous RFQs, found {dict(amb)}")
    per_field = Counter(f for m in lab.values() for f in m)
    complete = sum(1 for m in lab.values() if not m)
    infos.append(f"families {dict(fam)}; ambiguity {dict(amb)}; complete RFQs {complete}/30; missing-by-field {dict(per_field)}")
    never = [f for f in FIELDS if per_field[f] == 0]
    if never:
        warns.append(f"fields never missing in the labels (recall untestable): {never}")
    thin = [f for f in FIELDS if 0 < per_field[f] < 2]
    if thin:
        warns.append(f"fields missing in only 1 RFQ (very thin evidence): {thin}")
    paraphrased = sum(r["paraphrased"] for r in rfqs)
    infos.append(f"paraphrased by local model: {paraphrased}/30 (rest are template text)")

    # past jobs
    pj_path = DATA / "past_jobs.json"
    if pj_path.exists():
        past_jobs()


def past_jobs():
    jobs = load(DATA / "past_jobs.json")
    if len(jobs) != 80:
        errors.append(f"expected 80 past jobs, found {len(jobs)}")
    if len({j["job_id"] for j in jobs}) != len(jobs):
        errors.append("duplicate past job ids")
    for j in jobs:
        if j["total_price"] <= 0 or j["lead_days"] < 1 or j["qty"] < 1:
            errors.append(f"{j['job_id']}: impossible value (price/lead/qty)")
        if not j["summary"].strip():
            errors.append(f"{j['job_id']}: blank summary")
    infos.append(f"past jobs: {len(jobs)}; price range ${min(j['total_price'] for j in jobs):,.0f} to ${max(j['total_price'] for j in jobs):,.0f}")


def outputs():
    rfqs = {r["id"]: r for r in load(DATA / "rfqs.json")}
    res = load(DATA / "outputs" / "results.json")
    v = validator("Result")
    if len(res) != 30:
        errors.append(f"expected 30 results, found {len(res)}")
    for r in res:
        rid = r["id"]
        for e in v.iter_errors(r):
            errors.append(f"{rid}: result schema: {e.message}")
        if rid not in rfqs:
            errors.append(f"{rid}: result without a source RFQ")
            continue
        if r["body"] != rfqs[rid]["body"]:
            errors.append(f"{rid}: body in results differs from data/rfqs.json")
        fl = r["flags"]
        if set(fl["present"]) | set(fl["missing"]) != set(FIELDS) or set(fl["present"]) & set(fl["missing"]):
            errors.append(f"{rid}: present/missing do not partition the 8 fields")
        if fl["ready_to_price"] != (not fl["missing"]):
            errors.append(f"{rid}: ready_to_price disagrees with the missing list")
        for f, ex in r["extraction"].items():
            if ex["value"] in ("", " "):
                errors.append(f"{rid}: blank-string value in {f} (should be null)")
        p = r["price"]
        if fl["ready_to_price"] and p["status"] == "withheld":
            errors.append(f"{rid}: ready but price withheld")
        if not fl["ready_to_price"] and p["status"] != "withheld":
            errors.append(f"{rid}: not ready but a price was produced")
        if p["status"] == "priced":
            if not p["total"] or p["total"] <= 0 or p["total"] > 500_000:
                errors.append(f"{rid}: implausible total {p['total']}")
            if not p["steps"]:
                errors.append(f"{rid}: priced without a rule trace")
        if not fl["ready_to_price"]:
            if not r["draft"]["text"]:
                errors.append(f"{rid}: incomplete RFQ but no clarification draft")
            elif r["draft"]["covers_all_missing"] is False:
                warns.append(f"{rid}: clarification draft does not mention every missing field")
        if len(r["similar_jobs"]) != 3:
            errors.append(f"{rid}: expected 3 similar jobs, got {len(r['similar_jobs'])}")
        for s in r["similar_jobs"]:
            if not -1 <= s["score"] <= 1:
                errors.append(f"{rid}: similarity score out of range")
    prices = [r["price"]["total"] for r in res if r["price"]["status"] == "priced"]
    if prices:
        infos.append(f"priced {len(prices)}/30; totals ${min(prices):,.0f} to ${max(prices):,.0f}")
    ev = DATA / "outputs" / "eval.json"
    if ev.exists():
        e = load(ev)
        for k, ci in e.get("intervals", {}).items():
            if not (0 <= ci["lo"] <= ci["p"] <= ci["hi"] <= 1):
                errors.append(f"eval interval {k} is not ordered within [0,1]")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--seed"
    seed() if mode == "--seed" else outputs()
    for tag, items in (("ERROR", errors), ("WARN", warns), ("INFO", infos)):
        for i in items:
            print(f"[{tag}] {i}")
    print(f"\n{mode}: {len(errors)} errors, {len(warns)} warnings")
    sys.exit(1 if errors else 0)
