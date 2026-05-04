---
module: quality
roadmap_phase: 4
status: skeleton
last_updated: 2026-05-04
---

# Quality

## Overview

Inspection plans, characteristic measurements, SPC (Cp/Cpk, X-bar/R), and the non-conformance (NCR) workflow. Audit log is mandatory for every entity in this module (per `golden-principles.md` GP-009 and `domain/compliance/21-cfr-part-11.md`).

## Domain entities

- `InspectionPlan` — product, station, characteristics, frequency.
- `Characteristic` — name, target, USL, LSL, sample size.
- `Measurement` — plan, characteristic, lot, value, taken_at, taken_by.
- `NonConformance` — opened_from_measurement, status, containment, root_cause, capa, closed_at.

## Use cases

- `record_measurement(...)` — checks SPC rules; if violated, emits `quality.measurement_rejected` and auto-opens NCR.
- `open_ncr(...)` / `advance_ncr_state(...)` / `close_ncr(...)` — guarded state machine.
- `compute_spc(plan, period)` — calculates Cp/Cpk and Western Electric rule violations.

## API contract

`/api/v1/quality/measurements/` (record, list).
`/api/v1/quality/ncrs/` (CRUD with state guard).
`/api/v1/quality/spc/?plan_id=&period=` (read SPC).

## Events emitted

- `quality.measurement_recorded`
- `quality.measurement_rejected`
- `quality.ncr_opened`
- `quality.ncr_closed`

## Events consumed

- `traceability.produced` — links measurement to lot.

## Open questions

- TODO: firma electrónica para 21 CFR Part 11 — método (TOTP, certificado, biométrico).
- TODO: integración con calibración de instrumentos (fuera de scope v1?).
