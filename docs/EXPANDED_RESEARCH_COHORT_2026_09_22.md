# Expanded research cohort — 22 September 2026

## Purpose

Expand the browsable company universe without changing the accepted 27-case outcome audit or weakening any source/identity gate.

The UI now separates:

- **27 audited historical Canadian outcome cases**; and
- **13 additional identity-qualified historical research companies** that are used as time-indexed controls or control candidates.

The combined browsable universe is therefore **40 unique companies**.

These 13 additional rows are **not current prospects**, **not permanent negatives**, and **not training-positive labels**.

## Source of the 13 additional companies

The expanded research cohort is derived only from existing reviewed identity artifacts:

- `reviews/control_cohorts/2026-09-20-control-identity-decisions.json`
- `reviews/control_cohorts/2026-09-22-expanded-control-identity-batch-01.json`
- `reviews/control_cohorts/2026-09-22-expanded-control-identity-batch-02.json`

One qualified control, SD2 Engineering Services, is excluded from the expanded UI cohort because the same company is already represented in the 27 audited historical cases.

The net-new research companies are:

1. SENZOMATIC, s.r.o.
2. Global Wind Service A/S
3. Deutsche Bahn International Operations GmbH
4. innoscripta SE
5. RWE Supply & Trading GmbH
6. SKS Welding Systems GmbH
7. WIZ DIGITAL SERVICES LIMITED
8. Andriani S.p.A.
9. EUROP ASSISTANCE S.A.
10. General Medical Merate S.p.A.
11. GILARDONI S.P.A. a Socio Unico
12. Leaf Space S.p.A.
13. NORD ENGINEERING FRANCE

## Analysis continuation

Nine of the 13 are the newly qualified batch-01/batch-02 controls. Their exact reviewed aliases are materialized in:

`reviews/backtests/2026-09-22-expanded-research-entities.json`

The dedicated workflow:

`.github/workflows/expanded-research-signal-scan.yml`

runs source-specific historical scans for:

- CIPO Canadian trademark evidence;
- TED procurement awards; and
- CanadaBuys federal award notices.

The output is composed through the existing event-time snapshot machinery at the original matched candidate anchors and 24/12/6/3-month cutoffs.

### CIPO boundary

The CIPO researcher bulk extract is presence-only because the known application-1799092 completeness gap prevents authoritative absence inference.

Therefore:

- a CIPO hit may be used as presence evidence;
- a CIPO non-hit in the researcher extract remains `UNKNOWN_UNVERIFIED_COVERAGE`;
- authoritative absence for the new aliases requires the full Trademarks Journal completeness scan.

This boundary is not relaxed for cohort expansion.

## Larger company-universe bottleneck

The current recent EU Investment Canada audit window contains **382** new-business outcomes.

Only **27** are currently federal-registry-confirmed in the gold audit because the resolver requires supported Corporations Canada identity evidence.

The unresolved geography queue remains:

- Ontario: 164
- Québec: 120
- British Columbia: 50
- Alberta: 15
- Nova Scotia: 12
- Saskatchewan: 3
- unknown: 3
- Manitoba: 2
- New Brunswick: 2
- Prince Edward Island: 1

Provincial registry access remains licence/API constrained. Publicly searchable interfaces are not treated as permission for commercial automated ingestion.

The next high-value expansion path remains:

1. continue exact foreign-identity review on unblocked research cohorts;
2. complete source-specific event-time coverage for those identities;
3. pursue supported/licensed provincial registry access to recover more of the 355 unresolved recent outcomes;
4. broaden the matched entrant strata before interpreting exploratory effect sizes;
5. keep Expansion Score publication blocked until a predeclared confirmatory design is evaluated on independent validation data.
