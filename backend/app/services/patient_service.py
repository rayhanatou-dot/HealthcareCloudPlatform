from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.models.patient import Patient


class PatientService:
    """
    Service layer for structured patient
    persistence and retrieval operations.
    """

    def create_patient(
        self,
        db: Session,
        *,
        patient_data: dict,
    ) -> Patient:
        """
        Create and persist a patient.
        """

        patient = Patient(
            **patient_data
        )

        try:
            db.add(patient)
            db.commit()
            db.refresh(patient)

            return patient

        except Exception:
            db.rollback()
            raise

    def get_patient(
        self,
        db: Session,
        *,
        patient_id: int,
    ) -> Patient | None:
        """
        Retrieve one patient by primary key.
        """

        return db.get(
            Patient,
            patient_id,
        )

    def list_patients(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Patient], int]:
        """
        Retrieve a paginated patient collection.
        """

        total = db.execute(
            select(
                func.count()
            ).select_from(
                Patient
            )
        ).scalar_one()

        patients = list(
            db.execute(
                select(Patient)
                .order_by(Patient.id)
                .offset(skip)
                .limit(limit)
            ).scalars().all()
        )

        return patients, int(total)

    def update_patient(
        self,
        db: Session,
        *,
        patient: Patient,
        update_data: dict,
    ) -> Patient:
        """
        Apply a partial update to an existing patient.
        """

        try:
            for field_name, value in update_data.items():
                setattr(
                    patient,
                    field_name,
                    value,
                )

            db.add(patient)
            db.commit()
            db.refresh(patient)

            return patient

        except Exception:
            db.rollback()
            raise


patient_service = PatientService()