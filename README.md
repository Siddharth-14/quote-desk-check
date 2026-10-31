# Quote Desk Check

**Live demo:** https://quote-desk-check.netlify.app

An audit of an RFQ-triage agent on 30 synthetic manufacturing quote requests. The agent flags the specs a customer left out and holds the price until they arrive. The demo shows how often that flag is right.

> All data is synthetic and all prices are illustrative. This is a personal project. It is not Forgepoint's product and uses nothing from Forgepoint.

## Problem

A quote desk receives emails like "need 6061 plate, 0.75 x 48 x 48, 40 pcs". Pricing before the spec is complete creates rework and wrong quotes. A triage agent that checks for missing specs first is only useful if you know how often it is wrong, and in which direction. The costly direction is **confidently wrong**: the agent says "ready to price" while a required field is missing.

## What it does

1. A local model (`qwen2.5:7b-instruct`, temperature 0) extracts 8 required fields from each email, each with a verbatim quote as evidence. The model never decides readiness.
2. A plain-Python checker compares the extraction with a required-field table (`data/required_fields.json`, two product families) and sets the flags and `ready_to_price`.
3. Ready requests get a price from plain rules with a printed trace: weight x base $/lb x grade x tolerance x quantity break x rush.
4. Incomplete requests get a clarification draft that asks only about the missing fields.
5. Every request also shows the 3 most similar past jobs (80 invented jobs, `all-MiniLM-L6-v2` embeddings, FAISS).

## How it runs for $0

- The model runs locally in Ollama. No API, no key, no card. Embeddings are a free local model.
- Everything the page shows is precomputed JSON (`data/outputs/`, copied to `site/data/`). The deployed site is static: no live model calls and no key anywhere in client code. A Content-Security-Policy limits the page to its own origin.
- Hosting is Netlify's free plan ($0, no card). Checked 31 Oct 2026: the free plan has a 300-credit monthly cap and a site that reaches it is paused until the next cycle, not billed. Netlify pauses all projects on the account together.

```bash
python3 -m venv .venv && .venv/bin/pip install sentence-transformers faiss-cpu numpy jsonschema
ollama pull qwen2.5:7b-instruct
.venv/bin/python pipeline/generate_rfqs.py   # 30 emails (already committed; rerun to regenerate)
.venv/bin/python pipeline/validate.py --seed # data QA before any model run
.venv/bin/python pipeline/past_jobs.py
.venv/bin/python pipeline/extract.py         # model extraction
.venv/bin/python pipeline/run_all.py         # checker, pricing, retrieval, drafts
.venv/bin/python eval/run_eval.py            # metrics and eval/report.md
.venv/bin/python pipeline/validate.py --outputs
.venv/bin/python pipeline/export_site.py     # then serve site/ with any static server
```

## The eval (the AI PM artifact)

Hand labels (`data/labels.json`) were written from the final email text before the extractor ran. Full numbers, ablation and failure analysis are in [`eval/report.md`](eval/report.md).

| Measure (n = 30 requests, 240 field checks) | Result | 95% Wilson interval |
|---|---|---|
| Confidently wrong (ready while a field is missing) | 0 of 30 | 0 to 11% |
| Incomplete requests held back | 19 of 19 | 83 to 100% |
| Missing-spec recall (fields) | 26 of 26 | 87 to 100% |
| Missing-spec precision (fields) | 26 of 27 | 82 to 99% |
| Field accuracy | 239 of 240 | 98 to 99.9% |

**Top failure mode: the model fills in details it cannot see.** Given bare numbers (`0.5 x 12 x 96`) it answered `units = "in"`, and it accepted "same as PO 4471" as a certification. The checker rejects both patterns, lifting field recall from 23/26 to 26/26. At the request level the naive rule was *not* confidently wrong on this set, only because each of those requests also had a second real gap. That is luck of the sample, not safety. Examples: RFQ-004, RFQ-005, RFQ-008.

## Limits

- **Synthetic.** Emails come from templates plus a local-model paraphrase. Real inboxes are messier, and the paraphrase pass shaped what the emails contain.
- **n = 30.** Every rate has a wide interval. "0 confidently wrong" means the true rate is plausibly anywhere up to about 11%. `dimensions` is missing in only 1 request, so its recall rests on one case. The 240 field checks come from 30 emails and are not independent.
- **Single labeller.** One labeller wrote the labels, before the model ran, using the rules in `data/LABELLING.md`. The labels were drafted by Claude Code, an AI assistant working for the repo owner, and have not had an independent second review. One label (RFQ-003) was corrected after the validation step caught it. The checker and the labels follow the same written policy, so some agreement is by construction. One end-to-end error (RFQ-014, units) is a labelling judgement call.
- **Prompt frozen at v1.** The extraction prompt was written from the labelling policy and not tuned on these 30 emails. Tuning on n = 30 would turn the eval into memorisation.
- **Not Frank.** This does not model how a real estimator thinks or decides. Prices come from invented rules and invented past jobs and say nothing about any real market.
- Netlify injects a small same-origin script (`/.netlify/scripts/hud`) on free-tier sites. It is not part of this repo.

## Layout

```
data/       required_fields.json, schema.json, rfqs.json, labels.json, LABELLING.md, past_jobs.json, outputs/
pipeline/   generate_rfqs, extract, checker, pricing, retrieve, draft, run_all, validate, export_site
eval/       run_eval.py, report.md
site/       index.html, styles.css, app.js, fonts/, data/   (the deployed static site)
```
