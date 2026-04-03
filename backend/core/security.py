"""
Symmetric encryption for stored API keys using Fernet (AES-128-CBC + HMAC-SHA256).
The master secret_key from settings is used to derive the Fernet key.
"""
import base64
import hashlib
from cryptography.fernet import Fernet
from .config import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    # Derive a 32-byte key from the secret_key string
    raw = hashlib.sha256(settings.secret_key.encode()).digest()
    key = base64.urlsafe_b64encode(raw)
    return Fernet(key)


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt a plaintext API key for storage."""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    """Decrypt a stored API key for use."""
    if not ciphertext:
        return ""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
