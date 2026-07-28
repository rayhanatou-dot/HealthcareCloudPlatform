from datetime import datetime, timezone
from uuid import uuid4

from app.db.session import SessionLocal
from app.models.patient import Patient
from app.services import diagnostic_report_service


def main() -> None:
    db = SessionLocal()

    try:
        patient = (
            db.query(Patient)
            .filter(
                Patient.medical_record_number
                == "SYNTH-DR-001"
            )
            .first()
        )

        if patient is None:
            patient = Patient(
                medical_record_number="SYNTH-DR-001",
                first_name="Synthetic",
                last_name="Patient",
                source_system="integration-test",
                external_id="synthetic-dr-patient-001",
            )

            db.add(patient)
            db.commit()
            db.refresh(patient)

            print(
                f"Synthetic patient created: {patient.id}"
            )
        else:
            print(
                f"Existing synthetic patient used: {patient.id}"
            )

        report_data = (
            b"SYNTHETIC diagnostic report for "
            b"healthcare cloud platform integration testing"
        )

        report = diagnostic_report_service.create_report(
            db,
            patient_id=patient.id,
            report_type="synthetic-test-report",
            title="Synthetic Diagnostic Report",
            issued_at=datetime.now(timezone.utc),
            original_filename="synthetic-report.txt",
            content_type="text/plain",
            data=report_data,
            external_id=f"report-{uuid4().hex}",
            source_system="integration-test",
            status="final",
            conclusion="Synthetic integration test only",
        )

        integrity_valid = (
            diagnostic_report_service
            .storage
            .verify_object_integrity(
                report.object_key,
                report.checksum_sha256,
            )
        )

        print("Integration test completed")
        print(f"Report ID: {report.id}")
        print(f"Patient ID: {patient.id}")
        print(f"Bucket: {report.bucket_name}")
        print(f"Object key: {report.object_key}")
        print(f"File size: {report.file_size_bytes}")
        print(f"SHA-256: {report.checksum_sha256}")
        print(f"Integrity valid: {integrity_valid}")

    finally:
        db.close()


if __name__ == "__main__":
    main()