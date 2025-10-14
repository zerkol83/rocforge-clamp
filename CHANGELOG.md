Clamp v0.5.0 — Runtime Isolation & ROCForge-CI Split
===================================================

Release date: 2025-??-??  
Status: Pending validation under Debian 13 + ROCm 6.4.4  
Tag: v0.5.0

Highlights
----------

- **Runtime isolation** – Clamp no longer performs network calls or GHCR policy checks. All provenance logic lives in the new `rocforge-ci` Python toolkit (`python -m rocforge_ci resolve|verify|update`).
- **Snapshot-driven aggregation** – `TemporalAggregator` now records only `mean_stability`, `stability_variance`, `drift_index`, and `session_count`, copying CI-generated metadata under `build_info` without verifying it.
- **CI redesign** – `.github/workflows/clamp-ci.yml` resolves digests via `rocforge-ci`, stores `build/rocm_snapshot.json`, and passes `-DROCM_SNAPSHOT_JSON` to Clamp’s CMake configuration. Legacy scripts are thin shims around the package.
- **CI verification** – GitHub Actions confirms `smart-bootstrap` emits structured JSON summaries, displays the persisted `.ci_mode` at job start, resets the marker on teardown, and surfaces warnings on mode flips, with no stray snapshots after completion.
- **Canonical ROCm cache** – `rocforge-ci cache-build` produces signed tarballs, records SHA-256 hashes in the matrix, preloads them in CI, and verifies every run before falling back to the `ghcr.io/zerkol83/rocm-dev` mirror or offline metadata.
- **Documentation refresh** – Added `docs/runtime_isolation.md` and updated `docs/ci_integrity_spec.md`, `docs/telemetry_spec.md`, and the README with the runtime vs CI responsibility split.


Clamp v0.4.0 — Distributed Temporal Scoring & Telemetry Aggregation
==================================================================

Release date: 2025-??-??  
Status: Pending validation under Debian 13 + ROCm 6.4.4  
Tag: v0.4.0

Summary
-------

Clamp v0.4 evolves the subsystem into a distributed stability evaluator. Temporal scoring converts anchor telemetry into quantitative reproducibility metrics, while enhanced aggregation APIs capture multi-node entropy behaviour and persist JSON logs for downstream ROCForge analytics.

Status Report
-------------

The telemetry subsystem has been modularized for clarity and reproducibility. The new `include/clamp/EntropyTelemetry.h` defines the core record type and API for entropy session tracking. Its implementation, `src/telemetry/entropy_telemetry.cpp`, captures lock and release events, computes elapsed durations, and aggregates stability scores into a single JSON object written to `build/telemetry/clamp_run_<timestamp>.json` via the `writeJSON` routine.

ClampAnchor now integrates directly with this telemetry layer, emitting deterministic entropy and stability data while maintaining strict RAII semantics. Validation now covers JSON persistence end-to-end: `tests/test_clamp.cpp` verifies file generation and schema correctness, while `tests/test_scoring.cpp` exercises scoring aggregation, temporal alignment, and summary output. Continuous integration preserves runtime artifacts through `.github/workflows/validate.yml`, uploading `clamp_test` and all telemetry exports so every run yields reproducible evidence. Documentation has been synchronized accordingly—`README.md`, `CHANGELOG.md`, and `docs/telemetry_spec.md` reference the schema, field semantics, and reproducibility checks required for v0.4 tagging.

Key Enhancements
----------------

- TemporalScoring module computes stability scores, variance metrics, and drift analysis with JSON and plain-text reporting.
- EntropyTelemetry gains distributed aggregation, timestamp alignment, and filesystem archival capabilities.
- TemporalAggregator consolidates per-run telemetry into `telemetry_summary.json`, exposing `mean_stability`, `stability_variance`, `drift_index`, and `session_count` for downstream analysis.
- Expanded CTest coverage validates scoring, multi-thread entropy reproducibility, and HIP mirroring across aggregated datasets.
- Telemetry schema formally documented in `docs/telemetry_spec.md`, ensuring downstream consumers share a consistent contract.
- GitHub Actions workflow now runs matrix builds with parallel test execution and publishes telemetry artifacts.

Validation Artifacts
--------------------

```
ctest --output-on-failure
cat build/telemetry/*.json | jq '.stability_score'
```

Outlook for v0.5
----------------

- Streaming telemetry ingestion for ROCForge’s global dashboards.
- GPU-resident scoring kernels for on-device reproducibility estimates.
- Automated anomaly detection over archived entropy traces.

Clamp v0.2.0 — Entropy Stabilization and Deterministic RAII Validation
======================================================================

Release date: 2025-10-12  
Status: Validated under Debian 13 + ROCm 6.4.4 (AMD RX 7900 XTX / Ryzen 7 3800X)  
Tag: v0.2.0

Summary
-------

Clamp v0.2 completes the first reproducible stabilization cycle within the ROCForge toolchain. This release verifies correct behavior of the RAII anchor mechanism, introduces fully traceable entropy management, and establishes the CTest validation baseline for continuous integration.

Technical Highlights
--------------------

Deterministic Entropy Lifecycle

- Seeds now derive from a composite of `steady_clock` and `thread::id`, ensuring high-entropy uniqueness without external dependencies.
- Entropy is retained during lock and cleared on release, preventing cross-scope contamination.
- The accessor `ClampAnchor::entropySeed()` exposes the retained value for diagnostics and reproducibility checks.

RAII Integrity Validation

- Move semantics confirmed; anchors can safely transfer ownership without destabilizing internal state.
- Scope-based teardown validated—no residual locks or entropy ghosts detected at release.
- Full assert coverage across lock/unlock sequences.

State Machine and Logging

- Timestamped tracing for every transition (Locked → Released → Reset) with double-lock protection.
- Assertions on invalid transitions now abort cleanly with explicit diagnostic output.

Testing and Build Environment

- All tests compiled and executed under Ninja + CMake 3.30 with ROCm HIP 6.x and rocBLAS 4.4.1.
- `ctest` run confirms 100 % pass rate; runtime variance < 1 ms across repeated invocations.
- The CMake skeleton remains static since v0.1, preserving reproducibility of the build graph.

Validation Results

```
Test project /home/zerkol/Dev/rocforge/clamp
1/1 Test #1: clamp_test ............ Passed 0.00 sec
100% tests passed, 0 tests failed out of 1
```

Outlook for v0.3
----------------

Next cycle will introduce:

- Formal entropy diagnostics export (JSON/telemetry endpoint).
- GPU-side anchor verification under HIP kernels.
- Integration with ROCForge Vector Field Architecture.
- Continuous integration via GitHub Actions (CTest + ROCm container).
