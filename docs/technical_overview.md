# Clamp Telemetry & Stability Architecture (v0.3)

## Entropy Lifecycle
- **Seed Generation**: `EntropyTracker` combines a steady clock tick with the executing thread identifier to produce deterministic-yet-unique entropy seeds.
- **Anchor Acquisition**: `ClampAnchor::lock` acquires the seed, updates the stabilization state machine to `Locked`, and registers the event with `EntropyTelemetry`, capturing timestamps and thread metadata.
- **Anchor Release**: Upon scope exit or explicit `release`, the anchor transitions through `Released` → `Unlocked`, resets entropy, and finalizes the telemetry record with a measured lock duration.
- **JSON Export**: Telemetry emits machine-readable summaries of each anchor interaction, enabling off-line reproducibility analysis or ingestion by ROCForge’s telemetry bus.

## ROCm / HIP Dependency Graph
- **HIP Runtime** (`hip::host`) provides kernel launch services and thread affinity metadata used to mirror entropy values onto AMD GPUs.
- **rocBLAS** initializes alongside Clamp to ensure numerical workloads can bind to stabilized anchors during integration testing.
- **HIP Kernel Validation**: `clampMirrorKernel` transfers seeds and state flags to device buffers, returning them to the host for validation so that host/device anchor views remain synchronized.

## Stability Metrics
- **Lock Duration (ms)**: Derived from telemetry timestamps, exposes anchor “half-life” across repeated acquisitions.
- **Entropy Deviation**: Seeds collected across threads are compared for drift and collision detection.
- **State Fidelity**: Transition logs ensure anchors never bypass expected `Unlocked → Locked → Released → Unlocked` progressions.
- **Reproducibility Score (WIP)**: Aggregated statistics form the basis of an upcoming scoring mechanism used to classify runtime stability under stochastic workloads.

## Experimental Protocol
1. Execute the standard validation loop (`ctest --output-on-failure`) to produce telemetry snapshots.
2. Inspect the generated JSON (via `EntropyTelemetry::toJson`) to confirm deterministic seeds and durations inside multi-threaded workloads.
3. Review HIP mirror status (available through test assertions) to ensure GPU coherence.
4. Archive telemetry outputs alongside ROCForge’s global entropy field data for composite system analysis.

Future iterations will extend telemetry to streaming collectors, integrate ROCProfiler sessions, and surface reproducibility scores directly within ROCForge dashboards.
