# FHIR and SMART integration mapping

## Read synchronization

| Local concept | FHIR R4 target | Notes |
|---|---|---|
| Client | Patient | Use stable issuer-qualified identifiers; avoid name/date-of-birth deduplication alone |
| Staff | Practitioner and PractitionerRole | Resolve organization and permitted service role |
| Appointment | Appointment and Encounter | Appointment plans the visit; Encounter represents performed care |
| Treatment plan | CarePlan | Map lifecycle status, period, goals, activities, and version/provenance |
| Treatment goal | Goal or CarePlan.goal | Preserve references and lifecycle status |
| Final document | DocumentReference/Composition target | Write only after explicit approval and EHR-specific validation |
| Audit event | AuditEvent target | Keep local security audit separate from clinical note content |

## Authorization profile

The production target is SMART App Launch on FHIR R4 with OAuth 2.0/OIDC. The
application requests the minimum resource scopes needed for the user's workflow.
Refresh-token handling, launch context, token audience, issuer discovery, and
PKCE validation belong in the EHR adapter, not in browser application logic.

## Synchronization semantics

- Upsert on issuer plus external identifier.
- Record upstream version and `lastUpdated` for conflict detection.
- Process pages and retries idempotently.
- Treat deletions and inactive status as lifecycle changes, not hard deletion.
- Preserve provenance of every imported plan version.
- Resolve the active plan server-side at generation time.
- Quarantine ambiguous identifiers or multiple equally current plans for review.

## Write-back safety

The default workflow only copies an approved note. Direct write-back is a future
adapter and must implement server capability discovery, conditional writes,
duplicate prevention, provenance, error recovery, reconciliation, and a user-visible
receipt. A network success response alone is not proof that the intended EHR field
was populated correctly.
