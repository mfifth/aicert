"""Doctor command for validating aicert installation and configuration."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from rich.console import Console

from aicert.config import Config, ConfigLoadError, ProviderConfig, load_config
from aicert.templating import build_schema_hint, render_prompt
from aicert.validation import load_json_schema, validate_output

console = Console()


class DoctorCheck:
    """Represents a single doctor check with result."""
    
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error: Optional[str] = None
        self.details: List[str] = []
    
    def pass_check(self, details: Optional[List[str]] = None) -> None:
        """Mark check as passed."""
        self.passed = True
        if details:
            self.details = details
    
    def fail_check(self, error: str) -> None:
        """Mark check as failed."""
        self.passed = False
        self.error = error
    
    def add_detail(self, detail: str) -> None:
        """Add a detail message."""
        self.details.append(detail)


def load_cases(cases_file: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Load test cases from JSONL file.
    
    Returns:
        Tuple of (cases, errors)
    """
    cases = []
    errors = []
    
    with open(cases_file, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                case = json.loads(line)
                cases.append(case)
                # Check for required 'id' field
                if "id" not in case and "name" not in case:
                    errors.append(f"Line {line_num}: Missing 'id' or 'name' field")
            except json.JSONDecodeError as e:
                errors.append(f"Line {line_num}: Invalid JSON - {e}")
    
    return cases, errors


def check_provider_env(provider: ProviderConfig) -> Tuple[str, Optional[str]]:
    """Check provider environment readiness.
    
    Returns:
        Tuple of (status, message)
        Status: "OK" | "MISSING_ENV" | "MISCONFIG"
    """
    if provider.provider == "fake":
        return "OK", "No environment variables required for fake provider"
    
    if provider.provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return "MISSING_ENV", "OPENAI_API_KEY not set"
        return "OK", "OPENAI_API_KEY is set"
    
    if provider.provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return "MISSING_ENV", "ANTHROPIC_API_KEY not set"
        return "OK", "ANTHROPIC_API_KEY is set"
    
    if provider.provider == "openai_compatible":
        base_url = provider.base_url
        if not base_url:
            return "MISCONFIG", "base_url not configured"
        
        api_key_env = os.environ.get("OPENAI_COMPAT_API_KEY")
        if api_key_env:
            return "OK", f"base_url={base_url}, OPENAI_COMPAT_API_KEY is set"
        else:
            return "OK", f"base_url={base_url}, OPENAI_COMPAT_API_KEY not set (optional)"
    
    return "MISCONFIG", f"Unknown provider type: {provider.provider}"


async def check_connectivity(provider: ProviderConfig) -> Tuple[bool, str]:
    """Check connectivity to openai_compatible provider.
    
    Returns:
        Tuple of (success, message)
    """
    base_url = provider.base_url
    if not base_url:
        return False, "No base_url configured"
    
    # Try /models endpoint first, then fallback to base URL
    test_urls = [
        f"{base_url.rstrip('/')}/models",
        base_url.rstrip('/'),
    ]
    
    for url in test_urls:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url, follow_redirects=True)
                if response.status_code < 500:
                    return True, f"Connected to {url} (status {response.status_code})"
        except httpx.TimeoutException:
            continue
        except Exception as e:
            continue
    
    return False, f"Could not connect to {base_url} (tried {len(test_urls)} endpoints)"


def run_doctor(
    config_path: str,
    check_connectivity_flag: bool = False,
) -> Tuple[int, int]:
    """Run all doctor checks.
    
    Args:
        config_path: Path to configuration file.
        check_connectivity_flag: Whether to check connectivity for openai_compatible providers.
    
    Returns:
        Tuple of (exit_code, failed_checks_count)
    """
    checks: List[DoctorCheck] = []
    failed_count = 0
    
    # === A. Load Config ===
    check = DoctorCheck("Config")
    checks.append(check)
    try:
        config = load_config(config_path)
        check.pass_check([f"Config path: {config_path}", f"Project: {config.project}"])
    except ConfigLoadError:
        # Re-raise for CLI to handle exit code
        raise
    except Exception as e:
        check.fail_check(f"Failed to load config: {e}")
        failed_count += 1
        # Can't continue without config
        return 1, failed_count
    
    # === B. Validate Files ===
    config_dir = Path(config_path).parent
    
    # B1. Prompt file
    check = DoctorCheck("Files")
    checks.append(check)
    prompt_errors = []
    
    prompt_file = config_dir / config.prompt_file
    try:
        with open(prompt_file, "r") as f:
            prompt_content = f.read()
        check.add_detail(f"prompt_file: {config.prompt_file} (readable, {len(prompt_content)} chars)")
    except Exception as e:
        prompt_errors.append(f"prompt_file: {e}")
    
    # B2. Cases file
    cases_file = config_dir / config.cases_file
    cases: List[Dict[str, Any]] = []
    try:
        cases, case_errors = load_cases(str(cases_file))
        if case_errors:
            prompt_errors.extend(case_errors)
        else:
            check.add_detail(f"cases_file: {config.cases_file} ({len(cases)} cases)")
    except Exception as e:
        prompt_errors.append(f"cases_file: {e}")
    
    # B3. Schema file
    schema_file = config_dir / config.schema_file
    schema: Dict[str, Any] = {}
    try:
        schema = load_json_schema(str(schema_file))
        check.add_detail(f"schema_file: {config.schema_file} (valid JSON schema)")
    except Exception as e:
        prompt_errors.append(f"schema_file: {e}")
    
    if prompt_errors:
        check.fail_check("\n  ".join(prompt_errors))
        failed_count += 1
    else:
        check.pass_check()
    
    # === C. Template Render Validation ===
    check = DoctorCheck("Template")
    checks.append(check)
    template_errors = []
    
    if cases and schema:
        schema_hint = build_schema_hint(schema)
        # Test first 1-3 cases
        test_cases = cases[:3]
        for case in test_cases:
            case_id = case.get("id") or case.get("name", "unknown")
            prompt_template = case.get("prompt", "")
            variables = case.get("variables", {})
            try:
                rendered = render_prompt(prompt_template, variables, schema_hint, case_id)
                check.add_detail(f"Case '{case_id}': rendered successfully")
            except ValueError as e:
                template_errors.append(f"Case '{case_id}': {e}")
    
    if template_errors:
        check.fail_check("\n  ".join(template_errors))
        failed_count += 1
    else:
        if cases:
            check.pass_check([f"Rendered {min(3, len(cases))} case(s) successfully"])
        else:
            check.pass_check(["No cases to test"])
    
    # === D. Validation Pipeline Sanity ===
    check = DoctorCheck("Validation")
    checks.append(check)
    
    # Use FakeAdapter with deterministic output to test validation
    try:
        from aicert.runner import FakeAdapter
        import asyncio
        
        async def test_validation():
            adapter = FakeAdapter(latency_ms=1)
            result = await adapter.generate("Test prompt")
            content = result["choices"][0]["message"]["content"]
            return content
        
        sample_output = asyncio.run(test_validation())
        
        # Test validation with schema
        validation_result = validate_output(
            text=sample_output,
            schema=schema,
            extract_json=config.validation.extract_json,
            allow_extra_keys=config.validation.allow_extra_keys,
        )
        
        if validation_result.ok_json and validation_result.ok_schema:
            check.pass_check(["Validation pipeline working correctly"])
        elif validation_result.ok_json:
            check.fail_check(f"Schema validation failed: {validation_result.error}")
            failed_count += 1
        else:
            check.fail_check(f"JSON parsing failed: {validation_result.error}")
            failed_count += 1
    except Exception as e:
        check.fail_check(f"Validation pipeline error: {e}")
        failed_count += 1
    
    # === E. Provider Readiness ===
    check = DoctorCheck("Providers")
    checks.append(check)
    provider_status = []
    provider_issues = []
    
    for provider in config.providers:
        status, message = check_provider_env(provider)
        provider_status.append(f"{provider.id} ({provider.provider}): {status}")
        if status != "OK":
            provider_issues.append(f"{provider.id}: {message}")
    
    if provider_issues:
        check.fail_check("\n  ".join(provider_issues))
        failed_count += 1
    else:
        check.pass_check(provider_status)
    
    # === E2. Connectivity Check (optional) ===
    if check_connectivity_flag:
        check = DoctorCheck("Connectivity")
        checks.append(check)
        connectivity_results = []
        connectivity_issues = []
        
        for provider in config.providers:
            if provider.provider == "openai_compatible":
                success, message = asyncio.run(check_connectivity(provider))
                if success:
                    connectivity_results.append(f"{provider.id}: {message}")
                else:
                    connectivity_issues.append(f"{provider.id}: {message}")
        
        if connectivity_issues:
            # Don't fail doctor for connectivity issues, just warn
            connectivity_results.extend([f"[warn] {x}" for x in connectivity_issues])
            check.pass_check(connectivity_results)
        else:
            check.pass_check(connectivity_results if connectivity_results else ["No openai_compatible providers"])
    
    # === Print Summary ===
    console.print("\n[bold]Doctor Summary[/bold]")
    console.print("-" * 50)
    
    for check in checks:
        if check.passed:
            icon = "✅"
            console.print(f"  {icon} {check.name}")
            for detail in check.details:
                console.print(f"     {detail}")
        else:
            icon = "❌"
            console.print(f"  {icon} {check.name}")
            error = check.error or "Unknown error"
            for line in error.split("\n"):
                console.print(f"     {line}")
    
    console.print("-" * 50)
    
    # Final verdict
    total_failed = len([c for c in checks if not c.passed])
    if total_failed == 0:
        console.print("[bold green]Doctor: OK[/bold green]")
        return 0, 0
    else:
        console.print(f"[bold red]Doctor: Issues found ({total_failed})[/bold red]")
        return 1, total_failed


def print_dry_run_plan(config: Config, cases: List[Dict[str, Any]]) -> None:
    """Print the dry-run execution plan."""
    console.print("\n[bold]Dry Run Plan[/bold]")
    console.print("-" * 50)
    
    providers_count = len(config.providers)
    cases_count = len(cases)
    runs = config.runs
    total_requests = providers_count * cases_count * runs
    
    console.print(f"  Providers: {providers_count}")
    for p in config.providers:
        console.print(f"    - {p.id}: {p.provider}/{p.model}")
    console.print(f"  Cases: {cases_count}")
    console.print(f"  Runs per case: {runs}")
    console.print(f"  [bold]Total requests: {total_requests}[/bold]")
    console.print(f"  Concurrency: {config.concurrency}")
    console.print(f"  Timeout: {config.timeout_s}s")
    console.print(f"  Validation:")
    console.print(f"    - extract_json: {config.validation.extract_json}")
    console.print(f"    - allow_extra_keys: {config.validation.allow_extra_keys}")
    
    console.print("-" * 50)
