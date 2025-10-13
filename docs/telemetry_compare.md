# Clamp Telemetry Comparison (Legacy Reference)

> **Note:** Comparative profiling now belongs to the ROCForge-CI pipeline. Clamp
> no longer ships the `telemetry_inspect` CLI or backend-aware summaries. This
> document is retained for historical context and future work inside
> `rocforge_ci`.

Phase 4 originally introduced comparative profiling so that CPU, HIP, and future Instinct backends could be evaluated side-by-side. The comparison layer consumed backend-aware summaries and emitted a consolidated parity report for dashboards or CI triage.

## Metrics

- **Mean Stability Delta (`meanDelta`)** – difference between backend mean stability and the CPU/host (or first) baseline. Positive values favour the compared backend; negative values indicate a regression.
- **Drift Skew (`driftSkew`)** – percentile drift offset (in milliseconds) between the backend and baseline. Values beyond ±5 ms are flagged as significant in both the CLI (`*`) and JSON payload (`driftSignificant`).
- **Variance Ratio (`varianceRatio`)** – ratio of sample variance versus baseline. `1.0` indicates parity; values greater than one signal higher spread.

Underlying summaries preserve camelCase fields with snake_case aliases to remain compatible with any Phase 2 automation.

## CLI Usage

```bash
ninja telemetry_inspect
./telemetry_inspect --compare build/telemetry_summary_*.json
```

Sample output:

```
Comparison (baseline: CPU)
+----------------+---------+---------+-----------+---------+---------+---------+-------+
| Backend        | Mean    | ΔMean   | Drift p95 | Drift Δ | Var     | Var x   | Trend |
+----------------+---------+---------+-----------+---------+---------+---------+-------+
| CPU/host       | 0.8000  | 0.0000  | 20.0000   | 0.0000  | 0.0400  | 1.00    | ↑     |
| HIP/gfx1100    | 0.7800  | -0.0200 | 27.0000   | 7.0000* | 0.0500  | 1.25    | ↓     |
+----------------+---------+---------+-----------+---------+---------+---------+-------+
(*) drift delta exceeds ±5 ms threshold
```

The tool writes `build/telemetry_comparison.json` with baseline metadata and per-backend deltas:

```json
{
  "baseline": {
    "backend": "CPU",
    "deviceName": "host",
    "meanStability": 0.8,
    "variance": 0.04,
    "driftPercentile": 20.0
  },
  "entries": [
    {
      "path": "build/telemetry_summary_cpu.json",
      "backend": "CPU",
      "deviceName": "host",
      "meanDelta": 0.0,
      "varianceRatio": 1.0,
      "driftSignificant": false
    },
    {
      "path": "build/telemetry_summary_hip.json",
      "backend": "HIP",
      "deviceName": "gfx1100",
      "meanDelta": -0.02,
      "varianceRatio": 1.25,
      "driftSignificant": true
    }
  ]
}
```

Downstream tooling can ingest the JSON to surface backend regressions, while developers can rely on the CLI output during local profiling or CI investigations.
