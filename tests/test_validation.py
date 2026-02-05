"""Tests for validation module."""

import pytest

from aicert.validation import (
    validate_json,
    parse_output,
    validate_schema,
    validate_output,
    ValidationResult,
    extract_json_from_block,
    extract_json_basic,
)


class TestExtractJsonFromBlock:
    """Tests for JSON block extraction."""

    def test_extract_json_block_simple(self):
        """Test extracting JSON from a simple code block."""
        text = "Here is some text\n```json\n{\"name\": \"Alice\"}\n```\nMore text"
        result = extract_json_from_block(text)
        assert result == '{"name": "Alice"}'

    def test_extract_json_block_with_newlines(self):
        """Test extracting JSON with newlines in block."""
        text = "```json\n{\n  \"name\": \"Alice\",\n  \"age\": 30\n}\n```"
        result = extract_json_from_block(text)
        assert result == '{\n  "name": "Alice",\n  "age": 30\n}'

    def test_extract_json_block_array(self):
        """Test extracting JSON array from block."""
        text = "```json\n[1, 2, 3, 4, 5]\n```"
        result = extract_json_from_block(text)
        assert result == '[1, 2, 3, 4, 5]'

    def test_no_json_block(self):
        """Test when no JSON block exists."""
        text = "This is just plain text without any code blocks"
        result = extract_json_from_block(text)
        assert result is None


class TestExtractJsonBasic:
    """Tests for basic JSON extraction from text."""

    def test_extract_object(self):
        """Test extracting a JSON object."""
        text = 'Here is some text {"name": "Alice"} more text'
        result = extract_json_basic(text)
        assert result == '{"name": "Alice"}'

    def test_extract_array(self):
        """Test extracting a JSON array."""
        text = 'Some text [1, 2, 3] more text'
        result = extract_json_basic(text)
        assert result == '[1, 2, 3]'

    def test_extract_nested_object(self):
        """Test extracting nested JSON."""
        text = 'Data: {"person": {"name": "Alice"}} end'
        result = extract_json_basic(text)
        assert result == '{"person": {"name": "Alice"}}'

    def test_no_json(self):
        """Test when no JSON exists."""
        text = "This is just plain text"
        result = extract_json_basic(text)
        assert result is None


class TestParseOutput:
    """Tests for parse_output function."""

    def test_parse_output_extract_json_block(self):
        """Test parsing JSON from a code block."""
        text = "Here is the result:\n```json\n{\"name\": \"Alice\"}\n```"
        ok, parsed, error = parse_output(text, extract_json=True)
        assert ok is True
        assert parsed == {"name": "Alice"}
        assert error is None

    def test_parse_output_extract_json_basic(self):
        """Test parsing JSON from plain text."""
        text = "Here is the result: {\"name\": \"Bob\"}"
        ok, parsed, error = parse_output(text, extract_json=True)
        assert ok is True
        assert parsed == {"name": "Bob"}
        assert error is None

    def test_parse_output_no_extract_json(self):
        """Test parsing entire text as JSON when extract_json=False."""
        text = '{"name": "Charlie"}'
        ok, parsed, error = parse_output(text, extract_json=False)
        assert ok is True
        assert parsed == {"name": "Charlie"}
        assert error is None

    def test_parse_output_invalid_json(self):
        """Test parsing invalid JSON fails."""
        text = "```json\n{invalid json}\n```"
        ok, parsed, error = parse_output(text, extract_json=True)
        assert ok is False
        assert parsed is None
        assert error is not None
        assert "Invalid JSON" in error

    def test_parse_output_no_json_found(self):
        """Test when no JSON is found."""
        text = "This is just plain text"
        ok, parsed, error = parse_output(text, extract_json=True)
        assert ok is False
        assert parsed is None
        assert error is not None
        assert "No JSON found" in error


class TestValidateSchema:
    """Tests for schema validation."""

    def test_validate_schema_valid(self):
        """Test valid schema validation."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"}
            },
            "required": ["name"]
        }
        data = {"name": "Alice", "age": 30}
        ok, error, extra_keys = validate_schema(data, schema)
        assert ok is True
        assert error is None
        assert extra_keys == []

    def test_validate_schema_missing_required(self):
        """Test validation fails for missing required field."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"}
            },
            "required": ["name", "age"]
        }
        data = {"name": "Alice"}
        ok, error, extra_keys = validate_schema(data, schema)
        assert ok is False
        assert "required" in error.lower() or "Schema validation" in error

    def test_validate_schema_invalid_type(self):
        """Test validation fails for wrong type."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"]
        }
        data = {"name": 123}
        ok, error, extra_keys = validate_schema(data, schema)
        assert ok is False
        assert error is not None

    def test_validate_schema_extra_keys_strict(self):
        """Test extra keys are flagged in strict mode."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "additionalProperties": False
        }
        data = {"name": "Alice", "extra_key": "value"}
        ok, error, extra_keys = validate_schema(data, schema, allow_extra_keys=False)
        assert ok is False
        assert "extra_key" in error or len(extra_keys) > 0

    def test_validate_schema_extra_keys_allowed(self):
        """Test extra keys are allowed in non-strict mode."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "additionalProperties": False
        }
        data = {"name": "Alice", "extra_key": "value"}
        ok, error, extra_keys = validate_schema(data, schema, allow_extra_keys=True)
        assert ok is True
        assert error is None


class TestValidateOutput:
    """Tests for the main validate_output function."""

    def test_validate_output_success(self):
        """Test successful validation."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"]
        }
        text = '{"name": "Alice"}'
        result = validate_output(text, schema, extract_json=False)
        assert result.ok_json is True
        assert result.ok_schema is True
        assert result.error is None
        assert result.parsed == {"name": "Alice"}

    def test_validate_output_json_block(self):
        """Test validation with JSON code block."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"]
        }
        text = "```json\n{\"name\": \"Bob\"}\n```"
        result = validate_output(text, schema, extract_json=True)
        assert result.ok_json is True
        assert result.ok_schema is True

    def test_validate_output_bad_json(self):
        """Test validation with bad JSON."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            }
        }
        text = "not valid json"
        result = validate_output(text, schema, extract_json=True)
        assert result.ok_json is False
        assert result.error is not None

    def test_validate_output_extra_keys_strict(self):
        """Test validation with extra keys in strict mode."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "additionalProperties": False
        }
        text = '{"name": "Charlie", "age": 30}'
        result = validate_output(text, schema, extract_json=False, allow_extra_keys=False)
        assert result.ok_json is True
        assert result.ok_schema is False
        assert len(result.extra_keys) > 0


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        result = ValidationResult()
        assert result.ok_json is False
        assert result.ok_schema is False
        assert result.extra_keys == []
        assert result.error is None
        assert result.parsed is None

    def test_with_values(self):
        """Test setting values."""
        result = ValidationResult(
            ok_json=True,
            ok_schema=True,
            extra_keys=["key1", "key2"],
            parsed={"test": "data"}
        )
        assert result.ok_json is True
        assert result.ok_schema is True
        assert result.extra_keys == ["key1", "key2"]
        assert result.parsed == {"test": "data"}
