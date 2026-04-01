"""
Field-level encryption using Fernet (AES-128-CBC + HMAC-SHA256).

Used to encrypt sensitive audit log fields (user_query, response_text)
at rest, so the database alone is insufficient to read conversation content.

Key management:
  - FIELD_ENCRYPTION_KEY must be a 32-byte URL-safe base64 string.
  - Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  - Store in environment variables / secrets manager — never hardcode.
"""
from cryptography.fernet import Fernet, InvalidToken
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

settings = get_settings()

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not settings.FIELD_ENCRYPTION_KEY:
            raise RuntimeError(
                "FIELD_ENCRYPTION_KEY is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        _fernet = Fernet(settings.FIELD_ENCRYPTION_KEY.encode())
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns a URL-safe base64 ciphertext string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string. Returns original plaintext."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Decryption failed — possible key mismatch or tampered ciphertext")
        return "[decryption error — key mismatch or tampered data]"


def encrypt_if_enabled(value: str) -> str:
    """Encrypt only when a key is configured; pass through otherwise.
    Allows the feature to be opt-in in development."""
    return encrypt(value) if settings.FIELD_ENCRYPTION_KEY else value


def decrypt_if_enabled(value: str) -> str:
    """Decrypt only when a key is configured; pass through otherwise."""
    return decrypt(value) if settings.FIELD_ENCRYPTION_KEY else value
