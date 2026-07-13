from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Literal, Protocol

SecretStorageKind = Literal["owner_only_file", "os_keyring"]


class ProviderSecretStoreError(RuntimeError):
    """Raised when an explicitly selected platform secret store is unavailable."""


class ProviderSecretStore(Protocol):
    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class OSKeyringSecretStore:
    def __init__(self, config_path: Path) -> None:
        identity = hashlib.sha256(str(config_path.resolve()).encode()).hexdigest()[:16]
        self.service_name = f"proofline.providers.{identity}"

    @staticmethod
    def _keyring():
        try:
            import keyring
        except ImportError as exc:  # pragma: no cover - dependency is included in release wheels
            raise ProviderSecretStoreError("OS keyring support is unavailable") from exc
        return keyring

    def get(self, name: str) -> str | None:
        try:
            return self._keyring().get_password(self.service_name, name)
        except Exception as exc:
            raise ProviderSecretStoreError("OS keyring could not be read") from exc

    def set(self, name: str, value: str) -> None:
        try:
            self._keyring().set_password(self.service_name, name, value)
        except Exception as exc:
            raise ProviderSecretStoreError("OS keyring could not be updated") from exc

    def delete(self, name: str) -> None:
        keyring = self._keyring()
        try:
            keyring.delete_password(self.service_name, name)
        except keyring.errors.PasswordDeleteError:
            return
        except Exception as exc:
            raise ProviderSecretStoreError("OS keyring could not be updated") from exc


def provider_secret_storage_kind() -> SecretStorageKind:
    configured = os.getenv("PROOFLINE_SECRET_STORE", "file").strip().lower()
    if configured == "file":
        return "owner_only_file"
    if configured == "os_keyring":
        return "os_keyring"
    raise ProviderSecretStoreError("PROOFLINE_SECRET_STORE must be either 'file' or 'os_keyring'")


def get_provider_secret_store(config_path: Path) -> ProviderSecretStore | None:
    if provider_secret_storage_kind() == "owner_only_file":
        return None
    return OSKeyringSecretStore(config_path)
