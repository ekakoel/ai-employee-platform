"""S3 / S3-compatible object storage (Job 25).

Uses boto3 when available. Works with AWS S3, MinIO, LocalStack via
S3_ENDPOINT_URL.
"""

from __future__ import annotations

from typing import Any

from app.storage.base import ObjectStorage


class S3ObjectStorage(ObjectStorage):
    def __init__(
        self,
        *,
        bucket: str | None = None,
        region: str | None = None,
        endpoint_url: str | None = None,
        client: Any | None = None,
    ):
        from app.core.config import settings as live_settings

        self.bucket = bucket or live_settings.s3_bucket
        if not self.bucket:
            raise ValueError(
                "S3 storage requires S3_BUCKET (or bucket=) to be set"
            )
        self.region = region or live_settings.s3_region or "us-east-1"
        self.endpoint_url = endpoint_url if endpoint_url is not None else (
            live_settings.s3_endpoint_url or None
        )
        self._settings = live_settings
        if client is not None:
            self._client = client
        else:
            self._client = self._build_client()

    def _build_client(self) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for S3 storage. "
                "Install with: pip install boto3"
            ) from exc

        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": self.region,
            "config": Config(signature_version="s3v4"),
        }
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        # Credentials: env AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
        # or optional settings fields
        key = getattr(self._settings, "s3_access_key_id", None) or None
        secret = getattr(self._settings, "s3_secret_access_key", None) or None
        if key and secret:
            kwargs["aws_access_key_id"] = key
            kwargs["aws_secret_access_key"] = secret
        return boto3.client(**kwargs)

    def put_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        key = key.lstrip("/")
        extra: dict[str, Any] = {}
        if content_type:
            extra["ContentType"] = content_type
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            **extra,
        )
        return key

    def get_bytes(self, key: str) -> bytes:
        key = key.lstrip("/")
        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            # Normalize missing key
            error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundError(key) from exc
            # botocore ClientError
            name = type(exc).__name__
            if name == "ClientError" and "NoSuchKey" in str(exc):
                raise FileNotFoundError(key) from exc
            raise
        body = resp["Body"].read()
        return body

    def exists(self, key: str) -> bool:
        key = key.lstrip("/")
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        key = key.lstrip("/")
        self._client.delete_object(Bucket=self.bucket, Key=key)
