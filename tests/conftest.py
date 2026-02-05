"""Pytest configuration and fixtures."""

import os
import shutil
from pathlib import Path

import pytest

# Add Path.copy_to compatibility method for Python < 3.8
if not hasattr(Path, 'copy_to'):
    def _copy_to(self, dst):
        """Copy file to destination, similar to shutil.copy2 but returns Path."""
        shutil.copy2(self, dst)
        return Path(dst)
    Path.copy_to = _copy_to


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set up test environment for all tests.
    
    This fixture ensures that test environment variables are set
    for all tests.
    """
    yield {}
