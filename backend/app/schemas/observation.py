from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class ObservationCreate(BaseModel):
    """
    Payload used to create a clinical observation
    or laboratory result.
    """

    patient_id: int = Field(
        gt=0,
    )

    encounter_id: int | None = Field(
        default=None,
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

    category: str = Field(
        min_length=1,
        max_length=100,
    )

    code: str = Field(
        min_length=1,
        max_length=100,
    )

    code_system: str | None = Field(
        default=None,
        max_length=100,
    )

    display_name: str | None = Field(
        default=None,
        max_length=255,
    )

    value_numeric: Decimal | None = None

    value_text: str | None = Field(
        default=None,
        max_length=500,
    )

    unit: str | None = Field(
        default=None,
        max_length=50,
    )

    reference_range: str | None = Field(
        default=None,
        max_length=255,
    )

    status: str = Field(
        default="registered",
        min_length=1,
        max_length=50,
    )

    observed_at: datetime

    issued_at: datetime | None = None

    @model_validator(mode="after")
    def validate_observation_value(self):
        if (
            self.value_numeric is None
            and self.value_text is None
        ):
            raise ValueError(
                "Either value_numeric or value_text must be supplied"
            )

        return self


class ObservationUpdate(BaseModel):
    """
    Partial observation update payload.

    Only supplied fields are modified.
    """

    encounter_id: int | None = Field(
        default=None,
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

    category: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    code_system: str | None = Field(
        default=None,
        max_length=100,
    )

    display_name: str | None = Field(
        default=None,
        max_length=255,
    )

    value_numeric: Decimal | None = None

    value_text: str | None = Field(
        default=None,
        max_length=500,
    )

    unit: str | None = Field(
        default=None,
        max_length=50,
    )

    reference_range: str | None = Field(
        default=None,
        max_length=255,
    )

    status: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    observed_at: datetime | None = None

    issued_at: datetime | None = None


class ObservationResponse(BaseModel):
    """
    Public API representation of an observation
    or laboratory result.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    patient_id: int
    encounter_id: int | None

    external_id: str | None
    source_system: str | None

    category: str
    code: str

    code_system: str | None
    display_name: str | None

    value_numeric: Decimal | None
    value_text: str | None

    unit: str | None
    reference_range: str | None

    status: str

    observed_at: datetime
    issued_at: datetime | None

    created_at: datetime
    updated_at: datetime


class ObservationListResponse(BaseModel):
    """
    Paginated observation collection.
    """

    total: int
    skip: int
    limit: int
    items: list[ObservationResponse]