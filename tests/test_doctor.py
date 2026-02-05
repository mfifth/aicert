"""Tests for the doctor command."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml


def run_aicert_command(args: list[str], env: dict = None) -> tuple[int, str, str]:
    """Run aicert CLI command and return exit code, stdout, stderr.
    
    Uses `python -m aicert` to avoid PATH issues.
    """
    env = env or {}
    full_env = os.environ.copy()
    full_env.update(env)
    
    # Use `python -m aicert` to run the command
    result = subprocess.run(
        [sys.executable, "-m", "aicert"] + args,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
        env=full_env,
    )
    return result.returncode, result.stdout, result.stderr


def run_aicert_command_from_dir(args: list[str], cwd: str, env: dict = None) -> tuple[int, str, str]:
    """Run aicert CLI command from a specific directory.
    
    Uses `python -m aicert` to avoid PATH issues.
    """
    env = env or {}
    full_env = os.environ.copy()
    full_env.update(env)
    
    # Use `python -m aicert` to run the command from specified directory
    result = subprocess.run(
        [sys.executable, "-m", "aicert"] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=full_env,
    )
    return result.returncode, result.stdout, result.stderr


class TestDoctorCommand:
    """Tests for aicert doctor command."""
    
    def test_doctor_ok_with_fake_chaos_example(self):
        """Run doctor on examples/fake_chaos/aicert.yaml with FakeAdapter config.
        
        Should exit 0 even without provider keys because provider is fake.
        """
        exit_code, stdout, stderr = run_aicert_command(
            ["doctor", "examples/fake_chaos/aicert.yaml"]
        )
        
        assert exit_code == 0, f"Expected exit 0, got {exit_code}. stderr: {stderr}"
        assert "Doctor: OK" in stdout, f"Expected 'Doctor: OK' in output. Output: {stdout}"
        # Should have checked all sections
        assert "Config" in stdout
        assert "Files" in stdout
        assert "Template" in stdout
        assert "Validation" in stdout
        assert "Providers" in stdout
    
    def test_doctor_missing_env_openai(self):
        """Create a temp config with provider=openai; ensure OPENAI_API_KEY not set.
        
        Doctor should exit 1 and report missing env.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create mock referenced files
            (config_dir / "prompt.txt").write_text("Test prompt: {{ input }}")
            (config_dir / "cases.jsonl").write_text('{"id": "test1", "variables": {"input": "hello"}}')
            (config_dir / "schema.json").write_text('{"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}')
            
            # Create config with openai provider
            config_data = {
                "project": "test-project",
                "providers": [
                    {
                        "id": "openai-test",
                        "provider": "openai",
                        "model": "gpt-4",
                        "temperature": 0.0,
                    }
                ],
                "prompt_file": "prompt.txt",
                "cases_file": "cases.jsonl",
                "schema_file": "schema.json",
                "runs": 1,
                "concurrency": 1,
                "timeout_s": 10,
            }
            
            config_path = config_dir / "aicert.yaml"
            config_path.write_text(yaml.dump(config_data))
            
            # Ensure OPENAI_API_KEY is not set
            env = {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}
            
            exit_code, stdout, stderr = run_aicert_command(
                ["doctor", str(config_path)],
                env=env
            )
            
            assert exit_code == 1, f"Expected exit 1, got {exit_code}. Output: {stdout}"
            assert "MISSING_ENV" in stdout or "OPENAI_API_KEY" in stdout, \
                f"Expected missing env warning. Output: {stdout}"
    
    def test_doctor_openai_compatible_missing_base_url(self):
        """Create a temp config with provider=openai_compatible but no base_url.
        
        Doctor should exit 1 and report missing base_url configuration.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create mock referenced files
            (config_dir / "prompt.txt").write_text("Test prompt: {{ input }}")
            (config_dir / "cases.jsonl").write_text('{"id": "test1", "variables": {"input": "hello"}}')
            (config_dir / "schema.json").write_text('{"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}')
            
            # Create config with openai_compatible provider but no base_url
            config_data = {
                "project": "test-project",
                "providers": [
                    {
                        "id": "compat-test",
                        "provider": "openai_compatible",
                        "model": "custom-model",
                        "temperature": 0.0,
                        # Note: no base_url specified
                    }
                ],
                "prompt_file": "prompt.txt",
                "cases_file": "cases.jsonl",
                "schema_file": "schema.json",
                "runs": 1,
                "concurrency": 1,
                "timeout_s": 10,
            }
            
            config_path = config_dir / "aicert.yaml"
            config_path.write_text(yaml.dump(config_data))
            
            exit_code, stdout, stderr = run_aicert_command(["doctor", str(config_path)])
            
            assert exit_code == 1, f"Expected exit 1, got {exit_code}. Output: {stdout}"
            assert "MISCONFIG" in stdout or "base_url" in stdout.lower(), \
                f"Expected missing base_url warning. Output: {stdout}"
    
    def test_doctor_missing_prompt_file(self):
        """Test that doctor reports missing prompt file.
        
        When a referenced file is missing, load_config() exits with code 3
        before the doctor output is printed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create only cases and schema, but no prompt file
            (config_dir / "cases.jsonl").write_text('{"id": "test1", "variables": {"input": "hello"}}')
            (config_dir / "schema.json").write_text('{"type": "object"}')
            
            config_data = {
                "project": "test-project",
                "providers": [
                    {
                        "id": "fake-test",
                        "provider": "fake",
                        "model": "fake-model",
                        "temperature": 0.0,
                    }
                ],
                "prompt_file": "missing_prompt.txt",
                "cases_file": "cases.jsonl",
                "schema_file": "schema.json",
            }
            
            config_path = config_dir / "aicert.yaml"
            config_path.write_text(yaml.dump(config_data))
            
            # Run doctor from the temp directory so paths resolve correctly
            exit_code, stdout, stderr = run_aicert_command_from_dir(
                ["doctor", "aicert.yaml"],
                cwd=tmpdir
            )
            
            # Config validation exits with code 3 when files are missing
            assert exit_code == 3
            # Error message should mention the missing file
            assert "prompt_file" in stderr or "missing_prompt" in stderr or "not found" in stderr.lower()
    
    def test_doctor_invalid_jsonl(self):
        """Test that doctor reports invalid JSONL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create files
            (config_dir / "prompt.txt").write_text("Test: {{ input }}")
            (config_dir / "cases.jsonl").write_text('{"id": "test1"}\ninvalid json\n{"id": "test2"}')
            (config_dir / "schema.json").write_text('{"type": "object"}')
            
            config_data = {
                "project": "test-project",
                "providers": [
                    {
                        "id": "fake-test",
                        "provider": "fake",
                        "model": "fake-model",
                        "temperature": 0.0,
                    }
                ],
                "prompt_file": "prompt.txt",
                "cases_file": "cases.jsonl",
                "schema_file": "schema.json",
            }
            
            config_path = config_dir / "aicert.yaml"
            config_path.write_text(yaml.dump(config_data))
            
            exit_code, stdout, stderr = run_aicert_command(["doctor", str(config_path)])
            
            assert exit_code == 1
            assert "Files" in stdout or "Invalid JSON" in stdout or "JSON" in stdout


class TestDoctorConnectivity:
    """Tests for --check-connectivity flag."""
    
    def test_check_connectivity_flag_exists(self):
        """Test that --check-connectivity flag is recognized."""
        exit_code, stdout, stderr = run_aicert_command(
            ["doctor", "examples/fake_chaos/aicert.yaml", "--check-connectivity", "--help"]
        )
        
        # Should not error on --check-connectivity
        assert "unrecognized arguments" not in stderr, \
            f"--check-connectivity flag not recognized. stderr: {stderr}"
    
    def test_connectivity_check_not_required(self):
        """Test that connectivity check is optional and doesn't fail when not connected."""
        # This test just verifies the flag is accepted
        exit_code, stdout, stderr = run_aicert_command(
            ["doctor", "examples/fake_chaos/aicert.yaml", "--check-connectivity"]
        )
        
        # With fake provider, should still pass
        assert exit_code == 0 or "Connectivity" in stdout or "Provider" in stdout


class TestDoctorSections:
    """Tests for doctor command output sections."""
    
    def test_doctor_has_summary(self):
        """Test that doctor outputs a summary section."""
        exit_code, stdout, stderr = run_aicert_command(
            ["doctor", "examples/fake_chaos/aicert.yaml"]
        )
        
        assert "Summary" in stdout or "Doctor:" in stdout
    
    def test_doctor_checks_all_sections(self):
        """Test that doctor checks all expected sections."""
        exit_code, stdout, stderr = run_aicert_command(
            ["doctor", "examples/fake_chaos/aicert.yaml"]
        )
        
        # All sections should be checked
        assert "Config" in stdout
        assert "Files" in stdout
        assert "Template" in stdout
        assert "Validation" in stdout
        assert "Providers" in stdout


class TestStabilityDryRun:
    """Tests for aicert stability --dry-run option."""
    
    def test_stability_dry_run_exits_zero(self):
        """Test that stability --dry-run exits 0 on success."""
        exit_code, stdout, stderr = run_aicert_command(
            ["stability", "examples/fake_chaos/aicert.yaml", "--dry-run"]
        )
        
        assert exit_code == 0, f"Expected exit 0, got {exit_code}. stderr: {stderr}"
    
    def test_stability_dry_run_contains_total_requests(self):
        """Test that stability --dry-run output contains 'total_requests'."""
        exit_code, stdout, stderr = run_aicert_command(
            ["stability", "examples/fake_chaos/aicert.yaml", "--dry-run"]
        )
        
        assert "total_requests" in stdout.lower() or "Total requests" in stdout, \
            f"Expected 'total_requests' in output. Output: {stdout}"
    
    def test_stability_dry_run_no_artifacts_created(self):
        """Test that stability --dry-run does not create .aicert/runs directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy example files to temp directory
            src_dir = Path(__file__).parent.parent / "examples" / "fake_chaos"
            dst_dir = Path(tmpdir)
            
            for f in ["aicert.yaml", "prompt.txt", "cases.jsonl", "schema.json"]:
                shutil.copy2(src_dir / f, dst_dir / f)
            
            # Run stability --dry-run from temp directory
            exit_code, stdout, stderr = run_aicert_command_from_dir(
                ["stability", "aicert.yaml", "--dry-run"],
                cwd=tmpdir
            )
            
            assert exit_code == 0, f"Expected exit 0, got {exit_code}. stderr: {stderr}"
            
            # Check that no .aicert/runs directory was created
            runs_dir = dst_dir / ".aicert" / "runs"
            assert not runs_dir.exists(), \
                f".aicert/runs directory should not exist after dry-run, but found: {runs_dir}"
    
    def test_stability_dry_run_does_not_call_providers(self):
        """Test that stability --dry-run does not call any providers."""
        exit_code, stdout, stderr = run_aicert_command(
            ["stability", "examples/fake_chaos/aicert.yaml", "--dry-run"]
        )
        
        assert exit_code == 0, f"Expected exit 0, got {exit_code}. stderr: {stderr}"
        # Should have doctor validation output but not actual provider calls
        assert "Doctor Summary" not in stdout or "Dry Run Plan" in stdout, \
            f"Expected dry-run plan in output. Output: {stdout}"
        # Should not have any results or metrics that would be produced by actual runs
        assert "Stability Results" not in stdout, \
            f"Should not have stability results in dry-run mode. Output: {stdout}"


class TestDryRunNotInOtherCommands:
    """Tests to verify --dry-run is NOT available in run/compare commands."""
    
    def test_run_command_has_no_dry_run_option(self):
        """Test that 'run' command does not have --dry-run option."""
        exit_code, stdout, stderr = run_aicert_command(
            ["run", "--help"]
        )
        
        assert "--dry-run" not in stdout and "dry-run" not in stdout, \
            f"'run' command should not have --dry-run option. stdout: {stdout}"
    
    def test_compare_command_has_no_dry_run_option(self):
        """Test that 'compare' command does not have --dry-run option."""
        exit_code, stdout, stderr = run_aicert_command(
            ["compare", "--help"]
        )
        
        assert "--dry-run" not in stdout and "dry-run" not in stdout, \
            f"'compare' command should not have --dry-run option. stdout: {stdout}"
    
    def test_stability_command_has_dry_run_option(self):
        """Test that 'stability' command has --dry-run option."""
        exit_code, stdout, stderr = run_aicert_command(
            ["stability", "--help"]
        )
        
        assert "--dry-run" in stdout, \
            f"'stability' command should have --dry-run option. stdout: {stdout}"
