# Phase II Evidence Register

## Purpose

Maintain a traceable inventory of every command output, log, screenshot, configuration record, checksum, and experimental result collected on the authorized UESTC VM.

## Evidence naming convention

Use the following format:

YYYY-MM-DD_HHMM_experiment_evidence-type.ext

Example:

2026-08-10_1430_200users_docker-stats.log

## Required metadata for every evidence item

- Evidence identifier
- Collection date and time
- VM hostname
- Git commit hash
- Experiment or validation category
- Workload configuration
- Command or collection method
- Original filename
- SHA-256 checksum
- Storage location
- Verification status
- Notes or anomalies

## Evidence categories

- VM specification and operating-system information
- SSH and firewall verification
- Docker and Docker Compose versions
- Git revision and deployment configuration
- Container status and health
- Application health and authentication
- Security and RBAC validation
- Performance and scalability outputs
- CPU, memory, disk, and network logs
- Endurance-test logs
- PostgreSQL backup and restore evidence
- MinIO backup and restore evidence
- RPO and RTO measurements
- Pricing and cost calculations
- Screenshots and exported figures

## Integrity requirements

- Preserve original raw files without manual modification.
- Calculate SHA-256 checksums after collection.
- Record corrections in a separate note instead of altering raw evidence.
- Do not commit credentials, private keys, production secrets, or healthcare backup data to GitHub.
- Store sensitive evidence only in an authorized protected location.

## Status values

- PENDING: not yet collected
- COLLECTED: file obtained but not independently checked
- VERIFIED: content and checksum confirmed
- INVALID: incomplete, corrupted, or unsuitable evidence
- SUPERSEDED: replaced by a newer verified item without deleting the original record

## Completion rule

A Phase II claim may be marked completed only when its corresponding raw evidence is registered and verified.
