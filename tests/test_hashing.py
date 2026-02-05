"""Tests for hashing utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.aicert.hashing import sha256_bytes, sha256_file


# Known SHA-256 hash of "hello" for testing
HELLO_HASH = "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


class TestSha256Bytes:
    """Tests for the sha256_bytes function."""

    def test_known_hash(self):
        """Test that sha256_bytes returns correct hash for known input."""
        result = sha256_bytes(b"hello")
        assert result == HELLO_HASH

    def test_empty_bytes(self):
        """Test that empty bytes returns empty hash."""
        result = sha256_bytes(b"")
        assert result == "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_format_prefix(self):
        """Test that output format has correct prefix."""
        result = sha256_bytes(b"test")
        assert result.startswith("sha256:")
        assert result.split(":")[1] is not None

    def test_stable_output(self):
        """Test that sha256_bytes produces stable, deterministic output."""
        result1 = sha256_bytes(b"stable input")
        result2 = sha256_bytes(b"stable input")
        assert result1 == result2


class TestSha256File:
    """Tests for the sha256_file function."""

    def test_file_hash_matches_bytes_hash(self, tmp_path: Path):
        """Test that sha256_file produces same hash as sha256_bytes for same content."""
        content = b"file content test"
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(content)

        file_hash = sha256_file(test_file)
        bytes_hash = sha256_bytes(content)

        assert file_hash == bytes_hash

    def test_known_file_hash(self, tmp_path: Path):
        """Test that sha256_file returns correct hash for a file with known content."""
        test_file = tmp_path / "hello.txt"
        test_file.write_bytes(b"hello")

        result = sha256_file(test_file)
        assert result == HELLO_HASH

    def test_empty_file(self, tmp_path: Path):
        """Test hashing an empty file."""
        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")

        result = sha256_file(test_file)
        assert result == "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_stable_output(self, tmp_path: Path):
        """Test that sha256_file produces stable, deterministic output."""
        test_file = tmp_path / "stable.txt"
        test_file.write_bytes(b"stable content")

        hash1 = sha256_file(test_file)
        hash2 = sha256_file(test_file)
        assert hash1 == hash2

    def test_binary_file(self, tmp_path: Path):
        """Test hashing a binary file."""
        binary_content = bytes(range(256))
        test_file = tmp_path / "binary.bin"
        test_file.write_bytes(binary_content)

        result = sha256_file(test_file)
        assert result.startswith("sha256:")
        # Verify it's a valid 64-char hex string after the prefix
        hex_part = result.split(":")[1]
        assert len(hex_part) == 64
        assert all(c in "0123456789abcdef" for c in hex_part)
