"""Hashing helpers for aicert."""

import hashlib
from pathlib import Path


def sha256_bytes(b: bytes) -> str:
    """Compute SHA-256 hash of bytes and return as 'sha256:<hex>' format.

    Args:
        b: Bytes to hash.

    Returns:
        String in format "sha256:<hex>" where <hex> is the lowercase SHA-256 hex digest.
    """
    return f"sha256:{hashlib.sha256(b).hexdigest()}"


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file and return as 'sha256:<hex>' format.

    Args:
        path: Path to the file to hash.

    Returns:
        String in format "sha256:<hex>" where <hex> is the lowercase SHA-256 hex digest.
    """
    return sha256_bytes(path.read_bytes())
