# Clamp Runtime Isolation

Clamp v0.5+ operates as a hermetic runtime component. All network access, GHCR
policy evaluation, and provenance verification live in the external
**ROCForge-CI** toolchain.

## Responsibilities

| Layer         | Responsibilities                                                                    |
|---------------|--------------------------------------------------------------------------------------|
| rocforge-ci   | Resolve ROCm container digests, verify matrix/policy compliance, update metadata.   |
| Clamp runtime | Execute HIP validation kernels, collect telemetry, aggregate stability metrics.     |

## Runtime View

1. **Before build** the CI pipeline runs `python3 -m rocforge_ci resolve` to produce
   `build/rocm_snapshot.json`. This snapshot includes the resolved image reference,
   digest, policy mode, and signer (if any).
2. Clamp's CMake configuration receives `-DROCM_SNAPSHOT_JSON=build/rocm_snapshot.json`.
3. During aggregation the runtime reads the snapshot and simply records the metadata
   in `telemetry_summary.json` under `build_info`. No network requests are performed.

This separation allows the runtime to remain reliable and reproducible in offline
environments, while CI tooling can evolve independently (cosign verification,
auto-update policies, provenance attestations, etc.).
