Clamp — Runtime Stabilization & Environment Anchoring Module for ROCForge

Clamp is a foundational subsystem in the ROCForge toolchain designed to provide deterministic runtime anchoring, environmental consistency, and fault-tolerant state control for heterogeneous compute pipelines.

Where ROCForge orchestrates large-scale GPU/CPU workloads, Clamp acts as its stabilizer — detecting, isolating, and controlling volatile runtime states that arise from entropy-driven scheduling, thread divergence, or inconsistent memory visibility across the ROCm stack.

Clamp exposes a simple C++20 API (ClampAnchor) that lets higher-level modules “lock” execution environments, synchronize memory anchors, and safely “release” them once integrity checks pass. ClampAnchor relies on RAII semantics so anchors lock during construction and release automatically on scope exit. Each anchor tracks a lightweight entropy seed derived from clock and thread identifiers, making HIP kernel seeding deterministic while preparing for ROCForge’s future global entropy model. The v0.4 line extends this foundation with an EntropyTelemetry subsystem that captures per-anchor seeds, timestamps, thread identifiers, and lock durations, plus a TemporalScoring evaluator that quantifies reproducibility scores across sequential and distributed runs. A stabilization protocol records anchor state transitions (Unlocked → Locked → Released/Error) with timestamped diagnostics and HIP mirroring routines to guard against double-locks or premature releases while validating device-side consistency.

The project’s immediate goals are:

Runtime Anchoring: Create a low-overhead mechanism for pinning execution contexts and preventing temporal drift between CPU–GPU compute phases.

Entropy Management: Integrate entropy tracking for controlled randomness, ensuring repeatable outcomes in deterministic simulations.

Integration Readiness: Serve as a drop-in subsystem for the broader ROCForge engine, supporting both developer debugging and production-grade runtime validation.

Long-term, Clamp will form the backbone of ROCForge’s stabilization layer — bridging experimental GPU-accelerated logic with predictable, auditable runtime control suitable for both academic reproducibility and commercial reliability.

## Build & Validation
```bash
mkdir build
cd build
cmake -G Ninja ..
ninja
ctest --output-on-failure
```

The default build links against HIP and rocBLAS, enabling the optional HIP entropy mirroring kernel used during validation. Test output includes multi-threaded reproducibility checks, telemetry JSON export verification, and host/device synchronization assertions.

## Telemetry & Metrics
- `EntropyTelemetry` records per-anchor seeds, acquisition/release timestamps, thread identifiers, and lock durations.
- JSON snapshots provide machine-readable feeds for ROCForge telemetry ingestion and can be serialised to `/tmp/clamp_telemetry` or a user-specified path.
- HIP mirroring validates that entropy seeds and state flags observed on the host are consistent on AMD GPUs.
- `TemporalScoring` consumes telemetry snapshots to produce normalized reproducibility scores (0.0–1.0), entropy variance, duration variance, and drift measurements. Results can be exported as JSON or human-readable summaries for dashboards and CI artifacts.
- `TemporalAggregator` consolidates telemetry logs under `build/telemetry/`, computes cross-run statistics, and emits `telemetry_summary.json` exposing `meanStability`, `variance`, `driftPercentile`, and `sessionCount` (with legacy snake_case aliases) for versioned reproducibility reporting.

### ROCm Toolchain Setup
Ensure HIP and rocBLAS are discoverable by CMake:
```bash
export HIP_DIR=/opt/rocm/lib/cmake/hip
export CMAKE_PREFIX_PATH=/opt/rocm:/opt/rocm/lib/cmake
cmake -S . -B build -G Ninja
cmake --build build
ctest --output-on-failure --test-dir build
```
Adjust `/opt/rocm` if ROCm is installed elsewhere.

See `docs/technical_overview.md` for an in-depth discussion of the entropy lifecycle, temporal alignment algorithms, ROCm dependency graph, and stability metrics captured during the v0.4 validation campaign. The telemetry schema and reproducibility guarantees are defined in `docs/telemetry_spec.md`.
