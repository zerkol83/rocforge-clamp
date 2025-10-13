# Clamp Telemetry & Stability Architecture (v0.4)

## Entropy Lifecycle
- **Seed Generation**: `EntropyTracker` combines a steady clock tick with the executing thread identifier to produce deterministic-yet-unique entropy seeds.
- **Anchor Acquisition**: `ClampAnchor::lock` acquires the seed, updates the stabilization state machine to `Locked`, and registers the event with `EntropyTelemetry`, capturing timestamps and thread metadata.
- **Anchor Release**: Upon scope exit or explicit `release`, the anchor transitions through `Released` → `Unlocked`, resets entropy, and finalizes the telemetry record with a measured lock duration.
- **JSON Export**: Telemetry emits machine-readable summaries of each anchor interaction, enabling off-line reproducibility analysis or ingestion by ROCForge’s telemetry bus.

## ROCm / HIP Dependency Graph
- **HIP Runtime** (`hip::host`) provides kernel launch services and thread affinity metadata used to mirror entropy values onto AMD GPUs.
- **rocBLAS** initializes alongside Clamp to ensure numerical workloads can bind to stabilized anchors during integration testing.
- **HIP Kernel Validation**: `clampMirrorKernel` transfers seeds and state flags to device buffers, returning them to the host for validation so that host/device anchor views remain synchronized.

## Temporal Alignment & Distributed Aggregation
- **Reference Alignment**: Telemetry snapshots from multiple nodes can be aligned to a shared reference timestamp; offsets are applied uniformly to accurately measure temporal drift.
- **Snapshot Aggregation**: `EntropyTelemetry::merge` accepts batches from remote processes, providing a consolidated view of distributed anchor activity for cross-run analysis.
- **Persistent Archival**: Telemetry can be serialized to `/tmp/clamp_telemetry` (or a caller-defined path) enabling post-run ingestion by ROCForge analytics and long-lived stability studies.

## Stability Metrics & Scoring
- **Lock Duration (ms)**: Derived from telemetry timestamps, exposes anchor “half-life” across repeated acquisitions.
- **Entropy Deviation**: Seeds collected across threads are compared for drift and collision detection.
- **State Fidelity**: Transition logs ensure anchors never bypass expected `Unlocked → Locked → Released → Unlocked` progressions.
- **Temporal Reproducibility Score**: `TemporalScoring` produces a normalized 0.0–1.0 index by combining entropy variance, duration variance, and drift components, providing a quantitative definition of stability across sequential and parallel workloads.
- **Aggregate Stability Summary**: `TemporalAggregator` merges multiple session logs into `telemetry_summary.json`, reporting `mean_stability`, `stability_variance`, `drift_index`, and `session_count` for longitudinal analysis.

## Experimental Protocol
1. Execute the standard validation loop (`ctest --output-on-failure`) to produce telemetry snapshots.
2. Inspect the generated JSON (via `EntropyTelemetry::writeJSON` or `toJson`) to confirm deterministic seeds, durations, and aligned timestamps.
3. Aggregate all telemetry logs using `TemporalAggregator` to create `telemetry_summary.json`, capturing mean/variance/drift across runs.
4. Compute stability indices with `TemporalScoring::evaluate` or `evaluateAggregated`, capturing JSON summaries for dashboards.
5. Review HIP mirror status (available through test assertions) to ensure GPU coherence.
6. Archive telemetry outputs alongside ROCForge’s global entropy field data for composite system analysis.

Future iterations will extend telemetry to streaming collectors, integrate ROCProfiler sessions, and surface reproducibility scores directly within ROCForge dashboards.
