from pathlib import Path


CONFIG_FILE = Path("backend/app/core/config.py")


def insert_before(text: str, marker: str, addition: str) -> str:
    if marker not in text:
        raise RuntimeError(f"Marker not found: {marker!r}")

    return text.replace(marker, addition + marker, 1)


def main() -> None:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Missing file: {CONFIG_FILE}")

    text = CONFIG_FILE.read_text(encoding="utf-8-sig")

    required_existing_settings = [
        "MINIO_ENDPOINT",
    ]

    missing = [
        name
        for name in required_existing_settings
        if name not in text
    ]

    if missing:
        raise RuntimeError(
            "Restore the committed config first. Missing settings: "
            + ", ".join(missing)
        )

    if "DOCS_ENABLED:" not in text:
        fields = '''
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

'''
        text = insert_before(
            text,
            "    model_config = SettingsConfigDict(",
            fields,
        )

    if "def cors_allowed_origins" not in text:
        properties = '''
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


'''
        text = insert_before(
            text,
            "\nsettings = Settings()",
            properties,
        )

    CONFIG_FILE.write_text(
        text,
        encoding="utf-8",
        newline="\n",
    )

    print("Existing application settings preserved.")
    print("HTTP security settings added safely.")
    print(f"Updated: {CONFIG_FILE}")


if __name__ == "__main__":
    main()
