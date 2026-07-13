from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.models.prescription import Prescription


class PrescriptionService:
    """
    Service layer for prescription persistence operations.
    """

    def create_prescription(
        self,
        db: Session,
        prescription_data: dict,
    ) -> Prescription:
        prescription = Prescription(
            **prescription_data
        )

        try:
            db.add(prescription)
            db.commit()
            db.refresh(prescription)

            return prescription

        except Exception:
            db.rollback()
            raise

    def get_prescription(
        self,
        db: Session,
        prescription_id: int,
    ) -> Prescription | None:
        return db.get(
            Prescription,
            prescription_id,
        )

    def list_prescriptions(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        patient_id: int | None = None,
        encounter_id: int | None = None,
        prescriber_id: int | None = None,
        status: str | None = None,
    ) -> tuple[int, list[Prescription]]:
        count_statement = select(
            func.count(Prescription.id)
        )

        data_statement = select(
            Prescription
        )

        if patient_id is not None:
            count_statement = count_statement.where(
                Prescription.patient_id == patient_id
            )
            data_statement = data_statement.where(
                Prescription.patient_id == patient_id
            )

        if encounter_id is not None:
            count_statement = count_statement.where(
                Prescription.encounter_id == encounter_id
            )
            data_statement = data_statement.where(
                Prescription.encounter_id == encounter_id
            )

        if prescriber_id is not None:
            count_statement = count_statement.where(
                Prescription.prescriber_id == prescriber_id
            )
            data_statement = data_statement.where(
                Prescription.prescriber_id == prescriber_id
            )

        if status is not None:
            count_statement = count_statement.where(
                Prescription.status == status
            )
            data_statement = data_statement.where(
                Prescription.status == status
            )

        total = db.scalar(
            count_statement
        ) or 0

        prescriptions = list(
            db.scalars(
                data_statement
                .order_by(
                    Prescription.authored_at.desc(),
                    Prescription.id.desc(),
                )
                .offset(skip)
                .limit(limit)
            ).all()
        )

        return total, prescriptions

    def update_prescription(
        self,
        db: Session,
        prescription: Prescription,
        update_data: dict,
    ) -> Prescription:
        for field_name, value in update_data.items():
            setattr(
                prescription,
                field_name,
                value,
            )

        try:
            db.add(prescription)
            db.commit()
            db.refresh(prescription)

            return prescription

        except Exception:
            db.rollback()
            raise


prescription_service = PrescriptionService()