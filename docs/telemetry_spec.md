# Clamp Telemetry Specification (v0.4)

This document defines the JSON schema exported by `EntropyTelemetry::writeJSON` and the collection procedure used by Clamp v0.4. Telemetry snapshots are written to `build/telemetry/clamp_run_<timestamp>.json` during validation and continuous integration workflows.

## Record Schema

Each JSON document contains a single object with the top-level property `stability_score` (the arithmetic mean of all recorded stability scores) and the property `records`, an array of anchor events. Every element of the array adheres to the following structure:

| Field            | Type    | Description                                                                                  |
|------------------|---------|----------------------------------------------------------------------------------------------|
| `context`        | string  | Logical name of the anchor (e.g., thread id or subsystem).                                   |
| `seed`           | number  | 64-bit entropy seed captured at lock acquisition.                                            |
| `thread_id`      | string  | Host thread identifier that acquired the anchor.                                             |
| `acquired_at`    | string  | ISO-8601 UTC timestamp marking lock acquisition.                                             |
| `released_at`    | string \| null | ISO-8601 UTC timestamp for anchor release; `null` if the anchor is still in-flight.   |
| `duration_ms`    | number  | Measured lock duration in milliseconds (0.000 precision).                                   |
| `stability_score`| number  | Normalized (0.0–1.0) stability metric associated with the anchor cycle.                      |

## Collection Procedure

1. `ClampAnchor::lock` registers an acquisition event with the process-local `EntropyTelemetry` instance, capturing the entropy seed, thread id, and acquisition timestamp.
2. `ClampAnchor::release` finalises the record, computing duration and assigning a stability score (current implementation emits `1.0` for successful cycles).
3. Integration and tests invoke `EntropyTelemetry::writeJSON()` to serialize accumulated records into `build/telemetry/`.
4. Continuous integration workflows archive `build/telemetry/` alongside the compiled test binaries for reproducibility analysis.

## Reproducibility Criteria

- All timestamps are reported in UTC and may be aligned post-hoc via `EntropyTelemetry::alignToReference`.
- Entropy seeds must remain non-zero for valid anchors; zero values indicate failed acquisition and should be flagged.
- Stability scores are constrained to `[0.0, 1.0]`. Values outside the range constitute telemetry corruption.
- Telemetry files must be preserved as CI artifacts for every tagged release. Validation scripts may inspect aggregate stability using `jq '.stability_score' build/telemetry/*.json` or per-record data with `jq '.records[].stability_score' build/telemetry/*.json`.

Future revisions will extend the schema with distributed node identifiers and probabilistic scoring metadata as the ROCForge reproducibility framework evolves.

## Summary Artifact

`TemporalAggregator` consumes all session files beneath `build/telemetry/` and emits `build/telemetry_summary.json` with the following top-level fields:

| Field              | Type   | Description                                                        |
|--------------------|--------|--------------------------------------------------------------------|
| `source_directory` | string | Directory scanned for session logs.                                |
| `session_count`    | number | Total count of aggregated telemetry records.                       |
| `mean_stability`   | number | Arithmetic mean of all stability scores (fixed 6 decimal places).  |
| `stability_variance` | number | Sample variance of the stability scores.                         |
| `drift_index`      | number | Difference between earliest and latest session timestamps (ms).    |

The summary file is meant for longitudinal analysis and accompanies the raw session logs in release artifacts and CI uploads.
