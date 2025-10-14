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
- `TemporalAggregator` consolidates telemetry logs under `build/telemetry/`, computes cross-run statistics, and emits `telemetry_summary.json` exposing `mean_stability`, `stability_variance`, `drift_index`, and `session_count`, plus `build_info` copied from the CI-generated `rocm_snapshot.json`.
- ROCm container provenance is resolved and verified by the external ROCForge-CI toolchain; Clamp only records the immutable snapshot in its telemetry summaries. Details live in `docs/ci_integrity_spec.md` and `docs/runtime_isolation.md`.

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

## Runtime vs CI Responsibility

| Layer        | Responsibilities                                                         |
|--------------|---------------------------------------------------------------------------|
| Clamp runtime | HIP validation kernels, entropy telemetry capture, temporal aggregation. |
| ROCForge-CI  | Container resolution, digest/policy verification, provenance generation. |

Clamp consumes the immutable snapshot produced by ROCForge-CI (`rocm_snapshot.json`) but
performs no network or registry access at runtime. See `docs/runtime_isolation.md` for the
full rationale and integration notes.

## Clamp (SNAPI) — capture, restore, verify

Clamp now bundles a lightweight Python SNAPI runtime that exposes three core commands:
`clamp.capture`, `clamp.restore`, and `clamp.verify`. Artifacts land in `build/clamp/` by
default, giving both developers and CI a consistent place to pull manifests and shell
exports from.

### Developer quickstart
1. Capture the current ROCm environment (defaults to `/opt/rocm`):
   ```bash
   python3 - <<'PY'
from engine import bootstrap_extensions
from snapi import dispatch

bootstrap_extensions()
result = dispatch('clamp.capture', {'output_dir': 'build/clamp'})
print(result['message'])
print('manifest:', result['manifest_path'])
print('env script:', result['env_path'])
PY
   ```
2. Source the generated environment before building locally:
   ```bash
   source build/clamp/env.sh
   cmake -S . -B build -G Ninja
   cmake --build build
   ```
3. Verify that the live system still matches the captured manifest:
   ```bash
   python3 - <<'PY'
from engine import bootstrap_extensions
from snapi import dispatch

bootstrap_extensions()
result = dispatch('clamp.verify', {'manifest_path': 'build/clamp/manifest.json'})
print(result['status'], result['message'])
if result.get('mismatches'):
    print('mismatches:', result['mismatches'])
PY
   ```

`clamp.restore` returns both the shell snippet (`shell_hint`) and a key/value map for
programmatic consumers that need to inject variables without sourcing `env.sh`.

### RocFoundry CLI
After `pip install -e .`, the `rocfoundry` command exposes the same Clamp flows via
`snapi.dispatch` under the hood:

```bash
rocfoundry clamp capture /opt/rocm --output build/clamp
rocfoundry clamp verify build/clamp/manifest.json
eval "$(rocfoundry clamp restore build/clamp/manifest.json --apply)"
```

Use `--json` for machine-readable output, `--lenient` to treat verification mismatches
as warnings, and `rocfoundry clamp show build/clamp/manifest.json --summary` to inspect
the captured metadata without editing JSON manually.

### CI integration snapshot
- `python3 -m rocforge_ci smart-bootstrap` now prints whether a Clamp manifest was found
  and records the verification outcome.
- Successful runs emit `build/run.json` with `mode`, `clamp_manifest_path`, and
  `verify_status` so downstream jobs can audit how the environment was prepared.
- `ci/rocm_matrix.yml` accepts an optional `clamp_manifest` field for documentation; the
  CI prefers the live manifest when present.

### Offline CI Bootstrap
In restricted environments without GHCR access, use the fallback matrix and offline flow:

```bash
python3 -m rocforge_ci smart-bootstrap        # auto-detect online vs offline mode
python3 -m rocforge_ci offline-bootstrap    # validates ci/rocm_matrix.yml without network
bash scripts/ci_offline_bootstrap.sh        # convenience wrapper (optional)
python3 -m rocforge_ci diagnostics          # prints environment/DNS/auth status
python3 -m rocforge_ci diagnostics --json   # machine-readable diagnostics
python3 -m rocforge_ci diagnostics --ci     # concise CI log line
```

Dynamic updates (`python3 -m rocforge_ci update …`) should only be run once GHCR access is restored.

Per-command overrides:

```bash
python3 -m rocforge_ci resolve --auto        # choose mode based on diagnostics
python3 -m rocforge_ci resolve --offline     # force fallback, skip manifest checks
python3 -m rocforge_ci verify --auto IMAGE   # verify build snapshot when online
python3 -m rocforge_ci update --auto --os ubuntu-22.04
```

rocforge_ci records the last active mode in `.ci_mode`; if a run switches between offline and online, a warning is emitted (`⚠️ Detected mode change …`) to help spot flapping credentials or network issues.
Use the helper commands to inspect or clear the marker between runs:

```bash
python3 -m rocforge_ci mode show   # prints {"mode": "...", "timestamp": "..."}
python3 -m rocforge_ci mode reset  # removes the marker after CI completion
```

Each invocation of `smart-bootstrap` emits a one-line JSON summary indicating the mode,
timestamp, and snapshot path—ideal for structured CI logs:

```json
{"mode": "offline", "snapshot": "build/rocm_snapshot.json", "timestamp": "2024-07-15T08:32:11Z"}
```

### Canonical ROCm Images

Clamp relies on canonical ROCm base images that are built, hashed, and cached inside this
repository. Use the helper command to generate and record a new image when AMD publishes
a fresh ROCm drop:

```bash
python3 -m rocforge_ci cache-build \
  --release 6.4.4 \
  --os ubuntu-20.04 \
  --canonical rocforge/rocm-dev:6.4.4-ubuntu-20.04 \
  --image ghcr.io/zerkol83/rocm-dev:6.4.4-ubuntu-20.04 \
  --mirror ghcr.io/zerkol83/rocm-dev \
  --push
```

`cache-build` performs the following actions:
- `docker build` of the canonical image using `images/Dockerfile` (or the path supplied via
  `--dockerfile`).
- `docker save` to `images/<tag>.tar.gz` with the compressed artifact hashed and recorded
  in `ci/rocm_matrix.yml`.
- SHA-256 computation of the compressed tarball and matrix update
  (`ci/rocm_matrix.yml`) with the image tag, tarball path, hash, mirror tag, and timestamp.
- Optional push to the mirror namespace (`--push`).

During CI the workflows call `docker load -i images/*.tar.gz` before invoking
`smart-bootstrap`. The resolver first checks for a matching tarball; if it exists and the
hash matches the matrix entry, the run is marked as `mode: local` and no network is
required. When the tarball is absent, the resolver attempts the GHCR mirror
(`ghcr.io/zerkol83/rocm-dev`). Only if both cache and mirror are unavailable does
`smart-bootstrap` fall back to the offline metadata path.

Lifecycle management for ROCm updates:

1. Build the new canonical image with `cache-build`.
2. Commit the updated tarball, matrix metadata, and regenerated snapshot hash.
3. Push the mirror tag and re-run CI to confirm the hash verification passes.
4. Tag the repository (e.g. `v0.4.0`) to lock the verified toolchain.

See `docs/technical_overview.md` for an in-depth discussion of the entropy lifecycle, temporal alignment algorithms, ROCm dependency graph, and stability metrics captured during the v0.4 validation campaign. The telemetry schema and reproducibility guarantees are defined in `docs/telemetry_spec.md`. The container resolver, digest verification pipeline, and update workflows are documented in `docs/ci_integrity_spec.md`.
