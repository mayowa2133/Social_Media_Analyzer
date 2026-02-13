"""
Token encryption/decryption service using Fernet symmetric encryption.
"""

import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from config import settings


def _get_fernet() -> Fernet:
    """Get Fernet instance from encryption key."""
    key = settings.ENCRYPTION_KEY
    
    # If key is not 32 bytes, derive a key using PBKDF2
    if len(key) != 32:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"social_performance_coach_salt",
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(key.encode()))
    else:
        key = base64.urlsafe_b64encode(key.encode())
    
    return Fernet(key)


def encrypt_token(token: str) -> str:
    """
    Encrypt a token for secure storage.
    
    Args:
        token: Plain text token
        
    Returns:
        Base64-encoded encrypted token
    """
    fernet = _get_fernet()
    encrypted = fernet.encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt an encrypted token.
    
    Args:
        encrypted_token: Base64-encoded encrypted token
        
    Returns:
        Plain text token
    """
    fernet = _get_fernet()
    decrypted = fernet.decrypt(encrypted_token.encode())
    return decrypted.decode()


def generate_encryption_key() -> str:
    """Generate a new random encryption key for .env file."""
    return Fernet.generate_key().decode()
