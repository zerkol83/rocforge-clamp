# Clamp Telemetry Diagnostics (Phase 3)

The Phase 3 diagnostics bridge overlays lightweight inspection tooling on top of Clamp’s telemetry artifacts. Use this guide to reason about the aggregate summary, drill into individual sessions, and connect stability metrics with reproducibility decisions.

## Interpreting Key Metrics

- **Mean Stability** (`meanStability`) – arithmetic average of per-record `stability_score`. Values near 1.0 imply consistent lock behaviour; sustained drops highlight regression candidates.
- **Variance** (`stabilityVariance`) – sample variance derived with Welford running statistics. Rising variance signals widening spread across runs even if the mean remains stable.
- **Drift Index** (`driftIndex`) – Difference between earliest and latest session timestamps. This approximates long-tail spread across telemetry runs.
- **Session Count** (`sessionCount`) – Total telemetry records covered by the summary. Behavior changes should be evaluated against comparable sample sizes.

When monitoring trends, track both the mean and variance: a stable mean with climbing variance is often the first sign of intermittent instability. Drift index helps distinguish between isolated spikes and systemic regressions by anchoring measurements to the long tail.

## Diagnostics Bridge

The Phase 4 split removes the standalone `telemetry_inspect` CLI. Diagnostics and parity reporting will return as part of the ROCForge-CI bridge (`python -m rocforge_ci ...`) once visualization work lands in Phase 7. Until then, telemetry summaries can be inspected with `jq` or any JSON tooling:

```bash
jq '.mean_stability, .stability_variance, .drift_index, .session_count, .build_info' build/telemetry_summary.json
```

CamelCase and snake_case aliases remain in the JSON for backward compatibility.
