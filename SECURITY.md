# Security policy

## Scope and deployment warning

This repository is a reference implementation evaluated only with synthetic
data. It demonstrates security controls, but it is not certified and must not
be used with protected health information (PHI) without an organization-specific
risk analysis, legal review, hardened deployment, vendor agreements, incident
response program, workforce controls, and validation of every safeguard.

## Reporting a vulnerability

Do not open a public issue containing secrets, PHI, exploit details, or personal
data. In a real deployment, configure a private security contact in the GitHub
Security tab and publish a supported disclosure address before launch.

## Production readiness gates

- Replace demo authentication with an approved OIDC/SMART-on-FHIR identity flow.
- Store encryption keys in a managed secret system and rotate them.
- Require TLS 1.2 or later at every network boundary.
- Use an encrypted, backed-up database with least-privilege service identities.
- Disable raw recording retention by default and document any approved exception.
- Forward immutable audit events to monitored security storage.
- Add malware scanning, content limits, and quarantine for any upload path.
- Run threat modeling, penetration testing, dependency review, disaster recovery
  exercises, and privacy/security risk assessments before handling PHI.
- Confirm business associate agreements and data-use terms for every processor.

## Supported versions

This educational release has no production support commitment. Pin dependencies,
apply security updates, and perform a fresh risk assessment for every deployment.
