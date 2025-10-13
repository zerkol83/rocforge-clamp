# Phase 4 Completion Checklist — Provenance & Trust Anchoring

## Feature Readiness
- [ ] `ci/verify_rocm_digest.py` integrates cosign verification, produces `rocm_provenance.json`, and returns exit code `3` for signature failures when `require_signature` is enabled.
- [ ] `ci/rocm_policy.yml` supports `require_signature` and `attest_mode`; matrix entries contain optional `provenance` metadata (key path / identity).
- [ ] `.github/workflows/clamp-ci.yml` uploads provenance artifact and surfaces trust status in logs.
- [ ] Telemetry summaries (`telemetry_summary.json`, CLI) include issuer, verification timestamp, digest algorithm, policy decision, and trust status.
- [ ] Auto-update workflow appends provenance metadata when refreshing digests.

## Testing & QA
- [ ] Unit tests cover verified / unsigned / invalid signature branches (cosign stub).
- [ ] `tests/test_phase4_end2end.py` signs (or stubs) an image, runs verifier in strict & warn modes, and validates telemetry output and exit codes.
- [ ] Telemetry aggregator tests confirm provenance ingestion and CLI display.
- [ ] CI pipelines pass with provenance enforcement enabled (strict policy build).

## Documentation & Communication
- [ ] README updated with provenance enforcement summary and links to detailed docs.
- [ ] `docs/Clamp_Integrity_v4_Spec.md`, `docs/provenance_overview.md`, and `docs/ci_integrity_spec.md` reflect new trust chain, sample artifacts, and policies.
- [ ] CHANGELOG entry summarizes Phase 4 provenance enhancements.

## Review & Sign-off
- [ ] Security/DevOps review cosign integration and key management approach.
- [ ] Telemetry/Analytics confirm provenance fields meet reporting needs.
- [ ] QA signs off on end-to-end tests and failure-mode coverage.

## Exit Criteria for Phase 4
- Provenance verification enforced in CI with automated remediation (auto-update) and telemetry propagation.
- All checklist items checked and approvals recorded in PR review thread.

## Entry Criteria for Phase 5 (Preview)
- Plan for multi-signer chains (e.g., AMD + ROCm release keys) defined.
- SBOM generation/ingestion workflow drafted.
- Telemetry schema prepared to transport SBOM and supply-chain telemetry fields.
- Identified tooling for cosign + SBOM (e.g., syft/grype) prototypes available.
