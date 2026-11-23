# Reproduce the recorded evidence

Use the published captures and offline graders to recheck the reported counts with zero API credits. Install the Python dependencies from `requirements.lock` and run the commands from the repository root. The commits identify where the recorded evidence entered the repository. Each capture can also record its fixture digest, protocol digest, and returned model identifiers.

| Experiment | Frozen inputs and captures | Evidence commit | Expected result |
| --- | --- | --- | --- |
| V1 investigation | [Four traces](../evidence/runs) | `49aa7f6` | Four internally consistent captures |
| V2 held-out recovery | [Fixtures](../backend/reliability/incidents.json), [captures](../evidence/v2) | `bf19343` | 19/24 vs 23/24 strict passes and 13/18 vs 17/18 recoveries |
| V3 approval | [Approval and access captures](../evidence/v3) | `982382d` | Recorded permissions, approval, and restart assertions pass |
| Blind cause contract | [Fixtures](../backend/reliability/blind-cause-fixtures.json), [captures](../evidence/cause-contract-blind) | `c645149` | 47/50 vs 50/50 strict passes |
| Sol vs. Luna recovery | [Manifest, traces, and summary](../evidence/assurance/live-recovery) | `27db587` | 32 verified grades with 16/16 citation-supported Sol runs and 7/16 Luna runs |
| Database-scoped approval | [Scoped approval capture](../evidence/assurance/database-boundary.json) | `27db587` | 13/13 recorded checks |
| Citation review, fixed cap and matched budget | [Fixed cap](../evidence/assurance/citation-review-fixed-cap), [matched budget](../evidence/assurance/citation-review-matched-budget) | `100fcb5` | 32 verified trials per experiment |
| Paired citation review | [Frozen inputs, key, and capture](../evidence/assurance/citation-review-paired) | `a1b2150` | 24 verified paired trials, 12/12 supported per model before and after |
| Earlier blind citation review | [Frozen inputs, key, and capture](../evidence/assurance/citation-review-blind) | `a1b2150` | 20/20 to 17/20 supported diagnoses per model |

```sh
python scripts/check-evidence.py
python -m backend.reliability.verify
python -m backend.controls.verify
python -m backend.reliability.paired_report --fixtures backend/reliability/blind-cause-fixtures.json --evidence evidence/cause-contract-blind
python -m backend.reliability.verify_recovery evidence/assurance/live-recovery
python -m backend.reliability.verify_recovery evidence/assurance/citation-review-fixed-cap
python -m backend.reliability.verify_recovery evidence/assurance/citation-review-matched-budget
python -m backend.reliability.verify_paired_citations evidence/assurance/citation-review-paired
```

The [release scorecard](release-scorecard.md) gives the main results and the boundaries of the evidence. Public replay is static. The recorded results come from lab-authored synthetic incidents, with an independently authored cohort still pending.

The [scoped stress fixtures](../backend/reliability/quality-fixtures) and [selective capture](../evidence/assurance/selective-stress) include sealed input digests, model identifiers, and all 32 traces. Regenerate the detailed summary with `python -m backend.reliability.quality_report evidence/assurance/selective-stress`. The [controlled citation challenge](../evidence/assurance/citation-challenge) used the public reviewer-kit example.
