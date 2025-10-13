# Clamp Telemetry Diagnostics (Phase 3)

The Phase 3 diagnostics bridge overlays lightweight inspection tooling on top of Clamp’s telemetry artifacts. Use this guide to reason about the aggregate summary, drill into individual sessions, and connect stability metrics with reproducibility decisions.

## Interpreting Key Metrics

- **Mean Stability** (`meanStability`) – arithmetic average of per-record `stability_score`. Values near 1.0 imply consistent lock behaviour; sustained drops highlight regression candidates.
- **Variance** (`variance`) – sample variance derived with Welford running statistics. Rising variance signals widening spread across runs even if the mean remains stable.
- **Drift Percentile** (`driftPercentile`) – 95th percentile of recorded `duration_ms`. This is the practical “tail latency” for lock retention: an increase indicates longer stalls or contention windows. Legacy consumers may still reference `drift_index` (numeric match).
- **Session Count** (`sessionCount`) – total telemetry records covered by the summary. Behavior changes should be evaluated against comparable sample sizes.

When monitoring trends, track both the mean and variance: a stable mean with climbing variance is often the first sign of intermittent instability. Drift percentiles help distinguish between isolated spikes and systemic regressions by anchoring measurements to the long tail.

## telemetry_inspect Usage

From the project root (after building with Ninja):

```bash
./telemetry_inspect            # Aggregate table plus per-session breakdown
./telemetry_inspect --summary  # Aggregate table only
./telemetry_inspect --sessions # Per-session view only
```

The per-session output renders ASCII bars scaled to the maximum observed values. `#` characters mark relative magnitude, while `(p95=…)` displays the exact drift percentile for each session file.

Example session snippet:

```
session_a.json mean=0.8125 count=8
  mean  ######################......
  drift ##########.................. (p95=12.50)
```

Use the camelCase metrics in new tooling; snake_case aliases remain in the JSON for backward compatibility.
