# Research and evidence notes

Access date for every web source in this note: **2026-07-15**.

## Scope and evidence rule

These notes support the benchmark, interoperability, security, privacy, and AI-risk decisions for the Clinical Documentation Copilot. Claims are limited to primary sources maintained by MITRE/Synthea, HL7, SMART Health IT, HHS, NIST, and PhysioNet. `references.json` is the machine-readable source register.

This is engineering research, not legal or clinical advice. A repository can demonstrate controls and an architecture can support HIPAA-aligned safeguards; neither the source code nor an architecture diagram can, by itself, be declared “HIPAA compliant.” HHS requires regulated entities to perform risk analysis and risk management, implement administrative, physical, and technical safeguards, evaluate those safeguards over time, and manage business-associate relationships. HHS also says it does not recognize private Security Rule certifications as relieving those obligations ([HHS-01](https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html), [HHS-02](https://www.hhs.gov/hipaa/for-professionals/security/guidance/guidance-risk-analysis/index.html), [HHS-05](https://www.hhs.gov/hipaa/for-professionals/faq/2003/are-we-required-to-certify-our-organizations-compliance-with-the-standards/index.html)).

## Decision summary

1. **Primary unrestricted benchmark: Synthea.** Synthea creates realistic but not real longitudinal patient histories and exports CSV, FHIR R4, Bulk FHIR, and C-CDA. Its official site describes generated records as free from cost, privacy, and security restrictions ([SYN-01](https://synthetichealth.github.io/synthea/), [SYN-02](https://github.com/synthetichealth/synthea)).
2. **Preferred scale method: reproducible local generation.** Pin an exact Synthea release or commit, fixed random and clinician seeds, reference date, geography, and exporter configuration. Generate CSV for scale/integrity tests and FHIR R4 for adapter/conformance tests. Synthea's CLI accepts `-p populationSize`; CSV export is configurable ([SYN-02](https://github.com/synthetichealth/synthea), [SYN-06](https://github.com/synthetichealth/synthea/wiki/CSV-File-Data-Dictionary)).
3. **Independent scale evidence exists.** MITRE provides 21 GB and 28 GB SyntheticMass archives, each described as containing one million synthetic patient medical records in FHIR, C-CDA, and CSV. Those archives date from 2017 and use pre-R4 FHIR, so they are evidence of scale or a legacy stress fixture—not the preferred R4 interoperability fixture ([SYN-03](https://synthea.mitre.org/downloads)).
4. **“One million rows” must be verified, not inferred.** Patient count, clinical-fact row count, and total CSV row count are separate metrics. The acceptance artifact must publish all three, with headers excluded and tables enumerated.
5. **MIMIC-IV is intentionally excluded.** MIMIC-IV v3.1 is restricted to credentialed users who complete training and sign its Data Use Agreement; it is unsuitable for an unrestricted, GitHub-ready data bundle ([MIMIC-01](https://physionet.org/content/mimiciv/3.1/)).
6. **Interoperability baseline: FHIR R4 plus SMART App Launch 2.2.** The adapter must discover each EHR's capabilities; FHIR servers choose supported resources and interactions and publish them in `CapabilityStatement`. SMART supplies launch and OAuth authorization conventions, but institutional authorization policy remains an EHR responsibility ([FHIR-01](https://hl7.org/fhir/R4/http.html), [SMART-01](https://hl7.org/fhir/smart-app-launch/STU2.2/app-launch.html)).
7. **Clinical control remains human.** Generated notes are drafts. A clinician must be able to edit every field and must review and approve before copy/export. NIST identifies confident false output (“confabulation”) as a generative-AI risk and recommends documented pre-deployment testing, provenance, human oversight, ongoing monitoring, and incident handling ([NIST-03](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)).

## Dataset selection, scale, and licensing

### Synthea fitness

Synthea is appropriate for public engineering demonstrations because it simulates complete longitudinal records rather than redistributing real patient records. The current project documents formats including FHIR R4, Bulk FHIR NDJSON, CSV, and C-CDA. The CSV dictionary describes separate relational tables for patients, encounters, care plans, conditions, medications, observations, procedures, claims, and other facts ([SYN-02](https://github.com/synthetichealth/synthea), [SYN-06](https://github.com/synthetichealth/synthea/wiki/CSV-File-Data-Dictionary)).

Synthetic realism is not clinical validation. Synthea should test ingestion, identity rules, workflow state, referential integrity, performance, security boundaries, and deterministic AI safeguards. It must not be presented as evidence of clinical efficacy, diagnostic accuracy, population representativeness for every deployment, or real-world time savings. The eight organization-specific note templates and expired-treatment-plan workflow require curated synthetic test cases in addition to generic Synthea histories.

### Recommended reproducible scale protocol

Use the following acceptance protocol rather than treating “record” as an undefined word:

- Pin the Synthea version/commit, Java version, seeds, reference date, geography, module set, and complete exporter configuration in a manifest.
- Enable CSV and FHIR R4. Keep raw generator output immutable; derive smaller test fixtures separately.
- Run a pilot population, measure rows per patient, then increase `-p` in deterministic shards until the clinical-fact threshold is passed. Shard identifiers and seeds must be non-overlapping and recorded.
- Parse CSV with a standards-aware CSV reader. Do not use physical line count if embedded newlines are possible.
- Report `patient_count = data rows in patients.csv`.
- Report `clinical_fact_rows` as the sum of data rows in an explicit allowlist: `allergies`, `careplans`, `conditions`, `devices`, `encounters`, `imaging_studies`, `immunizations`, `medications`, `observations`, `procedures`, and `supplies`.
- Report `all_csv_rows` as the sum of data rows in every exported CSV table. Never count headers.
- Require `clinical_fact_rows >= 1,000,000`; report the patient count alongside it so one million rows is not misrepresented as one million patients.
- Verify primary-key uniqueness where a table declares a key; patient foreign keys; encounter foreign keys where present; parseability; expected table set; null policy; and valid date ordering.
- Publish per-file byte size, data-row count, and SHA-256 digest plus aggregate counts in a machine-readable evidence artifact.
- Keep the large generated dataset out of normal Git history. Commit scripts, configuration, manifests, checksums, a small deterministic fixture, and instructions. Distribute large artifacts only through a storage mechanism whose terms and access controls have been reviewed.

The legacy MITRE million-patient archive is an optional scale fixture. If used, label it clearly as a 2017 SyntheticMass dataset and do not claim it proves FHIR R4 compatibility ([SYN-03](https://synthea.mitre.org/downloads)).

### License and redistribution caveats

- The Synthea software repository is Apache License 2.0. Redistribution obligations include providing the license, retaining applicable notices, marking modified files, and preserving the repository's `NOTICE` attribution where required ([SYN-04](https://raw.githubusercontent.com/synthetichealth/synthea/master/LICENSE)).
- MITRE's download page states that the generated SyntheticMass data is free from cost, privacy, and security restrictions ([SYN-03](https://synthea.mitre.org/downloads)).
- Do not translate that statement into “every embedded terminology is public domain.” Synthea's `NOTICE` identifies separate terms and attribution for LOINC and SNOMED CT; RxNorm material is identified there as public domain. Preserve the notice and review terminology redistribution for the target jurisdiction and use ([SYN-05](https://raw.githubusercontent.com/synthetichealth/synthea/master/NOTICE)).
- “Synthetic” does not excuse weak production controls. Once the application processes real ePHI, the production data path, backups, logs, clipboard, transcripts, recordings, prompts, outputs, and vendor telemetry are in the system risk analysis.
- MIMIC-IV files and derived sensitive artifacts must not be added. Its official access page requires credentialing, training, and a signed DUA ([MIMIC-01](https://physionet.org/content/mimiciv/3.1/)).

## Interoperability architecture notes

FHIR is the exchange model, not the application's entire workflow engine. Organization-specific statuses, note schemas, expiration rules, approval gates, and immutable bullet-point behavior should be enforced in the application domain and mapped to FHIR only where the receiving EHR supports the relevant profile and operation.

| Project concern | Standards-aligned representation | Boundary/caveat |
|---|---|---|
| Client identity and synchronization | FHIR `Patient`; retain source system, identifier system/value, source resource id, and version metadata ([FHIR-02](https://hl7.org/fhir/R4/patient.html)) | A FHIR `Patient` resource is an organization-specific record, not a universal person identifier. Deduplicate by configured authoritative identifiers; never merge on name alone. Respect `Patient.link` and source updates. |
| Treatment plan and goals | FHIR `CarePlan` with referenced `Goal` resources where the EHR profile supports them ([FHIR-03](https://hl7.org/fhir/R4/careplan.html)) | “Newest active plan” is a project policy, not a universal FHIR rule. Filter to accepted active statuses, validate the effective period, apply a deterministic source timestamp/version tie-break, and persist the exact selected snapshot. |
| Scheduled and delivered care | FHIR `Appointment` for scheduling where supported; `Encounter` for the delivered interaction ([FHIR-04A](https://hl7.org/fhir/R4/appointment.html), [FHIR-04](https://hl7.org/fhir/R4/encounter.html)) | Project states such as `DOCUMENTATION_PENDING` do not map one-to-one to Encounter status. Keep an explicit application state machine and a documented mapping. |
| Clinical note package | FHIR `Composition` as the note structure inside a document `Bundle` ([FHIR-05](https://hl7.org/fhir/R4/composition.html)) | A `Composition` alone is not a FHIR document. Do not claim direct-write support until the target EHR profile, note type codes, API scopes, validation, and write operation are proven. Copy-to-clipboard remains a user-mediated fallback. |
| Note and input lineage | FHIR `Provenance` plus internal immutable version records ([FHIR-06](https://hl7.org/fhir/R4/provenance.html)) | Record the selected plan version, input hash, transcript/bullet snapshot hash, model, prompt, template, output, editor, approval, and timestamps. Provenance is not a substitute for security logging. |
| Security-relevant activity | FHIR `AuditEvent` where supported, plus append-only application/security logs ([FHIR-07](https://hl7.org/fhir/R4/auditevent.html)) | Audit data can itself expose PHI. Restrict access, avoid unnecessary clinical payloads, protect integrity, define retention, and monitor the logs. |
| EHR launch and delegated access | SMART App Launch 2.2 OAuth flow, least-privilege scopes, OpenID Connect identity where needed, and PKCE `S256` ([SMART-01](https://hl7.org/fhir/smart-app-launch/STU2.2/app-launch.html)) | SMART mediates authorization; it does not define the institution's role policy or make an application HIPAA compliant. A browser app cannot safely hold a client secret. |
| Initial and incremental sync | FHIR REST search/history or Bulk Data only when declared by the server; poll or subscribe according to server capability ([FHIR-01](https://hl7.org/fhir/R4/http.html), [FHIR-08](https://hl7.org/fhir/uv/bulkdata/export.html)) | Read `CapabilityStatement`, use pagination and conditional/version-aware updates, make ingestion idempotent, preserve tombstone/deactivation behavior, retry safely, and reconcile periodically. |

### Active-treatment-plan invariant

The generation transaction should fail closed unless it can atomically bind to one selected plan snapshot:

1. Fetch supported CarePlans for the patient from the authoritative source.
2. Normalize status and effective period using the deployment mapping.
3. Select only a currently active plan; use deterministic version/timestamp tie-breaks and reject unresolved ambiguity.
4. Persist source resource id, `meta.versionId`/last-update metadata when available, effective period, goals/objectives, and a content hash.
5. Recheck the selected version at generation time or execute under a consistency mechanism.
6. If the plan is expired/missing/ambiguous, reject audio capture and AI generation; permit only the defined text bullets and pending state.
7. When a new plan becomes active, generate from the immutable saved bullets plus the new plan snapshot. Never rewrite the saved bullets.

The standard allows CarePlans to represent active plans but does not decide which of several active records is authoritative. That decision must be explicit, tested, and agreed with the EHR owner ([FHIR-03](https://hl7.org/fhir/R4/careplan.html)).

## Security and HIPAA-alignment notes

The current HHS Security Rule summary—not a proposed rule—is the compliance baseline referenced here. It requires regulated entities to protect the confidentiality, integrity, and availability of ePHI with reasonable and appropriate administrative, physical, and technical safeguards. Risk analysis covers all ePHI an organization creates, receives, maintains, or transmits and must be revisited as systems and risks change ([HHS-01](https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html), [HHS-02](https://www.hhs.gov/hipaa/for-professionals/security/guidance/guidance-risk-analysis/index.html)). NIST SP 800-66 Rev. 2 is an implementation resource and maps Security Rule provisions to NIST controls; it does not replace the regulation ([NIST-01](https://csrc.nist.gov/pubs/sp/800/66/r2/final)).

Required deployment evidence should include:

- an inventory and data-flow diagram covering ePHI in the EHR adapter, database, object/audio storage, transcription, prompts, model service, logs, backups, clipboard, exports, support tooling, and disaster recovery;
- documented risk analysis, remediation ownership, residual-risk acceptance, and periodic technical and non-technical evaluation;
- unique identities, strong authentication, least-privilege role/attribute checks, authorization at every object boundary, workforce lifecycle procedures, and emergency-access policy;
- encryption in transit and at rest with documented key ownership, rotation, recovery, and separation; encryption is one safeguard and does not replace integrity, availability, contingency planning, or administrative controls;
- append-only/tamper-evident audit trails for access, generation, edit, approval, copy/export, failed authorization, template change, configuration change, and deletion, with log review and alerting procedures;
- backups, restoration tests, availability objectives, incident response, breach assessment/notification procedures, retention schedules, secure disposal, vulnerability/patch management, and tested session termination;
- minimum-necessary data selection for uses/disclosures where the standard applies, and a documented reason when a complete record is needed ([HHS-04](https://www.hhs.gov/hipaa/for-professionals/privacy/guidance/minimum-necessary-requirement/index.html)); and
- vendor and subcontractor due diligence, contracts, and BAAs where a service creates, receives, maintains, or transmits ePHI.

HHS states that a cloud service provider maintaining encrypted ePHI is still a business associate even if it lacks the decryption key. By the same reasoning, routing ePHI through an AI, transcription, logging, monitoring, backup, or hosting provider requires role analysis and, when the provider is a business associate, an appropriate BAA and safeguards. “Zero retention,” “not used for training,” and encryption are useful contractual/technical requirements but are not substitutes for this analysis ([HHS-03](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html)).

Local speech processing can reduce external disclosure paths, but recordings and transcripts remain sensitive in a real deployment. The expired-plan rule must be enforced before microphone activation, upload, processing, or storage—not merely before note generation. Recording consent, professional practice, retention, and state-law requirements require deployment-specific legal review and are outside this federal-source note.

### Wording that is supportable

Use: **“The reference architecture implements controls designed to support HIPAA-aligned deployment. Actual compliance depends on the regulated entity's deployment, risk analysis, policies, workforce practices, vendor relationships/BAAs, configuration, and ongoing evaluation.”**

Do not use: **“This software is HIPAA compliant,” “HIPAA certified,” or “encryption makes the system compliant.”** HHS does not endorse or certify particular technologies, and an external certification does not prevent HHS from finding a violation ([HHS-03](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html), [HHS-05](https://www.hhs.gov/hipaa/for-professionals/faq/2003/are-we-required-to-certify-our-organizations-compliance-with-the-standards/index.html)).

## Generative-AI safeguard evidence

NIST AI RMF 1.0 is a voluntary, lifecycle risk-management framework organized around Govern, Map, Measure, and Manage. The NIST Generative AI Profile extends it with GAI-specific risks and actions. It defines confabulation as confidently presented erroneous or false content and emphasizes governance, content provenance, pre-deployment testing, and incident disclosure ([NIST-02](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf), [NIST-03](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)).

For this high-consequence documentation aid, implement and test:

- **Grounded input contract:** the model receives only the selected active-plan snapshot, appointment metadata, selected template/version, and immutable bullets or transcript. No previous inactive plans enter the prompt.
- **Source preservation:** store the clinician's bullets exactly as entered; do not let generation overwrite them. Keep transcript and speaker labels separate from the derived note.
- **Schema and rule validation:** validate required sections, allowed note type, field lengths, forbidden unsupported diagnoses/quotes/interventions, placeholder behavior, and treatment-goal references before presenting a draft.
- **Fact trace:** associate generated fields or claims with source spans/identifiers where feasible. Unsupported statements are removed or converted to an explicit “additional documentation required” placeholder.
- **Human authority:** label output as AI-generated draft, allow complete editing, require authenticated clinician review and approval, and prohibit autonomous EHR submission.
- **Versioned provenance:** record model/provider/version, system prompt, note-template version, decoding/configuration, input/output hashes, safety decisions, latency, editor changes, approval, and export event without duplicating unnecessary PHI into logs.
- **Pre-deployment TEVV:** test correct plan selection, expired-plan hard gate, plan-change recovery, insufficient audio, diarization errors, prompt injection in transcripts, omitted facts, unsupported diagnoses, invented quotes, invented progress, wrong note type, bias slices, unauthorized access, and fail-safe behavior.
- **Quantitative release gates:** define denominators and thresholds for unsupported-statement rate, critical omission rate, plan-selection accuracy, template validity, prohibited-content escapes, reviewer edit distance, and inter-rater agreement. A passing general benchmark is not a substitute for representative clinical workflow tests.
- **Ongoing monitoring:** sample approved/edited drafts under an authorized quality process; track overrides, near misses, user reports, drift after model/prompt/template changes, and security events. Maintain rollback and disable-generation controls.
- **Incident process:** retain enough versioned evidence to reconstruct a harmful output, triage it, notify responsible parties as required, remediate, and test recurrence prevention.

NIST warns that laboratory or anecdotal tests may not extrapolate to deployment conditions. Results should therefore be described as evidence within defined test conditions—not proof that hallucinations are impossible or that the system is clinically safe in every environment ([NIST-03](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)).

## Claims to avoid in project materials

- “Synthea contains real patient records.” It generates synthetic, realistic-but-not-real records.
- “One million rows means one million patients.” Publish both measures.
- “The 2017 million-patient download validates FHIR R4.” Its listed FHIR versions predate R4.
- “Synthetic data guarantees clinical validity or fairness.” It is an engineering benchmark, not deployment evidence by itself.
- “FHIR guarantees that every EHR supports these reads/writes.” Inspect `CapabilityStatement`, profiles, scopes, and vendor implementation behavior.
- “SMART scopes implement the organization's complete role model.” SMART provides authorization conventions; institutional policy remains separate.
- “No training” or “zero retention” means an AI vendor is not a business associate. Business-associate status depends on creating, receiving, maintaining, or transmitting ePHI on behalf of a regulated entity.
- “Encryption alone provides HIPAA compliance.” HHS requires broader administrative, physical, and technical safeguards plus risk management.
- “Human review eliminates AI risk.” It is a critical control that must be designed, measured, monitored, and supported by fail-safe system behavior.

## Source register

See [`references.json`](./references.json) for titles, publishers, direct URLs, access dates, claims, and caveats for every cited source.
