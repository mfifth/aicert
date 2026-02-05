"""Templating utilities for aicert."""

import re
from string import Template
from typing import Any, Dict, Optional


def render_template(template: str, variables: Dict[str, Any]) -> str:
    """Render a template string with variables."""
    t = Template(template)
    return t.substitute(**variables)


def render_template_file(path: str, variables: Dict[str, Any]) -> str:
    """Render a template file with variables."""
    with open(path, "r") as f:
        template = f.read()
    return render_template(template, variables)


def build_schema_hint(schema: dict) -> str:
    """Build a deterministic, compact schema hint from a JSON schema.
    
    Includes required keys and their types (shallow extraction).
    Output is deterministic and compact.
    """
    if not isinstance(schema, dict):
        return ""
    
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    
    # Build hint for required fields with their types
    hints = []
    for key in sorted(required):  # sorted for determinism
        prop = properties.get(key, {})
        prop_type = prop.get("type", "any")
        hints.append(f"{key}: {prop_type}")
    
    return " | ".join(hints) if hints else ""


def render_prompt(
    template: str, 
    case: dict, 
    schema_hint: str, 
    case_id: Optional[str] = None
) -> str:
    """Render a prompt template with placeholders.
    
    Supports {{ key }} placeholders with optional whitespace.
    Injects schema_hint automatically.
    Raises an error if any placeholder key is missing.
    """
    # Build variables dict from case, including schema_hint
    variables = dict(case)
    if schema_hint:
        variables["schema_hint"] = schema_hint
    
    # Pattern to match {{ key }} with optional whitespace
    pattern = re.compile(r'\{\{\s*(\w+)\s*\}\}')
    
    # Find all placeholders and check for missing keys
    missing_keys = []
    for match in pattern.finditer(template):
        key = match.group(1)
        if key not in variables:
            missing_keys.append(key)
    
    if missing_keys:
        case_info = f" (case_id: {case_id})" if case_id else ""
        missing_str = ", ".join(missing_keys)
        raise ValueError(
            f"Missing placeholder value(s) in template: {missing_str}{case_info}"
        )
    
    # Replace all placeholders
    result = pattern.sub(
        lambda m: str(variables[m.group(1)]),
        template
    )
    
    return result
