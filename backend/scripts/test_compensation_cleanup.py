from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.patient import Patient
from app.services import diagnostic_report_service


def main() -> None:
    db = SessionLocal()
    storage = diagnostic_report_service.storage

    try:
        # Dynamically generate a patient ID that does not exist.
        max_patient_id = db.execute(
            select(
                func.coalesce(
                    func.max(Patient.id),
                    0,
                )
            )
        ).scalar_one()

        invalid_patient_id = int(max_patient_id) + 1_000_000

        prefix = (
            f"patients/{invalid_patient_id}/"
            f"diagnostic-reports/"
        )

        objects_before = [
            obj.object_name
            for obj in storage.client.list_objects(
                storage.bucket_name,
                prefix=prefix,
                recursive=True,
            )
        ]

        print("Compensation test started")
        print(
            f"Invalid patient ID: {invalid_patient_id}"
        )
        print(
            f"Objects before failure: {len(objects_before)}"
        )

        operation_failed = False

        try:
            diagnostic_report_service.create_report(
                db,
                patient_id=invalid_patient_id,
                report_type="compensation-test",
                title="Forced Database Failure Test",
                issued_at=datetime.now(timezone.utc),
                original_filename="orphan-test.txt",
                content_type="text/plain",
                data=(
                    b"SYNTHETIC report used only to test "
                    b"cross-storage compensation cleanup"
                ),
                source_system="integration-test",
                status="final",
                conclusion=(
                    "This insert must fail because the "
                    "patient does not exist."
                ),
            )

        except Exception as exc:
            operation_failed = True

            print(
                "Expected database failure caught:",
                type(exc).__name__,
            )

        objects_after = [
            obj.object_name
            for obj in storage.client.list_objects(
                storage.bucket_name,
                prefix=prefix,
                recursive=True,
            )
        ]

        new_remaining_objects = sorted(
            set(objects_after)
            - set(objects_before)
        )

        compensation_valid = (
            operation_failed
            and len(new_remaining_objects) == 0
        )

        print(
            f"Objects after failure: {len(objects_after)}"
        )
        print(
            f"New orphan objects: "
            f"{len(new_remaining_objects)}"
        )
        print(
            f"Compensation valid: {compensation_valid}"
        )

        if new_remaining_objects:
            print(
                "Unexpected remaining objects:"
            )

            for object_name in new_remaining_objects:
                print(
                    f"  - {object_name}"
                )

    finally:
        db.close()


if __name__ == "__main__":
    main()