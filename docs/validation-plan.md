# Verification and validation plan

## Evidence philosophy

Every high-risk rule needs both a success test and a denial test. A passing user
interface test alone is insufficient because a caller may bypass the interface;
the same policy must be enforced by the API and domain layer.

## Test matrix

| ID | Layer | Scenario | Expected evidence |
|---|---|---|---|
| WF-01 | Domain/API | Active plan, 6-7 bullets, supported note type | Draft references selected current plan and supplied facts |
| WF-02 | Domain/API | Expired plan, bullet workflow | Facts saved unchanged; documentation pending |
| SAFE-01 | Domain/API/UI | Expired plan, start recording | Control disabled and request rejected before audio handling |
| SAFE-02 | Domain/API | Expired plan, direct upload attempt | 4xx denial; no file or transcript created |
| SAFE-03 | Generator | Missing progress | No invented improvement; explicit documentation-needed marker |
| SAFE-04 | Generator | Unsupported diagnosis in malicious input | No new diagnosis introduced by generator |
| PLAN-01 | Domain | Multiple active/historical plans | Newest currently effective plan selected deterministically |
| PLAN-02 | Domain | New plan activates after pending appointment | Original facts unchanged; generated draft uses new plan |
| SYNC-01 | Domain/API | Same EHR client synced twice | Single local record; update is idempotent |
| STATE-01 | Domain/API | Complete without approval | Denied |
| STATE-02 | Domain/API | Edit completed appointment | Denied; revision history unchanged |
| RBAC-01 | API | Each role versus protected operations | Permission matrix enforced, deny by default |
| NOTE-01 | Templates | Eight note types | Unique schema, required fields, instructions, and formatting |
| DATA-01 | Data | Official Synthea archive | Source receipt and archive checksum recorded |
| DATA-02 | Data | Record scale | Header-excluded total >= 1,000,000 |
| PERF-01 | API | Repeated read/generation requests | Latency distribution recorded, no safety bypass |
| UI-01 | Browser | Active-plan end-to-end path | Screenshot and accessible state labels |
| UI-02 | Browser | Expired-plan path | Screenshot shows disabled voice and pending explanation |
| DOC-01 | PDF | 20-25 page research report | Page count, metadata, text extraction, visual render inspection |

## Release gates

- All automated tests pass with no unexpected skips.
- Dataset manifest proves the threshold and includes hashes.
- No secrets, recordings, database files, or raw data are tracked.
- The UI builds with no TypeScript errors.
- The API starts and its health endpoint responds.
- The PDF has 20-25 pages and every rendered page is visually reviewed.
- Known limitations and deployment obligations are prominent.

## Clinical validation boundary

The repository tests workflow correctness and grounding mechanics. It does not
establish that generated content is clinically adequate. Before real use, a
qualified review panel must define representative cases, blinded scoring rubrics,
acceptable error limits, escalation rules, and post-deployment monitoring.
