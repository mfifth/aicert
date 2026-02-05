"""Tests for CLI commands."""

import json
import os
import subprocess
import sys
import tempfile


def test_ci_json_format():
    """Test that ci command with --format json outputs valid JSON."""
    result = subprocess.run(
        [sys.executable, "-m", "aicert", "ci", "examples/fake_chaos/aicert.yaml", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    
    # Should exit with code 0 (pass) or 2 (fail) but not error
    assert result.returncode in [0, 2], f"Expected exit code 0 or 2, got {result.returncode}. stderr: {result.stderr}"
    
    # Parse stdout as JSON
    output = result.stdout.strip()
    assert output, "Expected JSON output but got empty stdout"
    
    parsed = json.loads(output)
    
    # Verify required fields
    assert "project" in parsed, "JSON output must contain 'project'"
    assert "providers" in parsed, "JSON output must contain 'providers'"
    assert "thresholds" in parsed, "JSON output must contain 'thresholds'"
    assert "pass" in parsed, "JSON output must contain 'pass'"
    assert "per_provider" in parsed, "JSON output must contain 'per_provider'"
    
    # Verify pass field is boolean
    assert isinstance(parsed["pass"], bool), "'pass' must be a boolean"
    
    # Verify providers is a list
    assert isinstance(parsed["providers"], list), "'providers' must be a list"
    assert len(parsed["providers"]) > 0, "'providers' must not be empty"
    
    # Verify per_provider structure
    for provider_id, metrics in parsed["per_provider"].items():
        assert "stability" in metrics, f"Provider {provider_id} must have 'stability'"
        assert "compliance" in metrics, f"Provider {provider_id} must have 'compliance'"
        assert "latency_stats" in metrics, f"Provider {provider_id} must have 'latency_stats'"
        assert "error_counts" in metrics, f"Provider {provider_id} must have 'error_counts'"
        
        # Verify latency_stats structure
        assert "p95_ms" in metrics["latency_stats"], "latency_stats must have 'p95_ms'"
        
        # Verify error_counts structure
        assert "json_parse_failures" in metrics["error_counts"], "error_counts must have 'json_parse_failures'"
        assert "schema_failures" in metrics["error_counts"], "error_counts must have 'schema_failures'"


def test_stability_dry_run_json_format():
    """Test that stability --dry-run --format json outputs valid JSON with total_requests."""
    result = subprocess.run(
        [sys.executable, "-m", "aicert", "stability", "examples/fake_chaos/aicert.yaml", "--dry-run", "--format", "json"],
        capture_output=True,
        text=True,
        
        timeout=60,
    )
    
    # Should exit with code 0 (success)
    assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
    
    # Parse stdout as JSON
    output = result.stdout.strip()
    assert output, "Expected JSON output but got empty stdout"
    
    parsed = json.loads(output)
    
    # Verify required fields
    assert "project" in parsed, "JSON output must contain 'project'"
    assert "providers" in parsed, "JSON output must contain 'providers'"
    assert "total_requests" in parsed, "JSON output must contain 'total_requests'"
    assert "cases_count" in parsed, "JSON output must contain 'cases_count'"
    assert "runs_per_case" in parsed, "JSON output must contain 'runs_per_case'"
    
    # Verify total_requests is an integer
    assert isinstance(parsed["total_requests"], int), "'total_requests' must be an integer"
    assert parsed["total_requests"] > 0, "'total_requests' must be greater than 0"
    
    # Verify providers is a list
    assert isinstance(parsed["providers"], list), "'providers' must be a list"
    assert len(parsed["providers"]) > 0, "'providers' must not be empty"
    
    # Verify provider structure
    for provider in parsed["providers"]:
        assert "id" in provider, "Provider must have 'id'"
        assert "provider" in provider, "Provider must have 'provider'"
        assert "model" in provider, "Provider must have 'model'"


def test_stability_json_format():
    """Test that stability command with --format json outputs valid JSON."""
    result = subprocess.run(
        [sys.executable, "-m", "aicert", "stability", "examples/fake_chaos/aicert.yaml", "--format", "json"],
        capture_output=True,
        text=True,
        
        timeout=120,
    )
    
    # Should exit with code 0 (success)
    assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
    
    # Parse stdout as JSON
    output = result.stdout.strip()
    assert output, "Expected JSON output but got empty stdout"
    
    parsed = json.loads(output)
    
    # Verify required fields
    assert "project" in parsed, "JSON output must contain 'project'"
    assert "providers" in parsed, "JSON output must contain 'providers'"
    assert "pass" in parsed, "JSON output must contain 'pass'"
    assert "per_provider" in parsed, "JSON output must contain 'per_provider'"
    
    # Verify pass field is boolean
    assert isinstance(parsed["pass"], bool), "'pass' must be a boolean"
    
    # Verify providers is a list
    assert isinstance(parsed["providers"], list), "'providers' must be a list"
    assert len(parsed["providers"]) > 0, "'providers' must not be empty"
    
    # Verify per_provider structure
    for provider_id, metrics in parsed["per_provider"].items():
        assert "stability" in metrics, f"Provider {provider_id} must have 'stability'"
        assert "compliance" in metrics, f"Provider {provider_id} must have 'compliance'"
        assert "latency_stats" in metrics, f"Provider {provider_id} must have 'latency_stats'"
        assert "error_counts" in metrics, f"Provider {provider_id} must have 'error_counts'"
        
        # Verify latency_stats structure
        assert "p95_ms" in metrics["latency_stats"], "latency_stats must have 'p95_ms'"
        
        # Verify error_counts structure
        assert "json_parse_failures" in metrics["error_counts"], "error_counts must have 'json_parse_failures'"
        assert "schema_failures" in metrics["error_counts"], "error_counts must have 'schema_failures'"



    """Test that init command creates all required files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Run init in temp directory
        result = subprocess.run(
            [sys.executable, "-m", "aicert", "init"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=30,
        )
        
        # Should exit with code 0
        assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
        
        # Verify all files were created
        expected_files = ["aicert.yaml", "prompt.txt", "cases.jsonl", "schema.json"]
        for filename in expected_files:
            filepath = os.path.join(tmpdir, filename)
            assert os.path.exists(filepath), f"File {filename} should exist"
        
        # Verify aicert_baselines/ directory was created
        baselines_dir = os.path.join(tmpdir, "aicert_baselines")
        assert os.path.isdir(baselines_dir), "aicert_baselines/ directory should exist"
        
        # Verify aicert.yaml content
        aicert_yaml_path = os.path.join(tmpdir, "aicert.yaml")
        with open(aicert_yaml_path, "r") as f:
            content = f.read()
        assert "project:" in content
        assert "providers:" in content
        
        # Verify schema.json has required fields
        schema_path = os.path.join(tmpdir, "schema.json")
        with open(schema_path, "r") as f:
            schema = json.load(f)
        assert "label" in schema.get("required", [])
        assert "confidence" in schema.get("required", [])
        
        # Verify cases.jsonl has 3 cases
        cases_path = os.path.join(tmpdir, "cases.jsonl")
        with open(cases_path, "r") as f:
            cases = f.readlines()
        assert len(cases) == 3, f"Expected 3 cases, got {len(cases)}"


def test_init_no_overwrite():
    """Test that init does not overwrite existing files without --force."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a pre-existing file
        existing_content = "# Custom existing content"
        with open(os.path.join(tmpdir, "aicert.yaml"), "w") as f:
            f.write(existing_content)
        
        # Run init without --force
        result = subprocess.run(
            [sys.executable, "-m", "aicert", "init"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=30,
        )
        
        # Should exit with code 0
        assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
        
        # Verify existing file was not overwritten
        with open(os.path.join(tmpdir, "aicert.yaml"), "r") as f:
            content = f.read()
        assert content == existing_content, "Existing file should not be overwritten"
        
        # Verify skipped message appears in output
        assert "Skipped" in result.stdout or "skipped" in result.stdout


def test_init_force_overwrite():
    """Test that init with --force overwrites existing files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a pre-existing file
        existing_content = "# Custom existing content"
        with open(os.path.join(tmpdir, "aicert.yaml"), "w") as f:
            f.write(existing_content)
        
        # Run init with --force
        result = subprocess.run(
            [sys.executable, "-m", "aicert", "init", "--force"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=30,
        )
        
        # Should exit with code 0
        assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
        
        # Verify existing file was overwritten
        with open(os.path.join(tmpdir, "aicert.yaml"), "r") as f:
            content = f.read()
        assert content != existing_content, "File should be overwritten with --force"
        assert "project:" in content
        
        # Verify overwrite message appears in output
        assert "Overwrote" in result.stdout or "overwrote" in result.stdout


def test_init_in_existing_project_dir():
    """Test that init works correctly in a directory with some existing files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a pre-existing schema.json (but not others)
        with open(os.path.join(tmpdir, "schema.json"), "w") as f:
            f.write('{"type": "object"}')
        
        # Run init without --force
        result = subprocess.run(
            [sys.executable, "-m", "aicert", "init"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=30,
        )
        
        # Should exit with code 0
        assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
        
        # Verify schema.json was NOT overwritten (since it exists)
        with open(os.path.join(tmpdir, "schema.json"), "r") as f:
            content = f.read()
        assert content == '{"type": "object"}', "Existing schema.json should not be overwritten"
        
        # Verify other files were created
        assert os.path.exists(os.path.join(tmpdir, "aicert.yaml"))
        assert os.path.exists(os.path.join(tmpdir, "prompt.txt"))
        assert os.path.exists(os.path.join(tmpdir, "cases.jsonl"))


def test_ci_failure_output_contains_examples():
    """Test that CI failure output contains example case_ids for debugging."""
    # Use fake_chaos config which has low thresholds to trigger failures
    result = subprocess.run(
        [sys.executable, "-m", "aicert", "ci", "examples/fake_chaos/aicert.yaml", "--format", "text"],
        capture_output=True,
        text=True,
        
        timeout=120,
    )
    
    # Should exit with code 2 (threshold failure)
    assert result.returncode == 2, f"Expected exit code 2, got {result.returncode}. stderr: {result.stderr}"
    
    # Verify output contains example failures with case_ids
    output = result.stdout
    
    # Check that the output mentions example failures or case_id
    assert "Example failures" in output or "case" in output.lower(), \
        f"Expected failure examples in output, got: {output[:500]}"
    
    # Verify the output shows the failed provider
    assert "fake-chaos" in output or "CI Results" in output, \
        f"Expected provider or CI Results in output, got: {output[:500]}"


def test_get_example_failures_helper():
    """Test the _get_example_failures helper function directly."""
    from aicert.cli import _get_example_failures
    
    # Test with various failure types
    results = [
        {
            "case_id": "case_1",
            "ok_json": True,
            "ok_schema": False,
            "error": "Extra keys not allowed: extra_field",
            "extra_keys": ["extra_field"],
            "content": "{}",
        },
        {
            "case_id": "case_2",
            "ok_json": False,
            "ok_schema": False,
            "error": "Invalid JSON",
            "content": "{invalid json",
        },
        {
            "case_id": "case_3",
            "ok_json": True,
            "ok_schema": True,
            "error": "Timeout after 30s",
            "content": "",
        },
    ]
    
    examples = _get_example_failures(results, max_examples=2)
    
    # Should return up to max_examples
    assert len(examples) <= 2, f"Expected at most 2 examples, got {len(examples)}"
    
    # Each example should have case_id and type
    for ex in examples:
        assert "case_id" in ex, f"Example missing case_id: {ex}"
        assert "type" in ex, f"Example missing type: {ex}"
        assert "detail" in ex, f"Example missing detail: {ex}"
    
    # Verify schema failure example
    schema_examples = [e for e in examples if e["type"] == "schema"]
    if schema_examples:
        assert any("extra" in e["detail"].lower() or "schema" in e["detail"].lower() for e in schema_examples), \
            "Schema failure should mention extra keys or schema"
    
    # Verify json_parse failure example
    json_examples = [e for e in examples if e["type"] == "json_parse"]
    if json_examples:
        assert len(json_examples[0]["detail"]) <= 203, \
            "JSON parse example should be truncated to ~200 chars"


def test_report_command_basic():
    """Test that report command prints basic information from summary.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = os.path.join(tmpdir, "run_abc123")
        os.makedirs(run_dir)
        
        # Create a summary.json file
        summary = {
            "project": "test-project",
            "per_provider": {
                "fake:test-model": {
                    "stability_score": 90.0,
                    "schema_compliance": 95.0,
                    "latency_stats": {"mean": 100.0, "p95": 150.0, "std": 25.0},
                    "total_runs": 10,
                    "total_cost_usd": 0.01,
                    "json_parse_failures": 1,
                    "schema_failures": 0,
                    "provider_errors": 0,
                    "timeouts": 0,
                }
            },
            "overall": {
                "total_runs": 10,
                "stability_score": 90.0,
                "schema_compliance": 95.0,
            }
        }
        
        with open(os.path.join(run_dir, "summary.json"), "w") as f:
            json.dump(summary, f)
        
        # Run report command
        result = subprocess.run(
            [sys.executable, "-m", "aicert", "report", run_dir],
            capture_output=True,
            text=True,
            
            timeout=30,
        )
        
        # Should exit with code 0
        assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
        
        # Verify output contains expected fields
        output = result.stdout
        assert "test-project" in output, "Output should contain project name"
        assert "run_abc123" in output, "Output should contain run ID"
        assert "fake:test-model" in output, "Output should contain provider ID"
        assert "90.0%" in output, "Output should contain stability score"
        assert "95.0%" in output, "Output should contain compliance score"
        assert "150ms" in output, "Output should contain P95 latency"
        assert "100ms" in output, "Output should contain mean latency"
        assert "$0.0010" in output, "Output should contain mean cost"
        assert "1" in output, "Output should contain JSON parse failure count"


def test_report_command_missing_summary():
    """Test that report command fails with code 3 when summary.json is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = os.path.join(tmpdir, "run_abc123")
        os.makedirs(run_dir)
        
        # Run report command without summary.json
        result = subprocess.run(
            [sys.executable, "-m", "aicert", "report", run_dir],
            capture_output=True,
            text=True,
            
            timeout=30,
        )
        
        # Should exit with code 3
        assert result.returncode == 3, f"Expected exit code 3, got {result.returncode}"
        assert "summary.json" in result.stdout, "Error should mention summary.json"


def test_report_command_json_format():
    """Test that report command with --format json outputs valid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = os.path.join(tmpdir, "run_abc123")
        os.makedirs(run_dir)
        
        # Create a summary.json file
        summary = {
            "project": "test-project",
            "per_provider": {
                "fake:test-model": {
                    "stability_score": 90.0,
                    "schema_compliance": 95.0,
                    "latency_stats": {"mean": 100.0, "p95": 150.0, "std": 25.0},
                    "total_runs": 10,
                    "total_cost_usd": 0.01,
                    "json_parse_failures": 1,
                    "schema_failures": 0,
                    "provider_errors": 0,
                    "timeouts": 0,
                }
            },
            "overall": {
                "total_runs": 10,
                "stability_score": 90.0,
                "schema_compliance": 95.0,
            }
        }
        
        with open(os.path.join(run_dir, "summary.json"), "w") as f:
            json.dump(summary, f)
        
        # Run report command with --format json
        result = subprocess.run(
            [sys.executable, "-m", "aicert", "report", run_dir, "--format", "json"],
            capture_output=True,
            text=True,
            
            timeout=30,
        )
        
        # Should exit with code 0
        assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
        
        # Parse stdout as JSON
        output = result.stdout.strip()
        assert output, "Expected JSON output but got empty stdout"
        
        parsed = json.loads(output)
        
        # Verify required fields from summary.json
        assert parsed["project"] == "test-project", "JSON output must contain 'project'"
        assert "per_provider" in parsed, "JSON output must contain 'per_provider'"
        assert "overall" in parsed, "JSON output must contain 'overall'"
        
        # Verify augmented fields (run_id and run_dir)
        assert "run_id" in parsed, "JSON output must contain 'run_id'"
        assert parsed["run_id"] == "run_abc123", f"run_id must be 'run_abc123', got {parsed['run_id']}"
        assert "run_dir" in parsed, "JSON output must contain 'run_dir'"
        assert parsed["run_dir"].endswith("run_abc123"), f"run_dir must end with run_id, got {parsed['run_dir']}"
        
        # Verify per_provider structure
        assert "fake:test-model" in parsed["per_provider"], "per_provider must contain 'fake:test-model'"
        metrics = parsed["per_provider"]["fake:test-model"]
        assert metrics["stability_score"] == 90.0, "stability_score must be 90.0"
        assert metrics["schema_compliance"] == 95.0, "schema_compliance must be 95.0"


def test_ci_junit_format():
    """Test that ci command with --format junit outputs valid JUnit XML."""
    import xml.etree.ElementTree as ET
    
    result = subprocess.run(
        [sys.executable, "-m", "aicert", "ci", "examples/fake_chaos/aicert.yaml", "--format", "junit"],
        capture_output=True,
        text=True,
        
        timeout=60,
    )
    
    # Should exit with code 0 (pass) or 2 (fail) but not error
    assert result.returncode in [0, 2], f"Expected exit code 0 or 2, got {result.returncode}. stderr: {result.stderr}"
    
    # Parse stdout as XML
    output = result.stdout.strip()
    assert output, "Expected XML output but got empty stdout"
    
    # Verify XML declaration
    assert output.startswith('<?xml version="1.0" encoding="UTF-8"?>'), "XML output must start with XML declaration"
    
    # Parse XML
    root = ET.fromstring(output)
    
    # Verify root is testsuite
    assert root.tag == "testsuite", f"Root must be testsuite, got {root.tag}"
    
    # Verify required attributes
    assert "name" in root.attrib, "testsuite must have name attribute"
    assert "tests" in root.attrib, "testsuite must have tests attribute"
    assert "failures" in root.attrib, "testsuite must have failures attribute"
    assert "timestamp" in root.attrib, "testsuite must have timestamp attribute"
    
    # Verify tests attribute is a positive integer
    assert int(root.attrib["tests"]) > 0, "tests must be > 0"
    
    # Verify failures attribute is a non-negative integer
    assert int(root.attrib["failures"]) >= 0, "failures must be >= 0"
    
    # Verify at least one testcase
    testcases = root.findall("testcase")
    assert len(testcases) > 0, "Must have at least one testcase"
    
    # Verify each testcase has required attributes
    for tc in testcases:
        assert "name" in tc.attrib, "testcase must have name attribute"
        assert "classname" in tc.attrib, "testcase must have classname attribute"
        
        # Verify testcase names are valid threshold tests
        valid_names = ["stability_threshold", "compliance_threshold", "cost_regression", "latency_regression"]
        assert tc.attrib["name"] in valid_names, f"Invalid testcase name: {tc.attrib['name']}"


def test_ci_junit_format_with_failures():
    """Test that ci command with --format junit correctly reports failures."""
    import xml.etree.ElementTree as ET
    
    result = subprocess.run(
        [sys.executable, "-m", "aicert", "ci", "examples/fake_chaos/aicert.yaml", "--format", "junit"],
        capture_output=True,
        text=True,
        
        timeout=60,
    )
    
    # Should exit with code 2 (fail) since fake-chaos has low compliance
    assert result.returncode == 2, f"Expected exit code 2, got {result.returncode}"
    
    # Parse XML
    root = ET.fromstring(result.stdout)
    
    # Find failures in testcases
    failures = root.findall(".//failure")
    
    # Should have at least one failure (compliance threshold should fail)
    assert len(failures) > 0, "Should have at least one failure in the JUnit output"
    
    # Verify each failure has a message
    for failure in failures:
        assert "message" in failure.attrib, "failure must have message attribute"
        assert failure.attrib["message"], "failure message must not be empty"
        assert failure.text, "failure element must have text content"


def test_escape_xml_helper():
    """Test the _escape_xml helper function."""
    from aicert.cli import _escape_xml
    
    # Test special characters
    assert _escape_xml("&") == "&amp;"
    assert _escape_xml("<") == "&lt;"
    assert _escape_xml(">") == "&gt;"
    assert _escape_xml('"') == "&quot;"
    assert _escape_xml("'") == "&apos;"
    
    # Test mixed content
    assert _escape_xml("a < b & c > d") == "a &lt; b &amp; c &gt; d"
    
    # Test normal text remains unchanged
    assert _escape_xml("normal text") == "normal text"


def test_report_command_with_run_id():
    """Test that report command accepts run_id and resolves to .aicert/runs/<run_id>/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create .aicert/runs/<run_id>/ directory structure
        run_id = "test-run-abc123"
        run_dir = os.path.join(tmpdir, ".aicert", "runs", run_id)
        os.makedirs(run_dir)
        
        # Create a summary.json file
        summary = {
            "project": "test-project",
            "per_provider": {
                "fake:test-model": {
                    "stability_score": 90.0,
                    "schema_compliance": 95.0,
                    "latency_stats": {"mean": 100.0, "p95": 150.0, "std": 25.0},
                    "total_runs": 10,
                    "total_cost_usd": 0.01,
                    "json_parse_failures": 1,
                    "schema_failures": 0,
                    "provider_errors": 0,
                    "timeouts": 0,
                }
            },
            "overall": {
                "total_runs": 10,
                "stability_score": 90.0,
                "schema_compliance": 95.0,
            }
        }
        
        with open(os.path.join(run_dir, "summary.json"), "w") as f:
            json.dump(summary, f)
        
        # Run report command with run_id (not full path)
        result = subprocess.run(
            [sys.executable, "-m", "aicert", "report", run_id],
            capture_output=True,
            text=True,
            cwd=tmpdir,  # Use tmpdir as cwd so it resolves .aicert/runs/<run_id>
            timeout=30,
        )
        
        # Should exit with code 0
        assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
        
        # Verify output contains expected fields
        output = result.stdout
        assert "test-project" in output, "Output should contain project name"
        assert run_id in output, "Output should contain run ID"
        assert "fake:test-model" in output, "Output should contain provider ID"
        assert "90.0%" in output, "Output should contain stability score"


def test_report_command_run_id_not_found():
    """Test that report command exits 3 with friendly error when run_id not found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Run report command with non-existent run_id
        run_id = "non-existent-run-xyz789"
        result = subprocess.run(
            [sys.executable, "-m", "aicert", "report", run_id],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=30,
        )
        
        # Should exit with code 3
        assert result.returncode == 3, f"Expected exit code 3, got {result.returncode}"
        
        # Verify error message mentions the run_id and is friendly
        assert run_id in result.stdout or run_id in result.stderr, "Error should mention the run_id"
        assert "not found" in result.stdout.lower() or "error" in result.stdout.lower(), \
            "Error should be friendly and mention the issue"


def test_report_command_run_id_with_report_txt():
    """Test that report command prints report.txt when using run_id resolution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create .aicert/runs/<run_id>/ directory structure with report.txt
        run_id = "test-run-report"
        run_dir = os.path.join(tmpdir, ".aicert", "runs", run_id)
        os.makedirs(run_dir)
        
        # Create report.txt
        report_content = "Custom report content for run"
        with open(os.path.join(run_dir, "report.txt"), "w") as f:
            f.write(report_content)
        
        # Run report command with run_id
        result = subprocess.run(
            [sys.executable, "-m", "aicert", "report", run_id],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=30,
        )
        
        # Should exit with code 0
        assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. stderr: {result.stderr}"
        
        # Verify report.txt content is printed
        assert report_content in result.stdout, "Output should contain report.txt content"
