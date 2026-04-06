"""Derivação de senha (PBKDF2-HMAC-SHA256) para utilizadores na BD — só stdlib."""

from __future__ import annotations

import hashlib
import secrets

_ITERATIONS = 390_000


def hash_password(plain: str) -> str:
    """Devolve string persistível: ``iterations$salt_hex$dk_hex``."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        plain.encode("utf-8"),
        salt,
        _ITERATIONS,
        dklen=32,
    )
    return f"{_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        if len(parts) != 3:
            return False
        iterations = int(parts[0])
        salt = bytes.fromhex(parts[1])
        expected = bytes.fromhex(parts[2])
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            plain.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected),
        )
        return secrets.compare_digest(dk, expected)
    except (ValueError, TypeError, OSError):
        return False
