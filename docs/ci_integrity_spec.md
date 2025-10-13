# Clamp CI Container Integrity Specification

This document describes how Clamp validates and maintains the ROCm container matrices used for all automation.

## Components

| Component | Purpose |
|-----------|---------|
| `ci/rocm_matrix.yml` | Canonical catalog of ROCm container images (version, OS, digest, discovery date). |
| `ci/rocm_policy.yml` | Enforcement policy (strict / warn / auto_update), digest TTL, signature requirements (`require_signature`), and attestation handling (`attest_mode`). |
| `ci/resolve_rocm.py` | Selects the preferred container according to policy ordering and emits a digest-qualified reference. |
| `ci/verify_rocm_digest.py` | Validates the selected image’s digest against GHCR and the recorded matrix value. |
| `ci/update_rocm_matrix.py` | Discovers new ROCm tags and records their digests for review. |
| `.github/workflows/update-rocm.yml` | Weekly automation that runs the updater script and opens a PR with refreshed matrix data. |

## Resolver → Verifier Flow

1. **Resolver** reads the matrix and policy to determine the ordering of candidate tags (preferred OS, default fallback).
2. The resolver inspects GHCR manifests and emits `ghcr.io/rocm/dev:<version>-<os>@<digest>` as a step output.
3. **Verifier** consumes this reference, loads `ci/rocm_policy.yml`, and performs three checks:
   - The recorded digest in `ci/rocm_matrix.yml` must match both the resolver digest and the current GHCR manifest digest (`Docker-Content-Digest`).
   - The digest age (derived from `added`) must be less than the configured TTL (days).
   - On mismatch, behaviour depends on policy mode:
     - `strict`: fail the workflow (exit code `2`).
     - `warn`: emit a warning but continue (exit code `1`).
     - `auto_update`: trigger `update-rocm.yml` via the GitHub API, warn, and continue (exit code `1`).

Exit codes: `0 = OK`, `1 = warning`, `2 = failure`. The CI step wraps the script to propagate warnings as `::warning::` annotations while still gating failures.

## Digest Refresh Rules

- `ci/rocm_policy.yml` defines `digest_ttl` (default 7 days). Digests older than the TTL raise a warning to prompt review.
- The weekly updater workflow fetches GHCR tags for the configured OS (`ubuntu-22.04` today), records new entries with the current date, and requests a PR.
- Developers can trigger the workflow manually (`workflow_dispatch`) when a new ROCm release is published.

## Self-Healing Flow

```
          ┌────────────────────┐
          │  clamp-ci resolve  │
          └─────────┬──────────┘
                    │ image@digest
                    ▼
          ┌────────────────────┐
          │  verify_rocm_digest│
          └─────────┬──────────┘
            match    │   drift/ttl breach
            (OK)     │
                    ▼
          ┌────────────────────┐
          │policy auto_update? │
          └──────┬─────┬───────┘
                 │yes  │no
                 │     ▼
                 │  warn/fail per mode
                 ▼
      GitHub Actions API dispatch
                 │
                 ▼
  update-rocm.yml creates refresh PR
```

When `on_mismatch: auto_update` (policy mode `auto_update`) is active, any digest drift automatically dispatches `.github/workflows/update-rocm.yml` using the CI token. The workflow creates or updates the “Auto-update ROCm matrix” PR with refreshed digests, closing the loop without manual intervention. Strict/warn modes behave as before.

### Sample `rocm_provenance.json`

```json
{
  "image": "ghcr.io/rocm/dev:6.4.4-ubuntu-22.04@sha256:79aa4398…",
  "policyMode": "strict",
  "requireSignature": true,
  "attestMode": "record",
  "provenance": {
    "status": "verified",
    "issuer": "sigstore",
    "timestamp": "2025-01-01T00:00:00Z",
    "digestAlgorithm": "sha256",
    "policyDecision": "mode=strict|require_sig=true|attest=record|status=0",
    "trustStatus": "valid"
  }
}
```

## Workflow Interaction

- **clamp-ci**: resolves the container, verifies digest integrity, and only schedules build jobs when the policy passes. Warnings are surfaced in the log but do not block unless the policy is `strict`.
- **update-rocm**: runs on a schedule; when the verifier detects digest drift and policy is `auto_update`, it dispatches this workflow via the GitHub API.

## Future Enhancements

- Multi-OS comparison for drift (e.g., verifying both Ubuntu 22.04 and 24.04 digests simultaneously).
- Slack/Webhook notifications when the verifier downgrades to warning or triggers auto-update.
- Extended metadata (e.g., ROCm release notes URL) to accompany matrix entries.
