from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.models.encounter import Encounter


class EncounterService:
    """
    Service layer for encounter persistence operations.
    """

    def create_encounter(
        self,
        db: Session,
        encounter_data: dict,
    ) -> Encounter:
        encounter = Encounter(
            **encounter_data
        )

        try:
            db.add(encounter)
            db.commit()
            db.refresh(encounter)

            return encounter

        except Exception:
            db.rollback()
            raise

    def get_encounter(
        self,
        db: Session,
        encounter_id: int,
    ) -> Encounter | None:
        return db.get(
            Encounter,
            encounter_id,
        )

    def list_encounters(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        patient_id: int | None = None,
    ) -> tuple[int, list[Encounter]]:
        count_statement = select(
            func.count(Encounter.id)
        )

        data_statement = select(
            Encounter
        )

        if patient_id is not None:
            count_statement = count_statement.where(
                Encounter.patient_id == patient_id
            )

            data_statement = data_statement.where(
                Encounter.patient_id == patient_id
            )

        total = db.scalar(
            count_statement
        ) or 0

        encounters = list(
            db.scalars(
                data_statement
                .order_by(
                    Encounter.start_time.desc(),
                    Encounter.id.desc(),
                )
                .offset(skip)
                .limit(limit)
            ).all()
        )

        return total, encounters

    def update_encounter(
        self,
        db: Session,
        encounter: Encounter,
        update_data: dict,
    ) -> Encounter:
        for field_name, value in update_data.items():
            setattr(
                encounter,
                field_name,
                value,
            )

        try:
            db.add(encounter)
            db.commit()
            db.refresh(encounter)

            return encounter

        except Exception:
            db.rollback()
            raise


encounter_service = EncounterService()