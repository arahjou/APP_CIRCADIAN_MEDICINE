# CMAS research-workflow foundation

Scope agreed 2026-10-24: evolve the existing application into a reproducible,
device-independent research workflow, retaining the current metric implementations
and local AI pipeline. This is an engineering milestone, not clinical validation.

## Implementation sequence

1. Define a normalized recording contract and explicit CSV import options.
   Preserve optional signals, original sleep labels, device units, and input hash.
2. Add actionable quality checks and metric eligibility. Correct calendar pairing
   in SRI and sleep-duration labeling in comparison reports.
3. Extract numerical orchestration into a UI-independent service. Persist unique
   runs, input snapshots, parameters, software fingerprints, outcomes and reports.
4. Connect the service to Streamlit and a batch CLI. Produce an HTML/JSON report
   for a single recording without an LLM; retain existing comparison/AI features.
5. Add regression and integration tests, run existing checks, and document the
   architecture, data flow, compatibility boundaries and remaining pilot work.

## Acceptance criteria

- Optional signals do not prevent importing a recording or running eligible metrics.
- Unknown activity units are never silently converted to PIM activity counts.
- Invalid timestamps, duplicates, unsupported sampling and missing signals are
  surfaced before calculation; missing sleep is not silently treated as wake.
- Missing calendar days cannot become adjacent-day SRI comparisons.
- Every persisted numerical run has an immutable identifier and reproducibility
  metadata; concurrent reports do not share an output filename.
- New results remain visible through the existing database-backed views.
- Representative synthetic recordings exercise import, calculation, persistence,
  report export and failure behavior without touching the bundled database.

## Boundaries

The repository does not establish an ActiHub firmware export specification. A
documented normalized CSV contract and explicit column mapping are the integration
boundary; hardware decoding/calibration requires a real export and its specification.
Experimental temperature/phasor and LLM variants remain experimental until benchmarked.
Existing record ownership, cloud deployment and clinical interpretation validation
are separate follow-up work. No user data or stored credentials are test fixtures.
