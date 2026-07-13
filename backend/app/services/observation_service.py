from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.orm import Session

from app.models.observation import Observation


class ObservationService:
    """
    Service layer for observation persistence operations.
    """

    def create_observation(
        self,
        db: Session,
        observation_data: dict,
    ) -> Observation:
        observation = Observation(
            **observation_data
        )

        try:
            db.add(observation)
            db.commit()
            db.refresh(observation)

            return observation

        except Exception:
            db.rollback()
            raise

    def get_observation(
        self,
        db: Session,
        observation_id: int,
    ) -> Observation | None:
        return db.get(
            Observation,
            observation_id,
        )

    def list_observations(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        patient_id: int | None = None,
        encounter_id: int | None = None,
    ) -> tuple[int, list[Observation]]:
        count_statement = select(
            func.count(Observation.id)
        )

        data_statement = select(
            Observation
        )

        if patient_id is not None:
            count_statement = count_statement.where(
                Observation.patient_id == patient_id
            )

            data_statement = data_statement.where(
                Observation.patient_id == patient_id
            )

        if encounter_id is not None:
            count_statement = count_statement.where(
                Observation.encounter_id == encounter_id
            )

            data_statement = data_statement.where(
                Observation.encounter_id == encounter_id
            )

        total = db.scalar(
            count_statement
        ) or 0

        observations = list(
            db.scalars(
                data_statement
                .order_by(
                    Observation.observed_at.desc(),
                    Observation.id.desc(),
                )
                .offset(skip)
                .limit(limit)
            ).all()
        )

        return total, observations

    def update_observation(
        self,
        db: Session,
        observation: Observation,
        update_data: dict,
    ) -> Observation:
        for field_name, value in update_data.items():
            setattr(
                observation,
                field_name,
                value,
            )

        try:
            db.add(observation)
            db.commit()
            db.refresh(observation)

            return observation

        except Exception:
            db.rollback()
            raise


observation_service = ObservationService()