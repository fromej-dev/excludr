"""Password hashing helpers built directly on ``bcrypt``."""

import bcrypt

# bcrypt only uses the first 72 bytes of the password. bcrypt>=5 raises on longer
# input, so truncate explicitly (matching the previous passlib behaviour).
_BCRYPT_MAX_BYTES = 72


def _encode(password: str) -> bytes:
    """Encode a password to bytes, truncated to bcrypt's 72-byte limit."""
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt.

    Args:
        password: Plain-text password.

    Returns:
        The bcrypt hash as a ``$2b$`` string.
    """
    return bcrypt.hashpw(_encode(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash.

    Args:
        plain_password: Plain-text password to check.
        hashed_password: Stored bcrypt hash.

    Returns:
        True if the password matches, False otherwise (including malformed hashes).
    """
    try:
        return bcrypt.checkpw(_encode(plain_password), hashed_password.encode("utf-8"))
    except ValueError:
        return False
