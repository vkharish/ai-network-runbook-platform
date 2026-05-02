from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import bcrypt as _bcrypt_lib
from jose import JWTError, jwt

from backend.core.config import settings
from backend.core.logging import get_logger

log = get_logger(__name__)


class Role(str, Enum):
    ADMIN = "admin"
    ENGINEER = "engineer"
    VIEWER = "viewer"


ROLE_HIERARCHY: dict[Role, int] = {Role.VIEWER: 0, Role.ENGINEER: 1, Role.ADMIN: 2}


def role_gte(user_role: Role, required: Role) -> bool:
    return ROLE_HIERARCHY[user_role] >= ROLE_HIERARCHY[required]


def hash_password(plain: str) -> str:
    # Use bcrypt directly — passlib 1.7.x is incompatible with bcrypt >= 4.0
    return _bcrypt_lib.hashpw(plain.encode("utf-8"), _bcrypt_lib.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt_lib.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _create_token(subject, token_type, extra_claims=None, expires_delta=None) -> str:
    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.jwt_access_token_expire_minutes)
            if token_type == "access"
            else timedelta(days=settings.jwt_refresh_token_expire_days)
        )
    payload: dict[str, Any] = {
        "sub": str(subject), "type": token_type, "iat": now, "exp": now + expires_delta
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.app_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id, role: Role) -> str:
    return _create_token(user_id, "access", extra_claims={"role": role.value})


def create_refresh_token(user_id) -> str:
    return _create_token(user_id, "refresh")


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        log.warning("jwt_decode_failed", error=str(exc))
        raise


def extract_user_id(token: str) -> str:
    return decode_token(token)["sub"]


def extract_role(token: str) -> Role:
    return Role(decode_token(token)["role"])


from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    """Derive a Fernet key from CREDENTIAL_ENCRYPTION_KEY (separate from JWT secret)."""
    import base64, hashlib
    key = hashlib.sha256(settings.credential_encryption_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string for storage."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a stored credential string."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
