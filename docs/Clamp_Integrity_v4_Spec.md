# Clamp Integrity v4 — Provenance & Trust Anchoring

## 1. Scope
Phase 4 extends the existing digest-verification pipeline to ensure every ROCm container image consumed by Clamp CI (and recorded in telemetry artifacts) carries a verifiable provenance trail. The goal is to reject untrusted images, surface signing anomalies, and embed provenance metadata into downstream summaries for auditability.

## 2. Trust Anchors
- **Cosign Public Keys**  
  - Canonical key list distributed via `ci/provenance_keys/` (PEM-encoded).  
  - Keys mapped to ROCm release channels (e.g., `rocm-stable.pub`, `rocm-nightly.pub`).  
  - Rotations tracked with effective dates and fingerprints in the matrix.
- **Sigstore Fulcio**  
  - Fulcio root certificates (PEM bundle) stored locally; updated via weekly cron.  
  - Required when verifying keyless signatures tied to GitHub OIDC identities.
- **GitHub Actions OIDC Tokens**  
  - Resolver job can request ambient OIDC token and pass it to cosign for certificate validation (audience enforced: `sigstore`).
- **Fallback Policy**  
  - If trust anchors unavailable, default to `policy.mode` (strict = fail; warn = log and continue; auto_update = warn + trigger remediation workflow).

## 3. Artifact Flow
```
resolve_rocm.py  ──► image@digest
      │
      ▼
verify_rocm_digest.py (v3) ──► digest + TTL check
      │
      ▼
provenance verifier (v4)
      │
      ├─ cosign verify (keyful & keyless)
      ├─ fetch attestations (SLSA/rekor bundle)
      └─ emit provenance JSON blob
      ▼
telemetry + summary enrichment
```

## 4. Required Metadata per `image@digest`
| Field | Description | Source |
|-------|-------------|--------|
| `version`, `os` | Existing matrix identifiers | `ci/rocm_matrix.yml` |
| `digest` | SHA256 manifest digest | Matrix / GHCR |
| `signature_status` | `verified`, `unverified`, `failed` | Cosign |
| `signer_identity` | Email/URI from certificate SAN | Cosign payload |
| `cert_issuer` | Fulcio issuer | Cosign payload |
| `rekor_log_index` | Rekor transparency log index | Cosign |
| `attestation_type` | e.g., `SLSA`, `in-toto` | Cosign `--certificate-identity-regexp` |
| `attestation_digest` | SHA of attestation bundle | Cosign |
| `verification_timestamp` | RFC3339 timestamp | Verifier runtime |

Matrix entries gain optional `provenance` object, while telemetry summaries embed provenance hash to link runtime data to signed container.

## 5. Signature Verification Logic
1. **Key Selection**  
   - Determine expected signer key from matrix (`provenance.expected_key`).  
   - If absent, fall back to Fulcio keyless verification with identity regex.
2. **Cosign Invocation**  
   - `cosign verify --key <key>|--certificate-identity-regexp <regex> --certificate-oidc-issuer <issuer>`  
   - Provide `--rekor-url` (default Sigstore) and `--bundle` output path.
3. **Validation Steps**  
   - Check exit code; on success parse JSON bundle (signature + attestation).  
   - Ensure `subject` matches `ghcr.io/rocm/dev:<tag>` and digest equality.  
   - Compare signer identity against matrix allow list.
4. **Attestation Handling**  
   - If attestation available, store hash and high-level predicate (SLSA level, build pipeline ID).  
   - Fallback: if no attestation, mark `attestation_type: none`.
5. **Retry & Fallback**  
   - Retry once on transient network failures (HTTP 5xx).  
   - On failure, downgrade/abort per policy:  
     - `strict`: exit non-zero (block CI).  
     - `warn`: annotate warning, continue; mark `signature_status: unverified`.  
     - `auto_update`: warn, dispatch updater, continue.

## 6. Integration Points
- **Verifier Extensions**  
  - `ci/verify_rocm_digest.py` imports provenance helper (e.g., `ci/provenance.py`).  
  - After digest check, call `verify_signature(image_ref, policy)` to obtain structured provenance; attach to result object.
- **Matrix**  
  - `ci/rocm_matrix.yml` gains optional `provenance:` block with expected key fingerprint or certificate identity pattern.
- **Telemetry Schema**  
  - Aggregated summaries include `containerProvenance` with signer, log index, attestation hash.  
  - Per-session telemetry (Phase 2/3) stores `provenanceDigest` aligning runtime data with signed container.
- **Updater Workflow**  
  - When new tags discovered, updater also fetches signatures and populates `provenance` metadata.  
  - Failure to obtain valid signatures triggers PR warnings requesting manual review.

## 7. Operational Considerations
- **Key Rotation**: schedule monthly check verifying stored public keys match upstream release notes; integrate with auto-update PR.  
- **Credential Handling**: `GITHUB_TOKEN` may lack permission for cosign OIDC flows; consider using OpenID Connect token via `ACTIONS_ID_TOKEN_REQUEST_TOKEN`.  
- **Caching**: cosign bundles stored in CI workspace for audit logs; optionally upload as artifacts when verification fails.  
- **Telemetry Impact**: provenance hash propagated so downstream analytics can correlate performance data with specific signed images.

## 8. Next Steps
1. Implement provenance helper module wrapping cosign CLI with retries.  
2. Extend matrix/updater to record expected signer metadata.  
3. Update verifier to call provenance check and respect policy fallback.  
4. Surface provenance fields in telemetry summaries and documentation.  
5. Add tests: mocked cosign output, failure modes, policy permutations.

This specification forms the foundation for Phase 4, ensuring every ROCm container consumed by Clamp has both digest integrity and cryptographic provenance validation.
