# PAT Report Generator — Specifications

Spec-driven design for the rebuilt ABET reporting tool. Read these in order before any implementation work begins; update them when reality changes.

| # | Document | Purpose |
|---|---|---|
| 01 | [Requirements](01_requirements.md) | Numbered functional and non-functional requirements. Each requirement traces to a test in 05. |
| 02 | [Architecture](02_architecture.md) | Module layout, data flow, key technical decisions with rationale. |
| 03 | [Data Model](03_data_model.md) | PAT raw schema, cleaned canonical schema, Report intermediate representation, Assessment Schedule schema. |
| 04 | [UI Spec](04_ui_spec.md) | Per-page Streamlit behaviors: sidebar, Course Report, Sub-Outcome Lookup, Coverage Check. |
| 05 | [Verification](05_verification.md) | Test strategy, fixtures, requirement-to-test traceability, manual acceptance checklist. |
| 06 | [Implementation Plan](06_implementation_plan.md) | Six-phase build with entry/exit criteria, effort estimates, risk register, decision log. |

## Status

Draft v1 — awaiting review.

## How to use

1. Read 01 → 06 in order. Each builds on the prior.
2. Disagreements with the spec are raised and resolved *here* before code changes.
3. When the build deviates from the spec, update the spec — don't let it go stale.
4. The decision log at the end of 06 captures every architectural choice and its rationale; append to it as new decisions are made.
