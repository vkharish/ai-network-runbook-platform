"""HashiCorp Vault integration for device credential management.

When VAULT_ENABLED=true, device credentials are retrieved from Vault at runtime.
When VAULT_ENABLED=false (default), falls back to Fernet-encrypted credentials
stored in the DeviceCredential table — no behavior change from previous version.

Usage:
    username, password = get_credential(device)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.core.logging import get_logger

if TYPE_CHECKING:
    from backend.models.device_model import Device

log = get_logger(__name__)


class VaultClient:
    """Thin wrapper around hvac for device secret read/write."""

    def __init__(self) -> None:
        from backend.core.config import settings

        try:
            import hvac  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "hvac is not installed. Add 'hvac>=2.1.0' to requirements.txt."
            ) from exc

        self._client = hvac.Client(url=settings.vault_addr)
        self._mount = settings.vault_mount_path
        self._prefix = settings.vault_device_prefix

        if settings.vault_role_id and settings.vault_secret_id:
            self._client.auth.approle.login(
                role_id=settings.vault_role_id,
                secret_id=settings.vault_secret_id,
            )
            log.info("vault_auth_approle")
        elif settings.vault_token:
            self._client.token = settings.vault_token
            log.info("vault_auth_token")
        else:
            raise RuntimeError(
                "Vault enabled but no auth configured. "
                "Set VAULT_TOKEN or VAULT_ROLE_ID + VAULT_SECRET_ID."
            )

        if not self._client.is_authenticated():
            raise RuntimeError("Vault authentication failed.")

    def _path(self, hostname: str) -> str:
        return f"{self._prefix}/{hostname}"

    def get_device_secret(self, hostname: str) -> dict:
        """Return {'username': ..., 'password': ...} from Vault KV v2."""
        response = self._client.secrets.kv.v2.read_secret_version(
            path=self._path(hostname),
            mount_point=self._mount,
        )
        data: dict = response["data"]["data"]
        return data

    def put_device_secret(self, hostname: str, username: str, password: str) -> None:
        """Write or update device credentials in Vault."""
        self._client.secrets.kv.v2.create_or_update_secret(
            path=self._path(hostname),
            secret={"username": username, "password": password},
            mount_point=self._mount,
        )
        log.info("vault_secret_written", hostname=hostname)

    def rotate_device_secret(self, hostname: str, new_password: str) -> None:
        """Update the password for an existing device secret in Vault."""
        existing = self.get_device_secret(hostname)
        self.put_device_secret(hostname, existing["username"], new_password)
        log.info("vault_secret_rotated", hostname=hostname)


_vault_client: VaultClient | None = None


def _get_vault_client() -> VaultClient:
    """Singleton Vault client (initialised once per process)."""
    global _vault_client
    if _vault_client is None:
        _vault_client = VaultClient()
    return _vault_client


def get_credential(device: "Device") -> tuple[str, str]:
    """Return (username, plaintext_password) for a device.

    Uses Vault when VAULT_ENABLED=true, otherwise decrypts from DB.
    """
    from backend.core.config import settings

    if settings.vault_enabled:
        try:
            client = _get_vault_client()
            secret = client.get_device_secret(device.hostname)
            return secret["username"], secret["password"]
        except Exception as exc:
            log.warning(
                "vault_credential_fallback",
                hostname=device.hostname,
                error=str(exc),
            )
            # Fall through to local decryption on Vault error

    # Fallback: Fernet decrypt from DeviceCredential table
    from backend.core.security import decrypt_credential

    cred = getattr(device, "credential", None)
    if cred is None:
        raise ValueError(f"No credential found for device {device.hostname}")
    username = cred.username
    password = decrypt_credential(cred.password_encrypted)
    return username, password
