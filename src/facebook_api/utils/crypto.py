from cryptography.fernet import Fernet

from facebook_api.config import settings


def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        raise ValueError("ENCRYPTION_KEY not set in environment")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_data(data: str) -> str:
    f = _get_fernet()
    return f.encrypt(data.encode()).decode()


def decrypt_data(encrypted: str) -> str:
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()
