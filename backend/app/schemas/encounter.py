from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class EncounterCreate(BaseModel):
    """
    Payload used to create a healthcare encounter.
    """

    patient_id: int = Field(
        gt=0,
    )

    external_id: str | None = Field(
        default=None,
        max_length=100,
    )

    source_system: str | None = Field(
        default=None,
        max_length=100,
    )

    encounter_type: str = Field(
        min_length=1,
        max_length=100,
    )

    status: str = Field(
        default="active",
        min_length=1,
        max_length=50,
    )

    start_time: datetime

    end_time: datetime | None = None

    location: str | None = Field(
        default=None,
        max_length=255,
    )

    @model_validator(mode="after")
    def validate_time_range(self):
        if (
            self.end_time is not None
            and self.end_time < self.start_time
        ):
            raise ValueError(
                "end_time cannot be earlier than start_time"
            )

        return self


class EncounterUpdate(BaseModel):
    """
    Partial encounter update payload.

    Only supplied fields are modified.
    """

    external_id: str | None = Field(
        default=None,
        max_length=100,
    )

    source_system: str | None = Field(
        default=None,
        max_length=100,
    )

    encounter_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    status: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    start_time: datetime | None = None

    end_time: datetime | None = None

    location: str | None = Field(
        default=None,
        max_length=255,
    )


class EncounterResponse(BaseModel):
    """
    Public API representation of an encounter.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    patient_id: int

    external_id: str | None
    source_system: str | None

    encounter_type: str
    status: str

    start_time: datetime
    end_time: datetime | None

    location: str | None

    created_at: datetime
    updated_at: datetime


class EncounterListResponse(BaseModel):
    """
    Paginated encounter collection.
    """

    total: int
    skip: int
    limit: int
    items: list[EncounterResponse]