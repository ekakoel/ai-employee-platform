"""Object storage abstraction (local filesystem default; S3-ready interface)."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings


class ObjectStorage(ABC):
    @abstractmethod
    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        ...

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...


class LocalObjectStorage(ObjectStorage):
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or settings.storage_local_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # prevent path traversal
        safe = Path(key.replace("\\", "/").lstrip("/"))
        full = (self.root / safe).resolve()
        if not str(full).startswith(str(self.root)):
            raise ValueError("Invalid storage key")
        return full

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def copy_file(self, src: Path, key: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)
        return key


def get_storage() -> ObjectStorage:
    if settings.storage_backend == "local":
        return LocalObjectStorage()
    # Future: S3ObjectStorage
    return LocalObjectStorage()
