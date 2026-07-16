# Threat model

## Protected assets

- Client identity and EHR identifiers
- Active and historical treatment plans
- Appointment facts, generated drafts, revisions, and approvals
- Transient audio and transcripts, if the organization enables voice
- Credentials, tokens, encryption material, and session state
- Audit evidence and role assignments

## Trust boundaries

1. Browser to application API
2. Application to EHR/FHIR endpoint
3. Workflow services to persistence
4. Audio capture to local speech processing
5. Generation adapter to any configured inference runtime
6. Application events to monitoring and audit storage

## STRIDE analysis

| Threat | Example | Primary controls | Verification |
|---|---|---|---|
| Spoofing | Reusing another clinician session | OIDC/SMART target, secure cookies, short timeout, reauthentication | Authorization and session tests |
| Tampering | Changing plan ID during generation | Server-side plan selection, immutable source snapshot hash, revision history | Plan-selection and integrity tests |
| Repudiation | Denying approval or export | Actor/time/action audit events, append-only production target | Audit event tests |
| Information disclosure | PHI in logs or error traces | Structured redaction, content-free audit payloads, generic errors | Log scanning and error-path tests |
| Denial of service | Oversized audio or repeated generation | Size/type/duration limits, throttling target, bounded parsing | Boundary/performance tests |
| Elevation of privilege | Counselor managing templates | Central permission matrix, deny by default | Role matrix tests |

## Misuse and clinical-safety cases

| Misuse | Required behavior |
|---|---|
| Attempt voice capture with expired plan | Disable control in UI and reject API request before bytes are accepted |
| Upload audio by bypassing the UI | API rejects using server-resolved plan state |
| Generate from an inactive historical plan ID | Ignore caller-supplied plan choice and select newest active plan |
| Prompt-injection text inside a bullet or transcript | Treat as untrusted clinical text, not instructions; constrain output to schema |
| Missing progress evidence | Use a missing-information marker; never infer improvement or decline |
| New plan activates after facts are saved | Preserve facts byte-for-byte; generate a new draft linked to the new plan |
| Copy unreviewed content | Keep copy/finalize unavailable until explicit review state |
| Modify completed appointment | Reject mutation and retain prior revisions |

## Residual risks

No automated safeguard can establish clinical correctness. Template-based output
can still be incomplete or contextually inappropriate, and a probabilistic model
adds hallucination and automation-bias risks. Human review, clinical governance,
continuous evaluation, incident feedback, and the ability to disable generation
remain mandatory controls.
