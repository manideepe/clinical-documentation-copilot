# Contributing

Contributions should preserve four non-negotiable properties: the newest active
treatment plan is authoritative, expired plans block audio and generation, model
output is grounded in supplied facts, and a clinician must review and approve
before completion.

1. Create a focused branch.
2. Add tests for expected behavior and denied behavior.
3. Run `make verify` from the repository root.
4. Never commit PHI, recordings, secrets, local databases, or generated raw data.
5. Document security and clinical-safety implications in the pull request.

Clinical content changes require review by an appropriately qualified clinical
and compliance stakeholder. Software tests do not establish clinical validity.
