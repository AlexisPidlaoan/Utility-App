"""Password hashing with hashlib: PBKDF2-HMAC-SHA256 and a random salt per user.

Stored format:  pbkdf2_sha256$<rounds>$<salt in hex>$<hash in hex>
Plain-text passwords are never stored.
"""
import hashlib
import hmac
import os

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200_000
SALT_BYTES = 16


def hash_password(password, salt=None):
    """Hash a password with a fresh random salt (or the given salt)."""
    salt = salt or os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    """Re-hash the password with the stored salt and compare in constant time."""
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


# Checked when a login names an unknown user, so the response takes as long as a real one.
DUMMY_HASH = hash_password("dummy-password-for-timing")
