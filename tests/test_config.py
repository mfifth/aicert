"""Tests for config module."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from aicert.config import (
    Config,
    ConfigLoadError,
    ProviderConfig,
    load_config,
)


def test_load_config_from_example():
    """Test that config loads correctly from examples/aicert.yaml."""
    config = load_config("examples/aicert.yaml")

    assert config.project == "example-project"
    assert len(config.providers) == 1
    assert config.providers[0].id == "fake-test"
    assert config.providers[0].provider == "fake"
    assert config.providers[0].model == "fake-model"
    assert config.providers[0].temperature == 0.1
    assert config.prompt_file == "prompt.txt"
    assert config.cases_file == "cases.jsonl"
    assert config.schema_file == "schema.json"
    assert config.runs == 10  # Updated for FakeAdapter
    assert config.concurrency == 5  # Updated for FakeAdapter
    assert config.timeout_s == 30


def test_defaults_apply():
    """Test that defaults apply when fields are omitted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)

        # Create mock referenced files
        (config_dir / "prompt.txt").write_text("test prompt")
        (config_dir / "cases.jsonl").write_text("{}")
        (config_dir / "schema.json").write_text("{}")

        config_data = {
            "project": "test-project",
            "providers": [
                {
                    "id": "test",
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.0,
                }
            ],
            "prompt_file": "prompt.txt",
            "cases_file": "cases.jsonl",
            "schema_file": "schema.json",
        }

        config_path = config_dir / "config.yaml"
        config_path.write_text(yaml.dump(config_data))

        config = load_config(str(config_path))

        assert config.runs == 50  # default
        assert config.concurrency == 10  # default
        assert config.timeout_s == 30  # default
        assert config.validation.extract_json is True  # default
        assert config.validation.allow_extra_keys is False  # default
        assert config.thresholds.min_stability == 85  # default
        assert config.thresholds.min_compliance == 95  # default
        assert config.ci.runs == 10  # default
        assert config.ci.save_on_fail is True  # default


def test_relative_path_resolution():
    """Test that relative paths are resolved relative to config file directory."""
    # Create a temporary directory structure
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "subdir"
        config_dir.mkdir()

        # Create mock referenced files
        (config_dir / "prompt.txt").write_text("test prompt")
        (config_dir / "cases.jsonl").write_text("{}")
        (config_dir / "schema.json").write_text("{}")

        # Create config with relative paths
        config_data = {
            "project": "test",
            "providers": [
                {
                    "id": "test",
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.0,
                }
            ],
            "prompt_file": "prompt.txt",
            "cases_file": "cases.jsonl",
            "schema_file": "schema.json",
        }

        config_path = config_dir / "config.yaml"
        config_path.write_text(yaml.dump(config_data))

        # Load should succeed since files exist relative to config
        config = load_config(str(config_path))

        assert config.prompt_file == "prompt.txt"
        assert config.cases_file == "cases.jsonl"
        assert config.schema_file == "schema.json"


def test_missing_referenced_file_raises_error():
    """Test that missing referenced files raise friendly error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)

        config_data = {
            "project": "test",
            "providers": [
                {
                    "id": "test",
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.0,
                }
            ],
            "prompt_file": "missing.txt",
            "cases_file": "cases.jsonl",
            "schema_file": "schema.json",
        }

        config_path = config_dir / "config.yaml"
        config_path.write_text(yaml.dump(config_data))

        with pytest.raises(ConfigLoadError) as exc_info:
            load_config(str(config_path))

        assert "missing.txt" in str(exc_info.value)
        assert "not found" in str(exc_info.value).lower()


def test_missing_config_file_raises_error():
    """Test that missing config file raises error."""
    with pytest.raises(ConfigLoadError) as exc_info:
        load_config("/nonexistent/path/config.yaml")

    assert "not found" in str(exc_info.value).lower()


def test_invalid_yaml_raises_error():
    """Test that invalid YAML raises ConfigLoadError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config_path.write_text("invalid: yaml: content: [[[")

        with pytest.raises(ConfigLoadError):
            load_config(str(config_path))


def test_provider_with_base_url():
    """Test provider configuration with base_url for openai_compatible."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)

        # Create mock referenced files
        (config_dir / "prompt.txt").write_text("test prompt")
        (config_dir / "cases.jsonl").write_text("{}")
        (config_dir / "schema.json").write_text("{}")

        config_data = {
            "project": "test",
            "providers": [
                {
                    "id": "custom",
                    "provider": "openai_compatible",
                    "model": "custom-model",
                    "temperature": 0.0,
                    "base_url": "https://api.custom.com/v1",
                }
            ],
            "prompt_file": "prompt.txt",
            "cases_file": "cases.jsonl",
            "schema_file": "schema.json",
        }

        config_path = config_dir / "config.yaml"
        config_path.write_text(yaml.dump(config_data))

        config = load_config(str(config_path))

        assert config.providers[0].base_url == "https://api.custom.com/v1"


def test_multiple_providers():
    """Test configuration with multiple providers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)

        # Create mock referenced files
        (config_dir / "prompt.txt").write_text("test prompt")
        (config_dir / "cases.jsonl").write_text("{}")
        (config_dir / "schema.json").write_text("{}")

        config_data = {
            "project": "test",
            "providers": [
                {
                    "id": "openai",
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.0,
                },
                {
                    "id": "anthropic",
                    "provider": "anthropic",
                    "model": "claude-3-opus-20240307",
                    "temperature": 0.0,
                },
            ],
            "prompt_file": "prompt.txt",
            "cases_file": "cases.jsonl",
            "schema_file": "schema.json",
        }

        config_path = config_dir / "config.yaml"
        config_path.write_text(yaml.dump(config_data))

        config = load_config(str(config_path))

        assert len(config.providers) == 2
        assert config.providers[0].id == "openai"
        assert config.providers[1].id == "anthropic"
        assert config.primary_provider.id == "openai"


def test_validation_settings():
    """Test validation configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)

        # Create mock referenced files
        (config_dir / "prompt.txt").write_text("test prompt")
        (config_dir / "cases.jsonl").write_text("{}")
        (config_dir / "schema.json").write_text("{}")

        config_data = {
            "project": "test",
            "providers": [
                {
                    "id": "test",
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.0,
                }
            ],
            "prompt_file": "prompt.txt",
            "cases_file": "cases.jsonl",
            "schema_file": "schema.json",
            "validation": {
                "extract_json": False,
                "allow_extra_keys": True,
            },
        }

        config_path = config_dir / "config.yaml"
        config_path.write_text(yaml.dump(config_data))

        config = load_config(str(config_path))

        assert config.validation.extract_json is False
        assert config.validation.allow_extra_keys is True


def test_thresholds_settings():
    """Test thresholds configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)

        # Create mock referenced files
        (config_dir / "prompt.txt").write_text("test prompt")
        (config_dir / "cases.jsonl").write_text("{}")
        (config_dir / "schema.json").write_text("{}")

        config_data = {
            "project": "test",
            "providers": [
                {
                    "id": "test",
                    "provider": "openai",
                    "model": "gpt-4",
                    "temperature": 0.0,
                }
            ],
            "prompt_file": "prompt.txt",
            "cases_file": "cases.jsonl",
            "schema_file": "schema.json",
            "thresholds": {
                "min_stability": 90,
                "min_compliance": 98,
                "max_cost_usd": 5.0,
                "p95_latency_ms": 2000,
            },
        }

        config_path = config_dir / "config.yaml"
        config_path.write_text(yaml.dump(config_data))

        config = load_config(str(config_path))

        assert config.thresholds.min_stability == 90
        assert config.thresholds.min_compliance == 98
        assert config.thresholds.max_cost_usd == 5.0
        assert config.thresholds.p95_latency_ms == 2000
