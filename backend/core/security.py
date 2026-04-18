"""
Symmetric encryption for stored API keys using Fernet (AES-128-CBC + HMAC-SHA256).
The master secret_key from settings is used to derive the Fernet key via HKDF-SHA256
so that the encryption key is properly domain-separated from the raw secret.
"""
import base64
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException
from .config import get_settings

# HKDF info label — changing this would invalidate all stored ciphertexts,
# so treat it as an opaque constant tied to this application.
_HKDF_INFO = b"llm-eval-platform-fernet-v1"


def safe_bench_path(bench_library_path: str, dataset_path: str) -> Path:
    """Resolve dataset_path relative to bench_library_path and verify it stays inside.

    Raises HTTP 400 if the resolved path escapes the bench_library root (path traversal).
    Returns the resolved absolute Path on success.
    """
    root = Path(bench_library_path).resolve()
    candidate = (root / dataset_path).resolve()
    if not str(candidate).startswith(str(root)):
        raise HTTPException(status_code=400, detail="Invalid dataset path.")
    return candidate


def _get_fernet() -> Fernet:
    settings = get_settings()
    # Derive a 32-byte key using HKDF-SHA256 (RFC 5869).
    # This provides proper domain separation and makes future key rotation
    # possible by bumping the info label alongside a re-encryption migration.
    raw = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    ).derive(settings.secret_key.encode())
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
