# Reliability Lab release scorecard

| Area | Recorded result | Evidence |
| --- | --- | --- |
| Correct grounded diagnoses | V2 improved from 19/24 to 23/24 | [Held-out evaluation](../evidence/v2/summary.json) |
| Tool failure recovery | V2 improved from 13/18 to 17/18 exposed runs | [Recovery counts](../evidence/v2/summary.json) |
| Cause-label contract | 47/50 to 50/50 strict passes | [Blind comparison](../evidence/cause-contract-blind/paired.json) |
| Citation support | Original Sol vs. Luna was 16/16 vs 7/16 | [Live recovery comparison](../evidence/assurance/live-recovery/summary.json) |
| Citation review regression | Both models fell from 20/20 to 17/20 in the first blind follow-up | [Blind citation review](../evidence/assurance/citation-review-blind/summary.json) |
| Paired review after the worker fix | Both models scored 12/12 before and after review. The initial citations all passed. | [Paired policy results](../evidence/assurance/citation-review-paired/summary.json) |
| Paired latency and estimated cost | Sol 5.90 s / $0.112238 off and 7.82 s / $0.134186 always on. Luna 5.55 s / $0.006821 off and 7.09 s / $0.008055 always on. Times are medians and each cost covers 12 trials. | [Latency and cost](../evidence/assurance/citation-review-paired/summary.json) |
| Approval and recovery | 13/13 scoped recovery checks. One approved restart and one completed order. | [Database-scoped approval](../evidence/assurance/database-boundary.json) |

Citation review is off by default. The promotion gate requires outside authorship, sufficient weak-citation coverage, and per-model accuracy, support, latency, and cost checks. [Promotion policy](citation-promotion.md) · [Offline reproducibility bundle](reproduce-evidence.md)

The [scoped selective stress run](scoped-reliability.md) recorded 32 trials across eight synthetic incidents. Both models reached 8/8 cause accuracy with review off and selective review. Citation support held at 8/8 for Sol and 7/8 for Luna. The selective policy missed Luna's weak citation on the overlapping-fault case.
