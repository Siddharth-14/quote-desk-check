"""Eval: score the checker's missing-spec flags against the hand labels.

Unit of analysis
  field decision : one (RFQ, required field) pair; 30 x 8 = 240. Positive class = "field is missing".
  RFQ decision   : ready_to_price true/false vs. "no required field is truly missing"; n = 30.
Intervals
  Wilson 95% for every proportion. The 240 field decisions come from only 30 emails, so they are
  clustered; for field accuracy we also report a cluster bootstrap (resample RFQs) interval.
Ablation
  naive    : a field is present if the model returned any non-null value
  evidence : naive + the evidence quote must appear in the email body
  checker  : full deterministic checker (adds reference-to-prior-order, format, unit-token rules)
Outputs: data/outputs/eval.json, eval/report.md
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from checker import FIELDS, check, norm  # noqa: E402

Z = 1.959964


def wilson(k, n):
    if n == 0:
        return {"k": k, "n": n, "p": None, "lo": None, "hi": None}
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return {"k": k, "n": n, "p": round(p, 4), "lo": round(max(0.0, c - h), 4), "hi": round(min(1.0, c + h), 4)}


def sign_test_p(b, c):
    """Exact two-sided binomial sign test on discordant pairs (b vs c)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def main():
    rfqs = json.loads((ROOT / "data" / "rfqs.json").read_text())
    labels = {l["id"]: set(l["missing"]) for l in json.loads((ROOT / "data" / "labels.json").read_text())}
    ext_file = json.loads((ROOT / "data" / "outputs" / "extractions.json").read_text())
    ext = ext_file["extractions"]

    variants = {"naive": {}, "evidence": {}, "checker": {}}
    for r in rfqs:
        e = ext[r["id"]]
        hay = norm(r["subject"] + " " + r["body"])
        variants["naive"][r["id"]] = {f for f in FIELDS if not e[f]["value"]}
        variants["evidence"][r["id"]] = {f for f in FIELDS if not e[f]["value"] or not e[f]["evidence"] or norm(e[f]["evidence"]) not in hay}
        variants["checker"][r["id"]] = set(check(r, e)["missing"])

    out = {"model": ext_file["model"], "prompt_version": ext_file["prompt_version"], "n_rfqs": len(rfqs),
           "n_field_decisions": len(rfqs) * len(FIELDS), "variants": {}}
    for name, flagged in variants.items():
        tp = sum(len(flagged[i] & labels[i]) for i in labels)
        fp = sum(len(flagged[i] - labels[i]) for i in labels)
        fn = sum(len(labels[i] - flagged[i]) for i in labels)
        tn = out["n_field_decisions"] - tp - fp - fn
        incomplete = [i for i in labels if labels[i]]
        cw = [i for i in labels if not flagged[i] and labels[i]]  # ready_to_price true while a field is truly missing
        ready = [i for i in labels if not flagged[i]]
        blocked_complete = [i for i in labels if flagged[i] and not labels[i]]
        exact = sum(flagged[i] == labels[i] for i in labels)
        out["variants"][name] = {
            "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "field_accuracy": wilson(tp + tn, out["n_field_decisions"]),
            "missing_precision": wilson(tp, tp + fp),
            "missing_recall": wilson(tp, tp + fn),
            "rfq_exact_match": wilson(exact, len(labels)),
            "confidently_wrong": wilson(len(cw), len(labels)),
            "confidently_wrong_of_ready": wilson(len(cw), len(ready)),
            "incomplete_rfqs_caught": wilson(len(incomplete) - len(cw), len(incomplete)),
            "complete_rfqs_wrongly_blocked": wilson(len(blocked_complete), len(labels) - len(incomplete)),
            "confidently_wrong_ids": cw,
            "ready_ids": ready,
        }

    # cluster bootstrap for field accuracy (checker), resampling RFQs
    ids = sorted(labels)
    correct = np.array([8 - len(variants["checker"][i] ^ labels[i]) for i in ids])
    rng = np.random.default_rng(20260314)
    boots = [correct[rng.integers(0, len(ids), len(ids))].sum() / (8 * len(ids)) for _ in range(10000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    out["variants"]["checker"]["field_accuracy_cluster_bootstrap"] = {"p": round(correct.sum() / 240, 4), "lo": round(float(lo), 4), "hi": round(float(hi), 4)}

    # paired comparison: naive vs checker on confidently-wrong RFQs
    cw_naive = set(out["variants"]["naive"]["confidently_wrong_ids"])
    cw_check = set(out["variants"]["checker"]["confidently_wrong_ids"])
    b, c = len(cw_naive - cw_check), len(cw_check - cw_naive)
    out["paired_naive_vs_checker"] = {"naive_only_wrong": b, "checker_only_wrong": c, "exact_sign_test_p": round(sign_test_p(b, c), 4)}

    # per-field and per-ambiguity descriptives (no tests: segments are tiny)
    pf = {}
    for f in FIELDS:
        truly = [i for i in labels if f in labels[i]]
        got = [i for i in truly if f in variants["checker"][i]]
        fps = [i for i in labels if f not in labels[i] and f in variants["checker"][i]]
        pf[f] = {"truly_missing": len(truly), "caught": len(got), "false_flags": len(fps)}
    out["per_field"] = pf
    amb = {}
    for r in rfqs:
        a = amb.setdefault(r["ambiguity"], {"n": 0, "exact": 0})
        a["n"] += 1
        a["exact"] += variants["checker"][r["id"]] == labels[r["id"]]
    out["per_ambiguity"] = amb

    # failure examples: (1) model-alone errors the checker rescued, (2) residual end-to-end errors
    rescued, residual = [], []
    for r in rfqs:
        i, e = r["id"], ext[r["id"]]
        flags = check(r, e)
        for f in FIELDS:
            if f in labels[i] and f not in variants["naive"][i]:
                rescued.append({"id": i, "field": f, "model_value": e[f]["value"], "model_evidence": e[f]["evidence"],
                                "checker_reason": flags["reasons"].get(f), "truth": "missing"})
            if (f in variants["checker"][i]) != (f in labels[i]):
                residual.append({"id": i, "field": f, "model_value": e[f]["value"], "model_evidence": e[f]["evidence"],
                                 "checker_reason": flags["reasons"].get(f), "truth": "missing" if f in labels[i] else "present"})
    out["failures"] = {"rescued_by_checker": rescued, "residual": residual}

    v = out["variants"]
    for x in rescued:
        x["other_gaps_still_flagged_by_naive"] = sorted(labels[x["id"]] - {x["field"]})
    unit_cases = [x["id"] for x in rescued if x["field"] == "units"]
    ref_cases = [x["id"] for x in rescued if x["field"] != "units"]
    masked = [x["id"] for x in rescued if x["other_gaps_still_flagged_by_naive"]]
    nv, ck = v["naive"], v["checker"]
    out["failure_mode"] = {
        "title": "The model fills in details it cannot see",
        "summary": (f"Left alone, the 7B model made {len(rescued)} field-level mistakes of one kind: it stated a detail the email "
                    f"does not contain. Given bare numbers such as '0.5 x 12 x 96' it answered units='in' and quoted the dimension string "
                    f"as evidence ({len(unit_cases)} RFQs). It also accepted 'same as PO 4471' as a certs value ({len(ref_cases)} RFQ). "
                    f"The checker rejects both patterns (a units value needs a quote containing a unit token; a reference to another "
                    f"order is not a value), lifting missing-spec recall from {nv['missing_recall']['k']}/{nv['missing_recall']['n']} to "
                    f"{ck['missing_recall']['k']}/{ck['missing_recall']['n']}. At the RFQ level the naive rule was NOT confidently wrong on "
                    f"this set ({nv['confidently_wrong']['k']}/30, same as the checker): all {len(masked)} of these RFQs also had a second, "
                    f"genuine gap that the model did flag, so they were blocked anyway. That is luck of the sample. Had units or the "
                    f"cert reference been the only gap, the RFQ would have gone to pricing (counterfactual, not observed here)."),
        "examples": rescued,
        "residual_note": ("The one remaining error is the reverse: on RFQ-014 the model returned no units even though the "
                          "tolerance reads '+/- 0.001 in'. The checker flags units as missing, which costs one needless "
                          "clarification question. That RFQ was already correctly blocked (dimensions are missing), and whether "
                          "'in' in a tolerance counts as stating units is itself a labelling-policy judgement call."),
    }
    out["intervals"] = {
        "field_accuracy": v["checker"]["field_accuracy"], "missing_precision": v["checker"]["missing_precision"],
        "missing_recall": v["checker"]["missing_recall"], "confidently_wrong": v["checker"]["confidently_wrong"],
        "incomplete_rfqs_caught": v["checker"]["incomplete_rfqs_caught"], "rfq_exact_match": v["checker"]["rfq_exact_match"],
    }
    (ROOT / "data" / "outputs" / "eval.json").write_text(json.dumps(out, indent=2) + "\n")
    write_report(out)
    print(json.dumps({k: out["variants"]["checker"][k] for k in ("confusion", "field_accuracy", "missing_precision", "missing_recall", "confidently_wrong", "incomplete_rfqs_caught")}, indent=1))
    print("naive CW:", v["naive"]["confidently_wrong"], "evidence CW:", v["evidence"]["confidently_wrong"])
    print("paired:", out["paired_naive_vs_checker"])
    print("bootstrap:", v["checker"]["field_accuracy_cluster_bootstrap"])
    print("rescued:", [(x['id'], x['field']) for x in rescued], "residual:", [(x['id'], x['field']) for x in residual])


def pct(w):
    return f"{w['p'] * 100:.1f}% ({w['k']}/{w['n']}), 95% CI {w['lo'] * 100:.1f}-{w['hi'] * 100:.1f}%"


def write_report(o):
    v = o["variants"]
    c = v["checker"]
    lines = [
        "# Eval report", "",
        f"Model `{o['model']}`, prompt `{o['prompt_version']}`, temperature 0. n = {o['n_rfqs']} synthetic RFQs, {o['n_field_decisions']} field decisions.",
        "Labels: single labeller, written before the model ran. Intervals: Wilson 95%.", "",
        "## Headline (full checker)", "",
        f"- Field accuracy: {pct(c['field_accuracy'])}; cluster-bootstrap (resampling RFQs) {c['field_accuracy_cluster_bootstrap']['lo'] * 100:.1f}-{c['field_accuracy_cluster_bootstrap']['hi'] * 100:.1f}%",
        f"- Missing-spec precision: {pct(c['missing_precision'])}",
        f"- Missing-spec recall: {pct(c['missing_recall'])}",
        f"- Confidently wrong (ready_to_price true while a required field is truly missing): {pct(c['confidently_wrong'])}",
        f"- Incomplete RFQs correctly blocked: {pct(c['incomplete_rfqs_caught'])}",
        f"- RFQs where the flagged set equals the labelled set exactly: {pct(c['rfq_exact_match'])}", "",
        "## Ablation: what each layer buys", "",
        "| Rule for 'field present' | Field accuracy | Missing precision | Missing recall | Confidently wrong RFQs |", "|---|---|---|---|---|",
    ]
    for name, desc in (("naive", "any non-null model value"), ("evidence", "+ evidence quote found in email"), ("checker", "+ reference, format, unit-token rules (full checker)")):
        x = v[name]
        lines.append(f"| {desc} | {x['field_accuracy']['p'] * 100:.1f}% | {x['missing_precision']['p'] * 100:.1f}% | {x['missing_recall']['p'] * 100:.1f}% | {x['confidently_wrong']['k']}/30 |")
    pr = o["paired_naive_vs_checker"]
    lines += ["", f"Paired, naive vs checker, on confidently-wrong RFQs: {pr['naive_only_wrong']} fixed by the checker, {pr['checker_only_wrong']} made worse; exact sign-test p = {pr['exact_sign_test_p']}. "
              "No RFQ-level difference on this sample (zero discordant pairs), so no test is informative. The ablation difference is at field level only (recall).", "",
              "## Top failure mode", "", f"**{o['failure_mode']['title']}.** {o['failure_mode']['summary']}", ""]
    for x in o["failure_mode"]["examples"]:
        lines.append(f"- {x['id']} / {x['field']}: model said `{x['model_value']}` (evidence `{x['model_evidence']}`); checker: {x['checker_reason']}. Other real gaps in this RFQ: {', '.join(x['other_gaps_still_flagged_by_naive']) or 'none'}.")
    lines += ["", o["failure_mode"]["residual_note"], "", "## Per field (descriptive; segments are tiny)", "", "| Field | Truly missing | Caught | False flags |", "|---|---|---|---|"]
    for f, d in o["per_field"].items():
        lines.append(f"| {f} | {d['truly_missing']} | {d['caught']} | {d['false_flags']} |")
    lines += ["", "## Per ambiguity type (exact flagged-set match)", "", "| Type | RFQs | Exact |", "|---|---|---|"]
    for a, d in o["per_ambiguity"].items():
        lines.append(f"| {a} | {d['n']} | {d['exact']} |")
    (ROOT / "eval" / "report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
