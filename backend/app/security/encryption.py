"""API key encryption utilities."""

import base64
import hashlib
import os
from typing import Tuple

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings


def _get_fernet_key() -> bytes:
    """Derive a Fernet-compatible key from the encryption key."""
    # Use PBKDF2 to derive a proper 32-byte key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"professor_salt_v1",  # Fixed salt for consistency
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(settings.encryption_key.encode()))
    return key


def encrypt_api_key(api_key: str) -> Tuple[bytes, bytes]:
    """
    Encrypt an API key using Fernet symmetric encryption.
    
    Returns:
        Tuple of (encrypted_key, iv/nonce)
    """
    key = _get_fernet_key()
    fernet = Fernet(key)
    
    # Generate a random IV for additional security
    iv = os.urandom(16)
    
    # Combine IV with the key before encryption for uniqueness
    combined = iv + api_key.encode()
    
    encrypted = fernet.encrypt(combined)
    
    return encrypted, iv


def decrypt_api_key(encrypted_key: bytes, iv: bytes) -> str:
    """
    Decrypt an API key.
    
    Args:
        encrypted_key: The encrypted key bytes
        iv: The IV/nonce used during encryption
        
    Returns:
        The decrypted API key
    """
    key = _get_fernet_key()
    fernet = Fernet(key)
    
    decrypted = fernet.decrypt(encrypted_key)
    
    # Remove the IV prefix
    api_key = decrypted[16:].decode()
    
    return api_key


def hash_api_key(api_key: str) -> str:
    """
    Create a hash of the API key for validation without decryption.
    
    This allows checking if a key matches without decrypting.
    """
    # Use SHA-256 with a salt
    salted = f"professor_hash_{api_key}".encode()
    return hashlib.sha256(salted).hexdigest()


async def validate_openai_key(api_key: str) -> bool:
    """
    Validate an OpenAI API key by making a test request.
    
    Returns:
        True if the key is valid, False otherwise
    """
    import httpx
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            return response.status_code == 200
    except Exception:
        return False
