"""Clarification-email draft: local model, temperature 0, asked only about the checker's missing list.
A deterministic keyword check records whether every missing field is actually mentioned.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import chat  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TABLE = json.loads((ROOT / "data" / "required_fields.json").read_text())

COVER = {
    "material_grade": r"material|grade|alloy", "dimensions": r"dimension|size|length", "tolerance": r"toleranc",
    "quantity": r"quantity|how many|piece|qty", "finish": r"finish|surface|coating", "certs": r"cert|mtr|coc|paperwork",
    "delivery_date": r"date|deliver|need it by|when", "units": r"units?\b|inch|millimet|\bmm\b",
}


def make_draft(rfq, missing):
    fam = TABLE["families"][rfq["family"]]["fields"]
    asks = "\n".join(f"- {fam[f]['ask']}" for f in missing)
    sys_msg = ("You write short, polite replies from a metals quote desk to a customer. "
               "Ask ONLY for the items listed. Do not mention a price. Do not invent details. "
               "Greet the customer by first name only. Never use Mr, Ms, Mrs, Miss, Sir or Madam. "
               "Under 110 words. Plain text, no markdown. Sign off as 'Quote Desk'.")
    user = f"The customer's original email:\n\n{rfq['body']}\n\nWe cannot price this yet. Ask them to confirm:\n{asks}"
    text = chat([{"role": "system", "content": sys_msg}, {"role": "user", "content": user}],
                temperature=0.0, seed=7, num_predict=300).strip()
    if re.search(r"\b(mr|ms|mrs|miss|sir|madam)\b\.?", text, re.I):
        text = re.sub(r"\b(mr|ms|mrs|miss)\.?\s+", "", text, flags=re.I)  # deterministic fallback: drop the honorific
    covers = all(re.search(COVER[f], text, re.I) for f in missing)
    return {"text": text, "covers_all_missing": covers}
