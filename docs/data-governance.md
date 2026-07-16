# Data governance and benchmark provenance

## Dataset decision

The benchmark uses the official MITRE Synthea 10,000-patient COVID-19 CSV
archive. Synthea generates realistic synthetic records and publishes CSV and
FHIR outputs under permissive terms. The pipeline records the upstream URL,
download time, archive checksum, extracted file checksums, and exact data-row
counts.

The current local evidence reports **2,837,098 clinical-fact rows** and
**2,928,115 total rows across 16 CSV relations**, excluding headers. The dataset
contains 12,352 synthetic patients; `observations.csv` is the largest relation
with 1,659,750 rows. The raw data remains outside Git because it is 560 MB after download and
extraction; another reviewer can reproduce it with two commands.

```bash
python3 scripts/download_synthea.py
python3 scripts/profile_dataset.py
```

## Why Synthea instead of MIMIC

MIMIC is valuable research data, but access is credentialed and governed by a
data-use agreement. It is deliberately excluded so this public repository can be
shared, tested, and taught without redistributing restricted data. Synthetic data
does not make the application production-safe; it only removes patient privacy
risk from this benchmark.

## Intended use

- Load and performance testing
- Schema and adapter development
- Repeatable data-quality experiments
- Demonstration fixtures that contain no real patient records

## Observed source-data anomaly

The integrity scan checked 2,878,490 patient references, 2,472,082 encounter
references, 809,029 temporal ranges, and the primary identifiers in four core
tables. All checked references resolved and no duplicate core identifiers were
found. It also identified 67 medication rows whose stop date precedes the start
date, typically by six days. Those upstream synthetic rows are preserved and
reported rather than silently corrected. An operational ingestion pipeline should
quarantine them for review. This is a useful example of why a large, reputable
dataset still requires explicit quality gates.

## Prohibited interpretation

The benchmark is not evidence of population representativeness, clinical
effectiveness, fairness across real groups, or diagnostic validity. It must not be
used to make patient-care decisions.

## Confidential-data substitution guide

When adapting the pipeline to an authorized confidential dataset:

1. Keep the data outside the repository and document its legal basis and owner.
2. Use a controlled workspace with least privilege and approved retention.
3. Replace direct identifiers with governed pseudonyms where the purpose permits.
4. Create a data dictionary and field-level sensitivity classification.
5. Run schema, null, range, uniqueness, temporal, and referential-integrity checks.
6. Prevent samples, screenshots, traces, and failed-test payloads from leaking data.
7. Validate deletion, incident response, access review, and backup controls.
8. Publish only aggregate, disclosure-reviewed evidence.
