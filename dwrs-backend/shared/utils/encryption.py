"""
Encryption utilities for PII fields.
All Aadhaar numbers, names, and mobile numbers are encrypted at rest.
"""
import hashlib
import hmac
import base64
from cryptography.fernet import Fernet
from passlib.context import CryptContext
from shared.utils.config import settings

_fernet: Fernet | None = None
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.ENCRYPTION_KEY.encode())
    return _fernet


# ── Symmetric encryption (Fernet AES-128-CBC + HMAC) ───────────────────────

def encrypt(plaintext: str) -> bytes:
    """Encrypt a string. Returns bytes for storage in BYTEA column."""
    return _get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext: bytes) -> str:
    """Decrypt bytes back to string."""
    return _get_fernet().decrypt(ciphertext).decode("utf-8")


# ── Hashing (one-way, for deduplication) ────────────────────────────────────

def hash_with_salt(value: str, salt: str) -> str:
    """
    HMAC-SHA256 hash for deduplication fields (Aadhaar, mobile).
    Using HMAC (not plain SHA256) prevents rainbow table attacks.
    """
    return hmac.new(
        salt.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ── Password hashing ─────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


# ── Masked display (for logs and UI) ─────────────────────────────────────────

def mask_aadhaar(aadhaar: str) -> str:
    """Returns XXXXXXXX1234 — last 4 digits only."""
    return "X" * 8 + aadhaar[-4:]


def mask_mobile(mobile: str) -> str:
    """Returns XXXXXX1234 — last 4 digits only."""
    if len(mobile) >= 4:
        return "X" * (len(mobile) - 4) + mobile[-4:]
    return "XXXX"
