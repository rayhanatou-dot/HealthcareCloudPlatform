from hashlib import sha256
from io import BytesIO

from minio import Minio
from minio.error import S3Error

from app.core.config import settings


class StorageService:
    """
    Provides object-storage access for the
    Healthcare Cloud Platform.

    PostgreSQL stores structured metadata, while
    MinIO stores binary healthcare objects such as
    diagnostic reports and related attachments.
    """

    def __init__(self) -> None:
        self.bucket_name = settings.MINIO_BUCKET_NAME

        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ROOT_USER,
            secret_key=settings.MINIO_ROOT_PASSWORD,
            secure=settings.MINIO_SECURE,
        )

    def ensure_bucket(self) -> None:
        """
        Ensure that the configured healthcare object-storage
        bucket exists before upload or retrieval operations.
        """
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)

        except S3Error as exc:
            raise RuntimeError(
                "Unable to verify or create the MinIO bucket"
            ) from exc

    def is_ready(self) -> bool:
        """
        Verify that the configured bucket is accessible.
        """
        try:
            return self.client.bucket_exists(
                self.bucket_name
            )

        except S3Error as exc:
            raise RuntimeError(
                "Unable to verify MinIO storage readiness"
            ) from exc

    def upload_bytes(
        self,
        object_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, str | int]:
        """
        Upload binary data to MinIO and return metadata
        required for PostgreSQL persistence.
        """
        if not object_key.strip():
            raise ValueError(
                "object_key must not be empty"
            )

        if not data:
            raise ValueError(
                "data must not be empty"
            )

        self.ensure_bucket()

        checksum = sha256(data).hexdigest()
        file_size = len(data)

        try:
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_key,
                data=BytesIO(data),
                length=file_size,
                content_type=content_type,
            )

        except S3Error as exc:
            raise RuntimeError(
                f"Unable to upload object: {object_key}"
            ) from exc

        return {
            "bucket_name": self.bucket_name,
            "object_key": object_key,
            "content_type": content_type,
            "file_size_bytes": file_size,
            "checksum_sha256": checksum,
        }

    def download_bytes(
        self,
        object_key: str,
    ) -> bytes:
        """
        Download an object from MinIO as bytes.
        """
        if not object_key.strip():
            raise ValueError(
                "object_key must not be empty"
            )

        response = None

        try:
            response = self.client.get_object(
                bucket_name=self.bucket_name,
                object_name=object_key,
            )

            return response.read()

        except S3Error as exc:
            raise RuntimeError(
                f"Unable to download object: {object_key}"
            ) from exc

        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def verify_object_integrity(
        self,
        object_key: str,
        expected_sha256: str,
    ) -> bool:
        """
        Download an object, recompute its SHA-256 digest,
        and compare it with the expected checksum.
        """
        downloaded_data = self.download_bytes(
            object_key
        )

        actual_sha256 = sha256(
            downloaded_data
        ).hexdigest()

        return actual_sha256 == expected_sha256

    def delete_object(
        self,
        object_key: str,
    ) -> None:
        """
        Delete an object from MinIO.

        This method supports compensating cleanup when
        object upload succeeds but PostgreSQL persistence
        fails.
        """
        if not object_key.strip():
            raise ValueError(
                "object_key must not be empty"
            )

        try:
            self.client.remove_object(
                bucket_name=self.bucket_name,
                object_name=object_key,
            )

        except S3Error as exc:
            raise RuntimeError(
                f"Unable to delete object: {object_key}"
            ) from exc
        
storage_service = StorageService()

