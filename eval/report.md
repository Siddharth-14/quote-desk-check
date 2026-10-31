# Eval report

Model `qwen2.5:7b-instruct`, prompt `v1`, temperature 0. n = 30 synthetic RFQs, 240 field decisions.
Labels: single labeller, written before the model ran. Intervals: Wilson 95%.

## Headline (full checker)

- Field accuracy: 99.6% (239/240), 95% CI 97.7-99.9%; cluster-bootstrap (resampling RFQs) 98.8-100.0%
- Missing-spec precision: 96.3% (26/27), 95% CI 81.7-99.3%
- Missing-spec recall: 100.0% (26/26), 95% CI 87.1-100.0%
- Confidently wrong (ready_to_price true while a required field is truly missing): 0.0% (0/30), 95% CI 0.0-11.3%
- Incomplete RFQs correctly blocked: 100.0% (19/19), 95% CI 83.2-100.0%
- RFQs where the flagged set equals the labelled set exactly: 96.7% (29/30), 95% CI 83.3-99.4%

## Ablation: what each layer buys

| Rule for 'field present' | Field accuracy | Missing precision | Missing recall | Confidently wrong RFQs |
|---|---|---|---|---|
| any non-null model value | 98.3% | 95.8% | 88.5% | 0/30 |
| + evidence quote found in email | 98.3% | 95.8% | 88.5% | 0/30 |
| + reference, format, unit-token rules (full checker) | 99.6% | 96.3% | 100.0% | 0/30 |

Paired, naive vs checker, on confidently-wrong RFQs: 0 fixed by the checker, 0 made worse; exact sign-test p = 1.0. No RFQ-level difference on this sample (zero discordant pairs), so no test is informative. The ablation difference is at field level only (recall).

## Top failure mode

**The model fills in details it cannot see.** Left alone, the 7B model made 3 field-level mistakes of one kind: it stated a detail the email does not contain. Given bare numbers such as '0.5 x 12 x 96' it answered units='in' and quoted the dimension string as evidence (2 RFQs). It also accepted 'same as PO 4471' as a certs value (1 RFQ). The checker rejects both patterns (a units value needs a quote containing a unit token; a reference to another order is not a value), lifting missing-spec recall from 23/26 to 26/26. At the RFQ level the naive rule was NOT confidently wrong on this set (0/30, same as the checker): all 3 of these RFQs also had a second, genuine gap that the model did flag, so they were blocked anyway. That is luck of the sample. Had units or the cert reference been the only gap, the RFQ would have gone to pricing (counterfactual, not observed here).

- RFQ-004 / units: model said `in` (evidence `0.5 x 12 x 96`); checker: units evidence quote contains no unit token. Other real gaps in this RFQ: certs.
- RFQ-005 / certs: model said `same as PO 4471` (evidence `Certs: same as PO 4471`); checker: value is a reference to another order, not a stated spec. Other real gaps in this RFQ: finish.
- RFQ-008 / units: model said `in` (evidence `1.25 OD x 1.5 long`); checker: units evidence quote contains no unit token. Other real gaps in this RFQ: finish.

The one remaining error is the reverse: on RFQ-014 the model returned no units even though the tolerance reads '+/- 0.001 in'. The checker flags units as missing, which costs one needless clarification question. That RFQ was already correctly blocked (dimensions are missing), and whether 'in' in a tolerance counts as stating units is itself a labelling-policy judgement call.

## Per field (descriptive; segments are tiny)

| Field | Truly missing | Caught | False flags |
|---|---|---|---|
| material_grade | 4 | 4 | 0 |
| dimensions | 1 | 1 | 0 |
| tolerance | 4 | 4 | 0 |
| quantity | 2 | 2 | 0 |
| finish | 4 | 4 | 0 |
| certs | 4 | 4 | 0 |
| delivery_date | 3 | 3 | 0 |
| units | 4 | 4 | 1 |

## Per ambiguity type (exact flagged-set match)

| Type | RFQs | Exact |
|---|---|---|
| none | 20 | 19 |
| units_missing | 4 | 4 |
| same_as_last_time | 3 | 3 |
| attachment_filename | 3 | 3 |
