from datetime import date, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class PrescriptionCreate(BaseModel):
    """
    Payload used to create a medication prescription.
    """

    patient_id: int = Field(
        gt=0,
    )

    encounter_id: int | None = Field(
        default=None,
        gt=0,
    )

    prescriber_id: int = Field(
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

    medication_name: str = Field(
        min_length=1,
        max_length=255,
    )

    medication_code: str | None = Field(
        default=None,
        max_length=100,
    )

    code_system: str | None = Field(
        default=None,
        max_length=100,
    )

    dosage_amount: Decimal | None = Field(
        default=None,
        gt=0,
    )

    dosage_unit: str | None = Field(
        default=None,
        max_length=50,
    )

    route: str | None = Field(
        default=None,
        max_length=100,
    )

    frequency: str | None = Field(
        default=None,
        max_length=100,
    )

    instructions: str | None = Field(
        default=None,
        max_length=1000,
    )

    status: str = Field(
        default="active",
        min_length=1,
        max_length=50,
    )

    authored_at: datetime

    start_date: date | None = None

    end_date: date | None = None

    @model_validator(mode="after")
    def validate_prescription(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError(
                "end_date cannot be earlier than start_date"
            )

        if (
            self.dosage_amount is not None
            and self.dosage_unit is None
        ):
            raise ValueError(
                "dosage_unit must be supplied when dosage_amount is provided"
            )

        return self


class PrescriptionUpdate(BaseModel):
    """
    Partial prescription update payload.

    Only supplied fields are modified.
    """

    encounter_id: int | None = Field(
        default=None,
        gt=0,
    )

    prescriber_id: int | None = Field(
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

    medication_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    medication_code: str | None = Field(
        default=None,
        max_length=100,
    )

    code_system: str | None = Field(
        default=None,
        max_length=100,
    )

    dosage_amount: Decimal | None = Field(
        default=None,
        gt=0,
    )

    dosage_unit: str | None = Field(
        default=None,
        max_length=50,
    )

    route: str | None = Field(
        default=None,
        max_length=100,
    )

    frequency: str | None = Field(
        default=None,
        max_length=100,
    )

    instructions: str | None = Field(
        default=None,
        max_length=1000,
    )

    status: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    authored_at: datetime | None = None

    start_date: date | None = None

    end_date: date | None = None

    @model_validator(mode="after")
    def validate_supplied_dates(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError(
                "end_date cannot be earlier than start_date"
            )

        if (
            self.dosage_amount is not None
            and self.dosage_unit is None
        ):
            raise ValueError(
                "dosage_unit must be supplied when dosage_amount is provided"
            )

        return self


class PrescriptionResponse(BaseModel):
    """
    Public API representation of a prescription.
    """

    model_config = ConfigDict(
        from_attributes=True
    )

    id: int

    patient_id: int
    encounter_id: int | None
    prescriber_id: int | None

    external_id: str | None
    source_system: str | None

    medication_name: str
    medication_code: str | None
    code_system: str | None

    dosage_amount: Decimal | None
    dosage_unit: str | None

    route: str | None
    frequency: str | None
    instructions: str | None

    status: str

    authored_at: datetime

    start_date: date | None
    end_date: date | None

    created_at: datetime
    updated_at: datetime


class PrescriptionListResponse(BaseModel):
    """
    Paginated prescription collection.
    """

    total: int
    skip: int
    limit: int
    items: list[PrescriptionResponse]