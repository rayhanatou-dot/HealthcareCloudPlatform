from __future__ import annotations

import os
from typing import Any

from locust import HttpUser, between, task


class HealthcareApiUser(HttpUser):
    """Load-test user for the healthcare platform API."""

    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        """Authenticate once and store the bearer token."""

        username = os.getenv("LOADTEST_USERNAME", "demo_admin")
        password = os.getenv("LOADTEST_PASSWORD")

        if not password:
            raise RuntimeError(
                "LOADTEST_PASSWORD is required before starting Locust."
            )

        with self.client.post(
            "/api/v1/auth/login",
            data={
                "username": username,
                "password": password,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },
            name="POST /api/v1/auth/login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Authentication failed: {response.status_code}"
                )
                raise RuntimeError(
                    "Locust could not authenticate the test user."
                )

            payload: dict[str, Any] = response.json()
            access_token = payload.get("access_token")

            if not access_token:
                response.failure(
                    "Authentication response has no access token."
                )
                raise RuntimeError(
                    "Authentication response has no access token."
                )

            self.client.headers.update(
                {
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                }
            )

    @task(1)
    def health_check(self) -> None:
        """Check the public health endpoint."""

        self.client.get(
            "/health",
            name="GET /health",
        )

    @task(4)
    def read_patient(self) -> None:
        """Read one known patient."""

        self.client.get(
            "/api/v1/fhir/Patient/1192",
            name="GET /api/v1/fhir/Patient/{id}",
        )

    @task(1)
    def read_patient_everything(self) -> None:
        """Read the aggregated clinical record for one patient."""

        self.client.get(
            "/api/v1/fhir/Patient/1192/$everything",
            name="GET /api/v1/fhir/Patient/{id}/$everything",
        )

    @task(2)
    def read_encounter(self) -> None:
        """Read one known encounter."""

        self.client.get(
            "/api/v1/fhir/Encounter/2898",
            name="GET /api/v1/fhir/Encounter/{id}",
        )

    @task(3)
    def read_condition(self) -> None:
        """Read one known condition."""

        self.client.get(
            "/api/v1/fhir/Condition/1",
            name="GET /api/v1/fhir/Condition/{id}",
        )

    @task(3)
    def search_patient_conditions(self) -> None:
        """Search conditions for one known patient."""

        self.client.get(
            "/api/v1/fhir/Condition?patient=1192&_count=20",
            name=(
                "GET /api/v1/fhir/Condition"
                "?patient={id}&_count=20"
            ),
        )
