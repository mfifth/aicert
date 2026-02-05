"""Validation utilities for aicert."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from jsonschema import ValidationError, validate


@dataclass
class ValidationResult:
    """Result of validating LLM output."""
    ok_json: bool = False
    ok_schema: bool = False
    extra_keys: List[str] = field(default_factory=list)
    error: Optional[str] = None
    parsed: Optional[Any] = None


def extract_json_from_block(text: str) -> Optional[str]:
    """Extract JSON from a ```json ... ``` block."""
    # Match ```json at start of line, followed by any content, ending with ```
    pattern = r'```json\s*\n(.*?)\n```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def extract_json_basic(text: str) -> Optional[str]:
    """Basic extraction of first JSON object/array from text."""
    # Find the first { or [ that starts a JSON object/array
    text = text.strip()
    
    # Find first { or [ at the start or after whitespace
    start_idx = -1
    for i, char in enumerate(text):
        if char == '{':
            start_idx = i
            break
        elif char == '[':
            start_idx = i
            break
    
    if start_idx == -1:
        return None
    
    # Try to parse from this position
    # We'll try to find the matching closing bracket
    end_idx = -1
    stack = []
    for i in range(start_idx, len(text)):
        char = text[i]
        if char == '{' or char == '[':
            stack.append(char)
        elif char == '}' or char == ']':
            if not stack:
                continue
            opening = stack.pop()
            if (opening == '{' and char == '}') or (opening == '[' and char == ']'):
                if not stack:
                    end_idx = i + 1
                    break
    
    if end_idx > 0:
        return text[start_idx:end_idx]
    
    # Fallback: try to find any closing bracket at the end
    # This is a simple heuristic
    if start_idx == 0:
        # Try to find the last } or ]
        for i in range(len(text) - 1, start_idx - 1, -1):
            if text[i] in '}]':
                return text[start_idx:i + 1]
    
    return None


def parse_output(text: str, extract_json: bool) -> tuple[bool, Any | None, str | None]:
    """
    Parse output text to extract JSON.
    
    Args:
        text: The raw output text from the LLM
        extract_json: Whether to try extracting JSON from blocks or text
        
    Returns:
        Tuple of (ok_json: bool, parsed: Any|None, error: str|None)
    """
    if extract_json:
        # Try to extract from ```json block first
        json_text = extract_json_from_block(text)
        if json_text is None:
            # Fall back to basic extraction
            json_text = extract_json_basic(text)
        
        if json_text is None:
            return False, None, "No JSON found in output"
    else:
        # Use entire text as JSON
        json_text = text
    
    if json_text is None:
        return False, None, "No JSON found in output"
    
    try:
        parsed = json.loads(json_text)
        return True, parsed, None
    except json.JSONDecodeError as e:
        return False, None, f"Invalid JSON: {str(e)}"


def find_extra_keys(obj: Any, schema: Dict[str, Any], parent_path: str = "") -> List[str]:
    """
    Find extra keys in an object that are not in the schema.
    
    Args:
        obj: The parsed JSON object
        schema: The JSON schema
        parent_path: Path for error reporting
        
    Returns:
        List of extra key names
    """
    extra_keys: List[str] = []
    
    if not isinstance(obj, dict) or not isinstance(schema, dict):
        return extra_keys
    
    # Check if this object has additionalProperties: false
    additional_properties = schema.get("additionalProperties", None)
    is_strict = additional_properties is False
    
    # Get defined properties
    properties = schema.get("properties", {})
    required_fields = schema.get("required", [])
    
    for key, value in obj.items():
        key_path = f"{parent_path}.{key}" if parent_path else key
        
        if key in properties:
            # Key is defined, check nested schema
            prop_schema = properties[key]
            if isinstance(prop_schema, dict):
                # Recursively check nested objects
                nested_extra = find_extra_keys(value, prop_schema, key_path)
                extra_keys.extend(nested_extra)
        elif is_strict:
            # Key not defined and additionalProperties is false
            extra_keys.append(key_path)
    
    return extra_keys


def remove_additional_properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Remove additionalProperties from schema and nested schemas."""
    if not isinstance(schema, dict):
        return schema
    
    result = {}
    for key, value in schema.items():
        if key == "additionalProperties":
            continue
        elif key == "properties" and isinstance(value, dict):
            result[key] = {k: remove_additional_properties(v) for k, v in value.items()}
        elif isinstance(value, dict):
            result[key] = remove_additional_properties(value)
        else:
            result[key] = value
    return result


def validate_schema(parsed: Any, schema: Dict[str, Any], allow_extra_keys: bool = True) -> tuple[bool, str | None, List[str]]:
    """
    Validate parsed JSON against a schema.
    
    Args:
        parsed: The parsed JSON object
        schema: The JSON schema
        allow_extra_keys: If False, enforce that no extra keys exist
        
    Returns:
        Tuple of (ok_schema: bool, error: str|None, extra_keys: List[str])
    """
    extra_keys: List[str] = []
    
    if not isinstance(schema, dict):
        return True, None, []
    
    # Check for strict mode - extra key enforcement
    if not allow_extra_keys:
        extra_keys = find_extra_keys(parsed, schema)
        if extra_keys:
            return False, f"Extra keys not allowed: {', '.join(extra_keys)}", extra_keys
    
    # If allow_extra_keys=True, remove additionalProperties restriction
    # before validation to allow extra keys
    validation_schema = schema if allow_extra_keys else schema
    if allow_extra_keys and schema.get("additionalProperties") is False:
        validation_schema = remove_additional_properties(schema)
    
    try:
        validate(instance=parsed, schema=validation_schema)
        return True, None, extra_keys
    except ValidationError as e:
        return False, f"Schema validation error: {e.message}", extra_keys


def validate_output(
    text: str,
    schema: Dict[str, Any],
    extract_json: bool,
    allow_extra_keys: bool = True
) -> ValidationResult:
    """
    Validate LLM output against a schema.
    
    Args:
        text: The raw output text from the LLM
        schema: The JSON schema to validate against
        extract_json: Whether to try extracting JSON from blocks
        allow_extra_keys: If False, enforce that no extra keys exist
        
    Returns:
        ValidationResult with ok_json, ok_schema, extra_keys, and error
    """
    # Step 1: Parse JSON from output
    ok_json, parsed, error = parse_output(text, extract_json)
    
    if not ok_json:
        return ValidationResult(
            ok_json=False,
            ok_schema=False,
            error=error
        )
    
    # Step 2: Validate against schema
    ok_schema, schema_error, extra_keys = validate_schema(parsed, schema, allow_extra_keys)
    
    return ValidationResult(
        ok_json=True,
        ok_schema=ok_schema,
        extra_keys=extra_keys,
        error=schema_error,
        parsed=parsed
    )


# Keep old functions for backward compatibility

class SchemaLoadError(Exception):
    """Error raised when schema loading fails."""

    def __init__(self, message: str, schema_path: str = None, hint: str = None):
        self.message = message
        self.schema_path = schema_path
        self.hint = hint
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format the error message with context."""
        parts = []
        if self.schema_path:
            parts.append(f"[bold red]Schema file: {self.schema_path}[/bold red]")
        parts.append(f"[bold red]Error:[/bold red] {self.message}")
        if self.hint:
            parts.append(f"[bold yellow]Hint:[/bold yellow] {self.hint}")
        return "\n".join(parts)


def load_json_schema(schema_path: str) -> Dict[str, Any]:
    """Load a JSON schema from a file with better error messages."""
    import yaml
    from pathlib import Path

    try:
        with open(schema_path, "r") as f:
            schema = yaml.safe_load(f)
    except FileNotFoundError:
        raise SchemaLoadError(
            message=f"Schema file not found: {schema_path}",
            schema_path=schema_path,
            hint="Make sure the path is correct and the file exists."
        )
    except yaml.YAMLError as e:
        raise SchemaLoadError(
            message=f"Invalid YAML in schema file: {e}",
            schema_path=schema_path,
            hint="Check for syntax errors like incorrect indentation."
        )
    except Exception as e:
        raise SchemaLoadError(
            message=f"Failed to load schema: {e}",
            schema_path=schema_path,
            hint="Make sure the file is valid JSON or YAML."
        )

    # Validate that it's a dict (could be JSON or YAML parsed)
    if not isinstance(schema, dict):
        raise SchemaLoadError(
            message=f"Schema must be a dictionary/object, got {type(schema).__name__}",
            schema_path=schema_path,
            hint="The schema file should contain a JSON object with '$schema', 'type', 'properties', etc."
        )

    return schema


def validate_json(data: Any, schema: Dict[str, Any]) -> bool:
    """Validate JSON data against a schema."""
    validate(instance=data, schema=schema)
    return True


def validate_json_file(data_path: str, schema_path: str) -> bool:
    """Validate a JSON file against a schema."""
    import yaml
    with open(data_path, "r") as f:
        data = yaml.safe_load(f)
    schema = load_json_schema(schema_path)
    return validate_json(data, schema)
