import os

from locust import HttpUser, between, task


class HealthcarePlatformUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.username = os.getenv(
            "LOCUST_USERNAME",
            "demo_admin",
        )

        self.password = os.getenv(
            "LOCUST_PASSWORD",
            "ChangeMe123!",
        )

        self.auth_headers = {}

        self.login()

    def login(self):
        with self.client.post(
            "/api/v1/auth/login",
            data={
                "username": self.username,
                "password": self.password,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            name="POST /api/v1/auth/login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Login failed with status {response.status_code}: "
                    f"{response.text}"
                )
                return

            try:
                token = response.json().get(
                    "access_token"
                )
            except Exception as exc:
                response.failure(
                    f"Login response JSON parsing failed: {exc}"
                )
                return

            if not token:
                response.failure(
                    "Login response did not contain access_token"
                )
                return

            self.auth_headers = {
                "Authorization": f"Bearer {token}"
            }

            response.success()

    @task(1)
    def health_check(self):
        self.client.get(
            "/health",
            name="GET /health",
        )

    @task(4)
    def list_patients(self):
        self.client.get(
            "/api/v1/patients?skip=0&limit=20",
            headers=self.auth_headers,
            name="GET /api/v1/patients",
        )

    @task(3)
    def list_encounters(self):
        self.client.get(
            "/api/v1/encounters?skip=0&limit=20",
            headers=self.auth_headers,
            name="GET /api/v1/encounters",
        )

    @task(3)
    def list_observations(self):
        self.client.get(
            "/api/v1/observations?skip=0&limit=20",
            headers=self.auth_headers,
            name="GET /api/v1/observations",
        )

    @task(2)
    def list_prescriptions(self):
        self.client.get(
            "/api/v1/prescriptions?skip=0&limit=20",
            headers=self.auth_headers,
            name="GET /api/v1/prescriptions",
        )