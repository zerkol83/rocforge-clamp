# Phase 4 Implementation Plan — Provenance & Trust Anchoring

## Overview
Phase 4 upgrades Clamp’s ROCm integrity layer to perform cryptographic provenance verification, propagate attestation data, and surface trustworthy telemetry. Tasks are grouped by discipline with suggested owners; adjust according to team capacity.

## Workstream Breakdown

### 1. Verifier Enhancements (Owner: Integrity Engineer)
- Integrate `cosign` CLI (or Python SDK) into `ci/verify_rocm_digest.py`.
- Implement signature verification pipeline:
  - Resolve expected signer metadata from matrix/policy.
  - Execute `cosign verify` with key / OIDC options.
  - Parse Sigstore bundle JSON for subject, issuer, log index, timestamp.
  - Introduce exit code `3` for signature failures when `require_signature` is active.
- Emit provenance summary to stdout and attach to telemetry handoff.
- Retry on transient network issues; respect policy fallback for warn / auto-update.

### 2. Policy & Matrix Extensions (Owner: Release Engineering)
- Extend `ci/rocm_policy.yml` with:
  - `require_signature` (bool / per-image override support).
  - `attest_mode` (values: `none`, `record`, `enforce`).
- Expand `ci/rocm_matrix.yml` rows with optional `provenance` metadata (expected key fingerprint, identity regex).
- Update updater workflow to populate provenance fields when new images are discovered.

### 3. CI Artifact Generation (Owner: DevOps)
- Modify `.github/workflows/clamp-ci.yml` to archive `rocm_provenance.json` containing verification output.
- Ensure artifact includes per-image issuer, attestation hash, policy decision, timestamps.
- Plumb environment variables (OIDC token, cosign path) safely into jobs.

### 4. Telemetry & CLI Updates (Owner: Telemetry Engineer)
- Extend telemetry collector schema to store:
  - Signature issuer
  - Verification timestamp
  - Digest hash algorithm
  - Policy decision path
  - Trust status (`valid`, `unsigned`, `expired`)
- Update `telemetry_inspect` to display provenance status.
- Provide sample JSON and adjust aggregators/tests accordingly.

### 5. Testing (Owner: QA / Automation)
- Unit tests for verifier:
  - Verified signature
  - Unsigned image (warn/fail depending on policy)
  - Invalid signature / expired cert.
- Integration test (`tests/test_phase4_end2end.py`) signs a dummy container via `cosign`, injects entries, runs verifier in `strict` and `warn` modes, and asserts telemetry output & exit codes.
- Mock cosign failure modes for deterministic CI.

### 6. Documentation (Owner: Technical Writer)
- Update README with provenance enforcement summary and link to detailed docs.
- Author `docs/provenance_overview.md` including mermaid flow diagram (Developer → GHCR → Cosign → Clamp → Telemetry → Report).
- Cross-link `docs/Clamp_Integrity_v4_Spec.md` and update CHANGELOG.

## Acceptance Criteria
1. **Signature Enforcement**: `ci/verify_rocm_digest.py` exits with code `3` when signatures are required but invalid/missing; policies `warn` and `auto_update` downgrade severity as specified.
2. **Policy Support**: `ci/rocm_policy.yml` recognizes `require_signature` and `attest_mode`; toggling values changes verifier behavior without code modifications.
3. **Provenance Artifact**: `rocm_provenance.json` is generated in CI, uploaded as an artifact, and consumed by telemetry to annotate summaries.
4. **Telemetry Integration**: Summary JSON objects include provenance fields, and CLI tools display trust status.
5. **Test Coverage**: New unit/integration tests pass locally and in CI (including mocked cosign scenarios).
6. **Documentation**: README, integrity spec, and provenance overview describe workflows, policies, and failure codes.

## Failure Codes
| Exit Code | Meaning | Action |
|-----------|---------|--------|
| `0` | Digest & signature verified / policy satisfied | Continue build |
| `1` | Warning (e.g., TTL expiry, unsigned allowed in warn mode) | Log + continue |
| `2` | Digest mismatch (existing behavior) | Fail in strict mode / warn otherwise |
| `3` | Signature verification failure (`require_signature` true) | Fail unless policy downgrades |

## Timeline & Dependencies
- Week 1: Verifier + policy updates
- Week 2: Telemetry & CI artifact integration
- Week 3: Testing harness, end-to-end signing workflow, documentation
- Week 4: Review, stabilization, hand-off to Phase 5 planning

## Transition Criteria to Phase 5
- Automated provenance validation in place with passing tests.
- Documentation published and referenced in CHANGELOG.
- Auto-update workflow captures provenance metadata.
- Review sign-off from DevOps, Security, Telemetry owners confirming readiness for multi-signer chains and SBOM integration in Phase 5.
