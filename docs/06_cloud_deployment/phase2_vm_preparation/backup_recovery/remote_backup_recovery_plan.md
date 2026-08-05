# Remote Backup and Recovery Validation Plan

## Objective

Validate that PostgreSQL and MinIO data can be backed up, verified, restored, and audited on the authorized UESTC virtual machine.

## PostgreSQL validation

- Record the database name, PostgreSQL version, timestamp, and Git commit hash.
- Create a custom-format backup with pg_dump.
- Record the archive size and SHA-256 checksum.
- Restore the archive into a separate temporary database.
- Verify the Alembic revision, expected tables, and row counts.
- Confirm that the original production database remains unchanged.

## MinIO validation

- Record the source bucket, object count, total size, and timestamp.
- Copy the authorized objects to a protected backup location.
- Calculate SHA-256 checksums.
- Restore the objects into a temporary validation bucket.
- Compare object names, sizes, and checksums.
- Confirm that the original bucket remains unchanged.

## RPO and RTO measurement

- Measure RTO from the declared recovery start time until the restored service passes validation.
- Derive RPO from the timestamp of the newest recoverable data.
- Preserve automatic timestamps wherever possible.
- Do not report estimates as measured values.

## Required evidence

- Backup and restore commands
- Start and end timestamps
- Archive sizes and checksums
- Table and row-count comparisons
- MinIO object comparisons
- Application health after restoration
- Errors and corrective actions

## Security requirements

- Do not commit healthcare backup archives to GitHub.
- Do not expose passwords in commands or documentation.
- Record whether backups are local, off-host, and encrypted.

## Status rule

Remote recovery results remain pending until these procedures are executed and verified on the authorized VM.
