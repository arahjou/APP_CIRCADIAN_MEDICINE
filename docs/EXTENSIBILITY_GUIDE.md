# Extending CMAS

Updated 2026-10-24. The numerical service is the integration point.

## A new device

1. Obtain a real export specification and verify timestamp semantics, timezone,
   epoch length, signal definitions, units and calibration.
2. Implement an adapter returning `Recording(data, metadata)`, or use the normalized
   CSV contract in DATA_FLOW.md with an explicit column mapping.
3. Preserve source bytes hash, device/firmware label, mapping and conversion version.
4. Do not rename acceleration/ENMO to PIMn, or photopic lux to melanopic EDI, without
   a validated transformation. Unconverted signals can remain additional columns.
5. Add fixtures for actual headers and synthetic boundary cases, including optional
   channels, corrupt timestamps, missing values, duplicate records and DST.
6. Demonstrate the same supported metric calculations through UI and batch entry points.

ActiHub can initially export the documented CSV contract. Hardware-specific BLE,
firmware parsing, calibration and measurement equivalence remain separate work.

## A new metric or modality

1. Add the standard signal and units to `tools/recording.py` if needed.
2. Define eligibility in `services/analysis_service.py`: valid coverage, sampling,
   missingness and time assumptions must be explicit.
3. Implement a pure calculator in `tools/`; document units and edge cases.
4. Register orchestration and outcomes in `services/recording_service.py`. Preserve
   `completed/unavailable/skipped/failed` distinctions.
5. Add reproducibility parameters and regression tests against independently known
   examples. Verify that missing inputs produce no fabricated numerical result.
6. Existing HTML renders generic result tables. Add meaningful labels/units and
   plots where needed. Update comparison schemas deliberately if exposing the
   metric to the AI pipeline.
7. If a new modality needs a legacy SQLite table, update schema, safe table lists,
   the persistence whitelist and historical readers. A run report can retain new
   structured results without forcing a premature wide database schema.

## Temperature and phasor experiments

Temperature is imported and summarized, but experimental temperature/phasor rhythm
metrics are not promoted to the main engine. Before doing so, replace fixed sample
count assumptions with explicit cadence/coverage rules, handle low-amplitude
undefined phase, validate circular summaries, and test DST and missing channels.

## LLM experiments

Keep Development variants available for comparison. Use fixed approved cases with
known numerical changes and reviewed evidence. Evaluate numerical fidelity,
retrieval relevance, claim-to-paper support, missing-evidence behavior, readability
and runtime. PMID membership checks alone are not claim validation. A percentage
change threshold is a tunable heuristic unless independently justified. Choose a
pipeline from benchmark results before replacing the current mainline graph.
