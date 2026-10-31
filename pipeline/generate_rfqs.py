"""Generate 30 synthetic RFQ emails with controlled omissions.

Stage 1: deterministic templates (seeded). Stage 2: local-model paraphrase for natural noise,
guarded so numbers cannot change and, in units-missing cases, no unit words can leak in.

Outputs:
  data/rfqs.json             the 30 RFQ emails (schema: RFQ)
  data/generation_plan.json  what the generator intended to omit. NOT the label set:
                             labels are written by hand from the final text (data/labels.json).
Usage: python pipeline/generate_rfqs.py [--no-paraphrase]
"""
import datetime as dt
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import chat  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260314

FIELDS = ["material_grade", "dimensions", "tolerance", "quantity", "finish", "certs", "delivery_date", "units"]

# ---- catalogs (all invented) -------------------------------------------------------------------
SC_ITEMS = [
    {"form": "plate", "grade": "A36", "finish": ["hot rolled", "hot rolled, pickled and oiled"]},
    {"form": "plate", "grade": "304 stainless", "finish": ["No.1 hot rolled annealed", "mill finish"]},
    {"form": "plate", "grade": "6061-T651", "finish": ["mill finish"]},
    {"form": "plate", "grade": "7075-T651", "finish": ["mill finish"]},
    {"form": "round_bar", "grade": "1018 CF", "finish": ["cold drawn"]},
    {"form": "round_bar", "grade": "4140 annealed", "finish": ["hot rolled", "turned and polished"]},
    {"form": "round_bar", "grade": "304/304L", "finish": ["cold finished", "centerless ground"]},
    {"form": "round_bar", "grade": "C360 brass", "finish": ["cold drawn"]},
    {"form": "tube", "grade": "316L", "finish": ["pickled", "mill finish"]},
    {"form": "tube", "grade": "6061-T6", "finish": ["mill finish"]},
    {"form": "flat", "grade": "6061-T6", "finish": ["mill finish"]},
    {"form": "flat", "grade": "A36", "finish": ["hot rolled"]},
]
MS_ITEMS = [
    {"form": "turned", "grade": "303 stainless", "finish": ["passivate per ASTM A967", "black oxide", "as machined"]},
    {"form": "turned", "grade": "316 stainless", "finish": ["passivate per ASTM A967", "electropolish"]},
    {"form": "turned", "grade": "4140 pre-hard", "finish": ["black oxide", "zinc plate", "as machined"]},
    {"form": "turned", "grade": "6061-T6", "finish": ["clear anodize Type II", "black anodize Type II", "as machined"]},
    {"form": "turned", "grade": "C360 brass", "finish": ["as machined", "nickel plate"]},
    {"form": "turned", "grade": "1215 steel", "finish": ["zinc plate", "as machined"]},
    {"form": "turned", "grade": "17-4 PH", "finish": ["passivate per ASTM A967", "as machined"]},
    {"form": "turned", "grade": "7075-T6", "finish": ["clear anodize Type II", "as machined"]},
]
PART_NOUNS = ["shafts", "bushings", "spacers", "pins", "fitting blanks", "standoffs", "sleeves", "adapter pins"]
SC_TOL = ["cut length +/- 1/16 in", "+/- 0.03 in on length", "mill standard tolerance", "thickness per ASTM A6, length +/- 1/8 in"]
SC_TOL_BARE = ["mill standard tolerance", "standard mill tolerance", "cut length +/- 1/16"]
SC_TOL_MM = ["cut length +/- 1.5 mm", "mill standard tolerance", "+/- 1 mm on length"]
MS_TOL = ["+/- 0.005 in on all diameters", "+/- 0.002 in on OD", "+/- 0.010 in general", "+/- 0.001 in on the bearing journal"]
MS_TOL_BARE = ["+/- 0.005 on all diameters", "+/- 0.002 on OD", "+/- 0.010 general"]
MS_TOL_MM = ["+/- 0.05 mm on OD", "+/- 0.1 mm general", "+/- 0.025 mm on the bearing journal"]
SC_CERTS = ["MTR required", "EN 10204 3.1 cert with each heat", "no certs needed", "certified MTRs please"]
MS_CERTS = ["CoC and material cert", "RoHS cert plus CoC", "no certs needed", "full material cert and CoC"]
COMPANIES = [
    ("Harlan Fabrication", "Dana Whitfield"), ("Bright Valley Machinery", "Ravi Menon"),
    ("Corrigan Hydraulics", "Joel Prins"), ("Northfield Conveyor Co", "Mei-Lin Ortega"),
    ("Tallgrass Equipment", "Sam Okafor"), ("Redwater Pump Works", "Greta Lindqvist"),
    ("Pinecrest Automation", "Tom Barlow"), ("Ashby Trailer & Body", "Nadia Haddad"),
    ("Kestrel Tooling", "Luis Ferreira"), ("Marlow Packaging Systems", "Hannah Doyle"),
    ("Stonebridge Mining Supply", "Pete Kowalczyk"), ("Cedar Point Fabricators", "Aisha Rahman"),
]
GENERIC_ATTACH = ["PO_draft.pdf", "site_photo.jpg", "sketch_rev1.png", "contact_list.xlsx"]

# ---- the 30-RFQ plan: omissions are chosen, not random -----------------------------------------
# (family, omit, ambiguity, ambiguity_fields, metric, delivery_mode)
PLAN = [
    ("service_center", [], "none", [], False, "date"),
    ("service_center", ["tolerance"], "none", [], False, "date"),
    ("service_center", ["certs"], "none", [], False, "date"),
    ("service_center", [], "none", [], False, "date"),
    ("service_center", ["delivery_date"], "none", [], False, "asap"),
    ("service_center", ["quantity"], "none", [], False, "date"),
    ("service_center", [], "none", [], False, "date"),
    ("service_center", ["material_grade"], "none", [], False, "date"),
    ("machine_shop", [], "none", [], False, "date"),
    ("machine_shop", ["tolerance"], "none", [], False, "date"),
    ("machine_shop", ["finish", "certs"], "none", [], False, "date"),
    ("machine_shop", [], "none", [], False, "date"),
    ("machine_shop", ["delivery_date"], "none", [], False, "asap"),
    ("machine_shop", ["quantity"], "none", [], False, "date"),
    ("machine_shop", [], "none", [], False, "date"),
    ("machine_shop", [], "none", [], True, "date"),
    ("machine_shop", ["dimensions"], "none", [], False, "date"),
    ("service_center", ["tolerance", "delivery_date"], "none", [], False, "none"),
    ("service_center", [], "none", [], True, "date"),
    ("machine_shop", [], "none", [], False, "date"),
    # 10 ambiguous
    ("service_center", ["units"], "units_missing", [], False, "date"),
    ("service_center", ["units", "certs"], "units_missing", [], False, "date"),
    ("machine_shop", ["units"], "units_missing", [], False, "date"),
    ("machine_shop", ["units", "finish"], "units_missing", [], False, "date"),
    ("service_center", ["material_grade"], "same_as_last_time", ["material_grade"], False, "date"),
    ("machine_shop", ["finish", "certs"], "same_as_last_time", ["finish", "certs"], False, "date"),
    ("machine_shop", [], "same_as_last_time", ["finish_decoy"], False, "date"),
    ("service_center", ["material_grade", "finish"], "attachment_filename", ["material_grade", "finish"], False, "date"),
    ("machine_shop", ["material_grade", "tolerance"], "attachment_filename", ["material_grade", "tolerance"], False, "date"),
    ("machine_shop", [], "attachment_filename", ["decoy"], False, "date"),
]


def num(x):
    return f"{x:g}"


def gen_dims(rng, form, metric, bare):
    """Return (dimension string, anchor numbers)."""
    if metric:
        if form == "plate":
            t, w, l = rng.choice([6, 10, 12, 20]), rng.choice([300, 600, 1000]), rng.choice([1000, 2000, 3000])
            return f"{t} x {w} x {l} mm", [num(t), num(w), num(l)]
        if form == "flat":
            t, w, l = rng.choice([6, 10, 12]), rng.choice([25, 40, 50, 75]), rng.choice([3000, 6000])
            return f"{t} mm x {w} mm x {l} mm", [num(t), num(w), num(l)]
        if form == "round_bar":
            d, l = rng.choice([12, 20, 25, 40, 50]), rng.choice([3000, 6000])
            return f"{d} mm dia x {l} mm long", [num(d), num(l)]
        if form == "tube":
            od, wall, l = rng.choice([25, 40, 60]), rng.choice([2, 3, 4]), 6000
            return f"{od} mm OD x {wall} mm wall x {l} mm", [num(od), num(wall), num(l)]
        od, l = rng.choice([10, 12, 20, 30]), rng.choice([25, 40, 60, 100])
        return f"{od} mm OD x {l} mm long", [num(od), num(l)]
    if form == "plate":
        t, w, l = rng.choice([0.25, 0.375, 0.5, 0.75, 1.0]), rng.choice([12, 24, 36, 48]), rng.choice([48, 96, 120])
        return (f"{num(t)} x {w} x {l}" if bare else f"{num(t)} in x {w} in x {l} in"), [num(t), num(w), num(l)]
    if form == "flat":
        t, w = rng.choice([0.25, 0.5, 0.75]), rng.choice([1, 1.5, 2, 3, 4])
        if bare:
            return f"{num(t)} x {num(w)} x 240", [num(t), num(w), "240"]
        return f"{num(t)} in x {num(w)} in x 20 ft", [num(t), num(w), "20"]
    if form == "round_bar":
        d = rng.choice([0.5, 0.75, 1, 1.25, 1.5, 2, 3])
        if bare:
            return f"{num(d)} dia x 144 long", [num(d), "144"]
        l = rng.choice([10, 12])
        return f"{num(d)} in dia x {l} ft", [num(d), str(l)]
    if form == "tube":
        od, wall = rng.choice([1, 1.5, 2, 3]), rng.choice([0.083, 0.125, 0.188, 0.25])
        if bare:
            return f"{num(od)} OD x {num(wall)} wall x 240", [num(od), num(wall), "240"]
        return f"{num(od)} in OD x {num(wall)} in wall x 20 ft", [num(od), num(wall), "20"]
    od, l = rng.choice([0.375, 0.5, 0.75, 1, 1.25, 1.5, 2]), rng.choice([1, 1.5, 2, 3.5, 4, 6])
    if bare:
        return f"{num(od)} OD x {num(l)} long", [num(od), num(l)]
    return f"{num(od)} in OD x {num(l)} in long", [num(od), num(l)]


def fmt_date(rng, d):
    style = rng.randrange(4)
    mon = d.strftime("%B")
    if style == 0:
        return f"{mon} {d.day}", [mon, str(d.day)]
    if style == 1:
        return d.isoformat(), [d.isoformat()]
    if style == 2:
        return f"{d.month}/{d.day}/{d.year}", [f"{d.month}/{d.day}/{d.year}"]
    return f"{d.strftime('%A')} {mon} {d.day}", [mon, str(d.day)]


def build_rfq(idx, plan, rng, used):
    family, omit, amb, amb_fields, metric, dmode = plan
    bare = "units" in omit
    items = SC_ITEMS if family == "service_center" else MS_ITEMS
    for _ in range(50):
        item = rng.choice(items)
        dims, d_anchors = gen_dims(rng, item["form"], metric, bare)
        if (item["grade"], dims) not in used:
            used.add((item["grade"], dims))
            break
    finish = rng.choice(item["finish"])
    received = dt.date(2026, 3, 2) + dt.timedelta(days=rng.randrange(0, 26))
    lead = rng.choice([4, 9, 14, 21, 28, 35])
    due = received + dt.timedelta(days=lead)
    date_str, date_anchors = fmt_date(rng, due)
    if family == "service_center":
        qty = rng.choice([4, 6, 10, 12, 20, 25, 40, 60])
        tol = rng.choice(SC_TOL_MM if metric else (SC_TOL_BARE if bare else SC_TOL))
        cert = rng.choice(SC_CERTS)
    else:
        qty = rng.choice([25, 50, 100, 150, 250, 500, 1000])
        tol = rng.choice(MS_TOL_MM if metric else (MS_TOL_BARE if bare else MS_TOL))
        cert = rng.choice(MS_CERTS)
    company, person = COMPANIES[idx % len(COMPANIES)]
    noun = rng.choice(PART_NOUNS) if family == "machine_shop" else None
    attachments = []
    absent_by_ambiguity = set()

    # value phrases: (phrase, anchors) for each *stated* field
    stated = {}
    stated["material_grade"] = (item["grade"], [item["grade"]])
    stated["dimensions"] = (dims, d_anchors)
    stated["tolerance"] = (tol, [])
    stated["quantity"] = (f"{qty}", [str(qty)])
    stated["finish"] = (finish, [finish])
    stated["certs"] = (cert, [])
    stated["delivery_date"] = (date_str, date_anchors)

    lines_order = ["material_grade", "dimensions", "quantity", "tolerance", "finish", "certs", "delivery_date"]
    labels = {
        "material_grade": ["Material", "Grade", "Alloy"], "dimensions": ["Size", "Dimensions", "Stock size"],
        "quantity": ["Qty", "Quantity", "Pieces"], "tolerance": ["Tolerance", "Tolerances", "Tol"],
        "finish": ["Finish", "Surface", "Condition"], "certs": ["Certs", "Certification", "Paperwork"],
        "delivery_date": ["Need by", "Delivery", "Required date"],
    }
    text_override = {}

    # ambiguity handling
    if amb == "same_as_last_time":
        for f in amb_fields:
            if f == "finish_decoy":
                text_override["finish"] = f"same as last time ({finish})"
            else:
                text_override[f] = rng.choice(["same as last time", "same as our last order", "same as PO 4471"])
                absent_by_ambiguity.add(f)
    if amb == "attachment_filename":
        slug = lambda s: re.sub(r"[^A-Za-z0-9]+", "", s)
        if amb_fields == ["decoy"]:
            attachments.append(f"{slug(item['grade'])}_{slug(finish)}_spec_rev2.pdf")
        else:
            parts = []
            if "material_grade" in amb_fields:
                parts.append(slug(item["grade"]))
            if "finish" in amb_fields:
                parts.append(slug(finish))
            if "tolerance" in amb_fields:
                t = re.search(r"[0-9.]+", tol)
                parts.append("tol" + (t.group(0).replace(".", "p") if t else "tight"))
            attachments.append("_".join(parts) + "_spec_sheet_rev3.pdf")
            for f in amb_fields:
                absent_by_ambiguity.add(f)
    if rng.random() < 0.3 and not attachments:
        attachments.append(rng.choice(GENERIC_ATTACH))

    present = [f for f in lines_order if f not in omit and f not in absent_by_ambiguity]
    # build lines
    style = rng.choice(["bullets", "prose", "terse"])
    asap = dmode == "asap"
    ref_lines = []
    spec_lines = []
    for f in lines_order:
        if f in text_override:
            spec_lines.append((f, text_override[f]))
            continue
        if f == "delivery_date" and asap:
            spec_lines.append((f, rng.choice(["need it ASAP", "rush, as soon as you can"])))
            continue
        if f in omit:
            continue
        if f in absent_by_ambiguity:
            continue
        spec_lines.append((f, stated[f][0]))
    spec_lines = [(f, v) for f, v in spec_lines]
    if amb == "attachment_filename" and amb_fields != ["decoy"]:
        spec_lines.append(("note", rng.choice(["rest of the spec is in the attached", "see attached for the spec details", "spec sheet attached"])))

    what = f"{noun} (turned)" if noun else "stock"
    intro = rng.choice([
        f"Can you quote the following {what}?", f"Looking for pricing on {what}.", f"Please quote {what} per below.",
    ])
    if style == "bullets":
        body = "Hi,\n\n" + intro + "\n\n"
        for f, v in spec_lines:
            body += (f"- {rng.choice(labels[f])}: {v}\n" if f != "note" else f"- Note: {v}\n")
        body += f"\nThanks,\n{person}\n{company}"
    elif style == "terse":
        body = intro + "\n"
        body += "; ".join((f"{v}" if f in ("note",) else f"{rng.choice(labels[f]).lower()} {v}") for f, v in spec_lines)
        body += f".\n\n{person}, {company}"
    else:
        sentences = []
        for f, v in spec_lines:
            sentences.append(v if f == "note" else f"{rng.choice(labels[f])}: {v}.")
        body = f"Hello,\n\n{intro} " + " ".join(sentences) + f"\n\nRegards,\n{person}\n{company}"
    subject = rng.choice(["Quote request", "RFQ - need pricing", "Price and lead time please",
                          "Quote on turned parts" if family == "machine_shop" else f"Quote on {item['form'].replace('_', ' ')}"])
    anchors = []
    for f in present:
        anchors.extend([[a] for a in stated[f][1]])
    if "tolerance" in present:
        m = re.search(r"\d+(?:\.\d+)?(?:/\d+)?", tol)
        anchors.append([m.group(0)] if m else ["mill standard", "standard mill"])
    if "certs" in present:
        low = cert.lower()
        anchors.append(["no cert"] if "no cert" in low else
                       ["mtr"] if "mtr" in low else ["3.1"] if "3.1" in low else ["rohs"] if "rohs" in low else ["coc", "material cert"])
    if "same_as_last_time" == amb:
        for f in amb_fields:
            if f != "finish_decoy":
                anchors.append(["same as", "last time", "last order", "po 4471"])
    needs_units = (not bare) and ("units" not in omit) and ("dimensions" not in omit)
    return {
        "rfq": {"family": family, "received": received.isoformat(), "subject": subject, "body": body,
                "attachments": attachments, "ambiguity": amb, "paraphrased": False},
        "plan": {"intended_missing": sorted(set(omit) | absent_by_ambiguity), "anchors": anchors, "bare_units": bare,
                 "needs_units": needs_units, "item": item["grade"], "dims": dims, "company": company, "person": person},
    }


NUM_RE = re.compile(r"\d+(?:\.\d+)?")
UNIT_PRESENT = re.compile(r"\d\s*(?:in\b|inch|mm\b|ft\b|\")|\b(?:inch|inches|mm)\b", re.I)
UNIT_LEAK = re.compile(r"\d\s*(?:in\b|inch|inches|mm\b|ft\b|feet|cm\b|\")|\b(?:inch|inches|millimet\w+|millimeters)\b", re.I)


def paraphrase(rfq, plan, rng_seed):
    """Local-model paraphrase. Returns new body or None if guards reject every attempt."""
    orig_nums = set(NUM_RE.findall(rfq["body"]))
    system = (
        "You rewrite short purchasing emails so they sound like a real person typed them. "
        "The email is written BY a customer TO a supplier, asking the supplier for a quote. "
        "You are NOT the supplier: never answer, never say 'here is the quote'. "
        "Keep EVERY fact exactly: every number, unit, grade, date, filename and requirement. "
        "Do not add any new specification, number, unit, deadline or certificate. "
        "If something is not mentioned in the original, do not mention it. "
        "Do not convert units. Do not greet anyone by name (start with Hi, or Hello,). "
        "Keep the sign-off name and company exactly as in the original. Keep it short. Output only the email text."
    )
    for attempt in range(8):
        out = chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": "Rewrite this email in a natural, slightly informal voice:\n\n" + rfq["body"]}],
            temperature=0.7, seed=rng_seed + attempt, num_predict=500,
        ).strip()
        low = out.lower()
        if "[" in out or re.match(r"(sure|certainly|of course|absolutely|here)\b", low) or "quote for the" in low and "here" in low:
            continue
        if re.match(r"(hi|hello|hey)\s+[a-z]+[,!]", low) and not re.match(r"(hi|hello|hey) there", low):
            continue
        if plan["company"].lower() not in low or plan["person"].split()[0].lower() not in low:
            continue
        if any(not any(a.lower() in low for a in group) for group in plan["anchors"]):
            continue
        if plan["needs_units"] and not UNIT_PRESENT.search(out):
            continue
        if not set(NUM_RE.findall(out)) <= orig_nums:
            continue
        if plan["bare_units"] and UNIT_LEAK.search(out):
            continue
        if rfq["ambiguity"] == "same_as_last_time" and not re.search(r"last (time|order)|PO 4471|same as", out, re.I):
            continue
        if rfq["attachments"] and not all(a.lower() in low for a in rfq["attachments"] if "spec" in a):
            continue
        if re.search(r"\b(asap|rush|as soon as)\b", rfq["body"], re.I) and not re.search(r"asap|rush|soon", low):
            continue
        return out
    return None


def main():
    do_para = "--no-paraphrase" not in sys.argv
    rng = random.Random(SEED)
    used = set()
    built = [build_rfq(i, p, rng, used) for i, p in enumerate(PLAN)]
    order = list(range(len(built)))
    random.Random(SEED + 1).shuffle(order)  # ambiguous ones are not clustered at the end
    rfqs, plans = [], {}
    for new_i, old_i in enumerate(order, start=1):
        b = built[old_i]
        rid = f"RFQ-{new_i:03d}"
        rfq = {"id": rid, **b["rfq"]}
        if do_para:
            new = paraphrase(rfq, b["plan"], SEED + new_i * 10)
            if new:
                rfq["body"], rfq["paraphrased"] = new, True
            print(rid, "paraphrased" if new else "template-fallback", flush=True)
        rfqs.append(rfq)
        plans[rid] = {"intended_missing": b["plan"]["intended_missing"], "ambiguity": rfq["ambiguity"],
                      "item": b["plan"]["item"], "dims": b["plan"]["dims"]}
    (ROOT / "data" / "rfqs.json").write_text(json.dumps(rfqs, indent=2) + "\n")
    (ROOT / "data" / "generation_plan.json").write_text(json.dumps(plans, indent=2) + "\n")
    print(f"wrote {len(rfqs)} RFQs; paraphrased={sum(r['paraphrased'] for r in rfqs)}")


if __name__ == "__main__":
    main()
