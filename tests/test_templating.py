"""Tests for templating module."""

import pytest

from aicert.templating import render_template, render_template_file


def test_render_template_basic():
    """Test basic template rendering."""
    template = "Hello, $name!"
    result = render_template(template, {"name": "World"})
    assert result == "Hello, World!"


def test_render_template_multiple_vars():
    """Test template with multiple variables."""
    template = "$greeting, $name! Today is $day."
    result = render_template(template, {
        "greeting": "Good morning",
        "name": "Alice",
        "day": "Monday"
    })
    assert result == "Good morning, Alice! Today is Monday."


def test_render_template_missing_var():
    """Test template with missing variable raises error."""
    template = "Hello, $name!"
    with pytest.raises(KeyError):
        render_template(template, {})
