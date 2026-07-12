"""Token encryption helpers.

LinkedIn access tokens are stored encrypted in the database. In production,
set ENCRYPTION_KEY to a dedicated Fernet key so token encryption is independent
of SECRET_KEY. If ENCRYPTION_KEY is not provided, a key is derived from
SECRET_KEY using HKDF (not a simple SHA256 hash) with domain separation.
"""

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import config

logger = logging.getLogger(__name__)

_DERIVE_INFO = b"linkedin-auto-poster-token-encryption-v1"


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte URL-safe base64 Fernet key using HKDF-SHA256."""
    key_material = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_DERIVE_INFO,
    ).derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(key_material)


def _legacy_derive_key(secret: str) -> bytes:
    """Legacy key derivation kept only for decrypting old tokens."""
    import hashlib

    key_material = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(key_material)


def _get_fernet() -> Fernet:
    if config.ENCRYPTION_KEY:
        return Fernet(config.ENCRYPTION_KEY.encode("utf-8"))
    if not config.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not configured. Token encryption cannot work."
        )
    return Fernet(_derive_key(config.SECRET_KEY))


def _get_legacy_fernet() -> Fernet | None:
    if config.ENCRYPTION_KEY or not config.SECRET_KEY:
        return None
    return Fernet(_legacy_derive_key(config.SECRET_KEY))


def encrypt(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(value: str) -> str:
    if not value:
        return ""
    primary = _get_fernet()
    try:
        return primary.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        legacy = _get_legacy_fernet()
        if legacy is None:
            raise
        try:
            plaintext = legacy.decrypt(value.encode("utf-8")).decode("utf-8")
            logger.info("Decrypted token using legacy key derivation")
            return plaintext
        except InvalidToken:
            raise
