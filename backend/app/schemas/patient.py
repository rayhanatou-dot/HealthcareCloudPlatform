from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class PatientCreate(BaseModel):
    """
    Payload used to register a new patient.
    """

    medical_record_number: str = Field(
        min_length=1,
        max_length=100,
    )

    external_id: str | None = Field(
        default=None,
        max_length=100,
    )

    source_system: str | None = Field(
        default=None,
        max_length=100,
    )

    first_name: str = Field(
        min_length=1,
        max_length=100,
    )

    last_name: str = Field(
        min_length=1,
        max_length=100,
    )

    date_of_birth: date | None = None

    gender: str | None = Field(
        default=None,
        max_length=50,
    )

    phone: str | None = Field(
        default=None,
        max_length=50,
    )

    email: str | None = Field(
        default=None,
        max_length=255,
    )

    address_line: str | None = Field(
        default=None,
        max_length=255,
    )

    city: str | None = Field(
        default=None,
        max_length=100,
    )

    state: str | None = Field(
        default=None,
        max_length=100,
    )

    postal_code: str | None = Field(
        default=None,
        max_length=30,
    )

    country: str | None = Field(
        default=None,
        max_length=100,
    )


class PatientUpdate(BaseModel):
    """
    Partial patient update payload.

    Only supplied fields are modified.
    """

    medical_record_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    external_id: str | None = Field(
        default=None,
        max_length=100,
    )

    source_system: str | None = Field(
        default=None,
        max_length=100,
    )

    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    date_of_birth: date | None = None

    gender: str | None = Field(
        default=None,
        max_length=50,
    )

    phone: str | None = Field(
        default=None,
        max_length=50,
    )

    email: str | None = Field(
        default=None,
        max_length=255,
    )

    address_line: str | None = Field(
        default=None,
        max_length=255,
    )

    city: str | None = Field(
        default=None,
        max_length=100,
    )

    state: str | None = Field(
        default=None,
        max_length=100,
    )

    postal_code: str | None = Field(
        default=None,
        max_length=30,
    )

    country: str | None = Field(
        default=None,
        max_length=100,
    )


class PatientResponse(BaseModel):
    """
    Public API representation of a patient.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    medical_record_number: str

    external_id: str | None
    source_system: str | None

    first_name: str
    last_name: str

    date_of_birth: date | None

    gender: str | None
    phone: str | None
    email: str | None

    address_line: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None

    created_at: datetime
    updated_at: datetime


class PatientListResponse(BaseModel):
    """
    Paginated patient collection.
    """

    total: int
    skip: int
    limit: int
    items: list[PatientResponse]