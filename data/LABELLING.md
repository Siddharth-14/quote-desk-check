# Labelling protocol

Labels in `labels.json` were written **before** the extractor ran on any RFQ (the extractor output
files did not exist at the time; see git history). Each label is the set of required fields that are
*not stated in the email text*, judged from the final email text, not from the generator's plan.

Rules (also in `required_fields.json -> policy`):
- An explicit "no certs needed" / "mill standard tolerance" is a stated answer, so the field is present.
- "Same as last time" / "same as PO 4471" with no value in this email: field is **missing**.
- "Same as last time (zinc plate)": value is stated, so the field is **present**.
- Spec only in an attachment filename or "see attached": **missing**. Attachment contents are not visible.
- Bare numbers with no unit anywhere: `units` is **missing** (dimensions are present).
- "ASAP" / "rush" is not a delivery date.

Single labeller. Labels were drafted by Claude Code reading each email; the repo owner should review
them before treating the scoreboard as more than a demo.
