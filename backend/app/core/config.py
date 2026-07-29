
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Healthcare Cloud Platform"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True

    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    DATABASE_URL: str = "postgresql://your_postgres_user:your_postgres_password@localhost:5432/healthcare_cloud_db"

    JWT_SECRET_KEY: str = "replace_with_secure_random_key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ROOT_USER: str = "your_minio_user"
    MINIO_ROOT_PASSWORD: str = "your_minio_password"
    MINIO_BUCKET_NAME: str = "healthcare-files"
    MINIO_SECURE: bool = False

    DOCS_ENABLED: bool = True
    CORS_ALLOWED_ORIGINS: str = (
        "http://localhost:3000,"
        "http://localhost:5173,"
        "http://localhost:8080,"
        "http://localhost:8081"
    )
    ALLOWED_HOSTS: str = (
        "localhost,"
        "127.0.0.1,"
        "backend,"
        "healthcare_backend"
    )

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


    @property
    def cors_allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def allowed_hosts(self) -> list[str]:
        return [
            host.strip()
            for host in self.ALLOWED_HOSTS.split(",")
            if host.strip()
        ]



settings = Settings()
