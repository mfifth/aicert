"""CLI interface for aicert."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.style import Style

app = typer.Typer(
    name="aicert",
    help="CI for LLM JSON outputs - Validate, test, and measure LLM outputs",
    add_completion=False,
)
console = Console()


def _load_config_and_schema(config_path: str):
    """Load configuration and schema, resolving paths relative to config file.
    
    Returns:
        Tuple of (config_obj, schema, prompt_hash, schema_hash)
    """
    from aicert.config import Config, ConfigLoadError, load_config
    from aicert.validation import load_json_schema, SchemaLoadError
    from aicert.hashing import sha256_file

    try:
        config_obj = load_config(config_path)
        config_obj._config_path = config_path
    except ConfigLoadError as e:
        console.print(e)
        sys.exit(3)

    # Resolve paths relative to config file
    config_dir = Path(config_path).parent
    schema_file = config_dir / config_obj.schema_file if not Path(config_obj.schema_file).is_absolute() else Path(config_obj.schema_file)
    prompt_file = config_dir / config_obj.prompt_file if not Path(config_obj.prompt_file).is_absolute() else Path(config_obj.prompt_file)
    
    try:
        schema = load_json_schema(str(schema_file))
    except SchemaLoadError as e:
        console.print(e)
        sys.exit(3)

    # Compute hashes
    prompt_hash = sha256_file(prompt_file)
    schema_hash = sha256_file(schema_file)

    return config_obj, schema, prompt_hash, schema_hash


def _should_store(no_store: bool, save_on_fail: bool, failed: bool) -> bool:
    """Determine if artifacts should be stored."""
    if no_store:
        return False
    if save_on_fail and failed:
        return True
    if not save_on_fail:
        return True  # Save on success too
    return False


def _print_stability_summary(summary: dict, title: str = "Stability Results"):
    """Print per-provider stability summary using rich tables."""
    console.print(f"\n[bold]{title}[/bold]")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Provider", style="cyan")
    table.add_column("Runs", justify="right")
    table.add_column("Stability", justify="right")
    table.add_column("Compliance", justify="right")
    table.add_column("JSON Parse Fail", justify="right")
    table.add_column("Schema Fail", justify="right")
    table.add_column("Provider Err", justify="right")
    table.add_column("Timeouts", justify="right")
    table.add_column("Latency P95", justify="right")
    table.add_column("Cost ($)", justify="right")
    
    for provider_id, metrics in summary["per_provider"].items():
        stability = f"{metrics['stability_score']:.1f}%"
        compliance = f"{metrics['schema_compliance']:.1f}%"
        latency_p95 = f"{metrics['latency_stats']['p95']:.0f}ms"
        cost = f"${metrics['total_cost_usd']:.4f}"
        
        # Error counts
        json_parse_fail = metrics.get("json_parse_failures", 0)
        schema_fail = metrics.get("schema_failures", 0)
        provider_err = metrics.get("provider_errors", 0)
        timeouts = metrics.get("timeouts", 0)
        
        # Color code stability
        if metrics['stability_score'] >= 85:
            stability_text = Text(stability, style="green")
        elif metrics['stability_score'] >= 70:
            stability_text = Text(stability, style="yellow")
        else:
            stability_text = Text(stability, style="red")
        
        # Color code error counts
        json_fail_text = Text(str(json_parse_fail), style="red" if json_parse_fail > 0 else "dim")
        schema_fail_text = Text(str(schema_fail), style="red" if schema_fail > 0 else "dim")
        provider_err_text = Text(str(provider_err), style="red" if provider_err > 0 else "dim")
        timeout_text = Text(str(timeouts), style="red" if timeouts > 0 else "dim")
        
        table.add_row(
            provider_id, 
            str(metrics["total_runs"]), 
            stability_text, 
            compliance,
            json_fail_text,
            schema_fail_text,
            provider_err_text,
            timeout_text,
            latency_p95, 
            cost
        )
    
    console.print(table)
    
    # Overall summary
    overall = summary["overall"]
    console.print(f"\n[bold]Overall:[/bold] {overall['total_runs']} runs, "
                 f"Stability: {overall['stability_score']:.1f}%, "
                 f"Compliance: {overall['schema_compliance']:.1f}%, "
                 f"JSON Parse Fail: {overall.get('json_parse_failures', 0)}, "
                 f"Schema Fail: {overall.get('schema_failures', 0)}, "
                 f"Provider Err: {overall.get('provider_errors', 0)}, "
                 f"Timeouts: {overall.get('timeouts', 0)}, "
                 f"Cost: ${overall['total_cost_usd']:.4f}")


def _print_ranked_table(summary: dict) -> None:
    """Print ranked comparison table."""
    console.print("\n[bold]Provider Comparison (Ranked by Stability > Compliance > Cost)[/bold]")
    
    # Sort providers by stability, then compliance, then cost
    providers = []
    for provider_id, metrics in summary["per_provider"].items():
        providers.append({
            "id": provider_id,
            "stability": metrics["stability_score"],
            "compliance": metrics["schema_compliance"],
            "cost": metrics["total_cost_usd"],
            "runs": metrics["total_runs"],
            "latency_p95": metrics["latency_stats"]["p95"],
        })
    
    # Sort: higher stability is better, higher compliance is better, lower cost is better
    providers.sort(key=lambda x: (x["stability"], x["compliance"], -x["cost"]), reverse=True)
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Rank", justify="center", style="bold")
    table.add_column("Provider", style="cyan")
    table.add_column("Stability", justify="right")
    table.add_column("Compliance", justify="right")
    table.add_column("Cost ($)", justify="right")
    table.add_column("Latency P95", justify="right")
    
    for rank, p in enumerate(providers, 1):
        stability_text = Text(f"{p['stability']:.1f}%", style="green" if p['stability'] >= 85 else "yellow" if p['stability'] >= 70 else "red")
        compliance_text = Text(f"{p['compliance']:.1f}%", style="green" if p['compliance'] >= 95 else "yellow")
        
        rank_str = Text(str(rank), style="bold cyan" if rank == 1 else "dim")
        table.add_row(rank_str, p["id"], stability_text, compliance_text, f"${p['cost']:.4f}", f"{p['latency_p95']:.0f}ms")
    
    console.print(table)


def _evaluate_thresholds(summary: dict, thresholds: dict) -> tuple[bool, list[str]]:
    """Evaluate thresholds and return (passed, failures)."""
    failures = []
    
    overall = summary["overall"]
    
    # Check min_stability
    if thresholds.get("min_stability") is not None:
        if overall["stability_score"] < thresholds["min_stability"]:
            failures.append(f"Stability {overall['stability_score']:.1f}% < {thresholds['min_stability']}% threshold")
    
    # Check min_compliance
    if thresholds.get("min_compliance") is not None:
        if overall["schema_compliance"] < thresholds["min_compliance"]:
            failures.append(f"Compliance {overall['schema_compliance']:.1f}% < {thresholds['min_compliance']}% threshold")
    
    # Check max_cost_usd
    if thresholds.get("max_cost_usd") is not None:
        if overall["total_cost_usd"] > thresholds["max_cost_usd"]:
            failures.append(f"Cost ${overall['total_cost_usd']:.4f} > ${thresholds['max_cost_usd']:.2f} threshold")
    
    # Check p95_latency_ms
    if thresholds.get("p95_latency_ms") is not None:
        p95 = overall["latency_stats"]["p95"]
        if p95 > thresholds["p95_latency_ms"]:
            failures.append(f"P95 latency {p95:.0f}ms > {thresholds['p95_latency_ms']}ms threshold")
    
    return len(failures) == 0, failures


def _get_failed_thresholds(summary: dict, thresholds: dict) -> list[str]:
    """Get list of threshold names that failed."""
    failed = []
    overall = summary["overall"]
    
    if thresholds.get("min_stability") is not None and overall["stability_score"] < thresholds["min_stability"]:
        failed.append("min_stability")
    if thresholds.get("min_compliance") is not None and overall["schema_compliance"] < thresholds["min_compliance"]:
        failed.append("min_compliance")
    if thresholds.get("max_cost_usd") is not None and overall["total_cost_usd"] > thresholds["max_cost_usd"]:
        failed.append("max_cost_usd")
    if thresholds.get("p95_latency_ms") is not None:
        p95 = overall["latency_stats"]["p95"]
        if p95 > thresholds["p95_latency_ms"]:
            failed.append("p95_latency_ms")
    
    return failed


def _get_example_failures(results: list[dict], max_examples: int = 3) -> list[dict]:
    """Extract example failures from results for actionable debugging output.
    
    Args:
        results: List of result dictionaries from execute_case.
        max_examples: Maximum number of examples to return.
    
    Returns:
        List of up to max_examples failure details with case_id and error info.
    """
    examples = []
    
    for result in results:
        if not result.get("ok_schema", True):
            case_id = result.get("case_id", "unknown")
            
            # Determine failure type and details
            if result.get("error"):
                error = result["error"]
                # Schema validation failure
                if "Extra keys" in error:
                    extra_keys = result.get("extra_keys", [])
                    examples.append({
                        "case_id": case_id,
                        "type": "schema",
                        "detail": f"extra keys: {', '.join(extra_keys)}" if extra_keys else error,
                    })
                elif "missing required field" in error.lower() or "was of type" in error.lower():
                    examples.append({
                        "case_id": case_id,
                        "type": "schema",
                        "detail": error,
                    })
                else:
                    examples.append({
                        "case_id": case_id,
                        "type": "schema",
                        "detail": error,
                    })
            elif not result.get("ok_json", True):
                # JSON parse failure
                content = result.get("content", "")
                truncated = content[:200] + "..." if len(content) > 200 else content
                examples.append({
                    "case_id": case_id,
                    "type": "json_parse",
                    "detail": truncated,
                })
            else:
                # Provider error or timeout
                error = result.get("error", "unknown error")
                examples.append({
                    "case_id": case_id,
                    "type": "provider_error",
                    "detail": error,
                })
            
            if len(examples) >= max_examples:
                break
    
    return examples


def _escape_xml(text: str) -> str:
    """Escape special XML characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&apos;")


def _build_junit_output(
    project: str,
    providers: list[str],
    thresholds: dict,
    passed: bool,
    summary: dict,
) -> str:
    """Build JUnit XML output for CI mode.
    
    One <testsuite> per provider with tests for:
    - stability threshold
    - compliance threshold
    - cost regression (if applicable)
    - latency regression (if applicable)
    """
    import datetime
    
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    
    xml_parts = []
    
    for provider_id in providers:
        metrics = summary["per_provider"].get(provider_id, {})
        
        # Count tests and failures for this provider
        tests = 0
        failures = 0
        test_cases = []
        
        # Stability threshold test
        tests += 1
        stability_score = metrics.get("stability_score", 0)
        min_stability = thresholds.get("min_stability")
        if min_stability is not None:
            if stability_score < min_stability:
                failures += 1
                message = f"Stability {stability_score:.1f}% < {min_stability}% threshold"
                test_cases.append(
                    f'<testcase name="stability_threshold" classname="{_escape_xml(provider_id)}"><failure message="{_escape_xml(message)}">{_escape_xml(message)}</failure></testcase>'
                )
            else:
                test_cases.append(
                    f'<testcase name="stability_threshold" classname="{_escape_xml(provider_id)}"/>'
                )
        else:
            test_cases.append(
                f'<testcase name="stability_threshold" classname="{_escape_xml(provider_id)}"/>'
            )
        
        # Compliance threshold test
        tests += 1
        compliance_score = metrics.get("schema_compliance", 0)
        min_compliance = thresholds.get("min_compliance")
        if min_compliance is not None:
            if compliance_score < min_compliance:
                failures += 1
                message = f"Compliance {compliance_score:.1f}% < {min_compliance}% threshold"
                test_cases.append(
                    f'<testcase name="compliance_threshold" classname="{_escape_xml(provider_id)}"><failure message="{_escape_xml(message)}">{_escape_xml(message)}</failure></testcase>'
                )
            else:
                test_cases.append(
                    f'<testcase name="compliance_threshold" classname="{_escape_xml(provider_id)}"/>'
                )
        else:
            test_cases.append(
                f'<testcase name="compliance_threshold" classname="{_escape_xml(provider_id)}"/>'
            )
        
        # Cost regression test (if max_cost_usd threshold is set)
        max_cost = thresholds.get("max_cost_usd")
        if max_cost is not None:
            tests += 1
            cost_usd = metrics.get("total_cost_usd", 0)
            if cost_usd > max_cost:
                failures += 1
                message = f"Cost ${cost_usd:.4f} > ${max_cost:.2f} threshold"
                test_cases.append(
                    f'<testcase name="cost_regression" classname="{_escape_xml(provider_id)}"><failure message="{_escape_xml(message)}">{_escape_xml(message)}</failure></testcase>'
                )
            else:
                test_cases.append(
                    f'<testcase name="cost_regression" classname="{_escape_xml(provider_id)}"/>'
                )
        
        # Latency regression test (if p95_latency_ms threshold is set)
        p95_latency = thresholds.get("p95_latency_ms")
        if p95_latency is not None:
            tests += 1
            latency_p95 = metrics.get("latency_stats", {}).get("p95", 0)
            if latency_p95 > p95_latency:
                failures += 1
                message = f"P95 latency {latency_p95:.0f}ms > {p95_latency}ms threshold"
                test_cases.append(
                    f'<testcase name="latency_regression" classname="{_escape_xml(provider_id)}"><failure message="{_escape_xml(message)}">{_escape_xml(message)}</failure></testcase>'
                )
            else:
                test_cases.append(
                    f'<testcase name="latency_regression" classname="{_escape_xml(provider_id)}"/>'
                )
        
        # Build testsuite element for this provider
        xml_parts.append(
            f'<testsuite name="{_escape_xml(provider_id)}" tests="{tests}" failures="{failures}" timestamp="{timestamp}">\n' +
            "\n".join(test_cases) + 
            f'\n</testsuite>'
        )
    
    # Return complete JUnit XML
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(xml_parts)


def _print_example_failures(examples: list[dict]) -> None:
    """Print example failures in a concise format.
    
    Args:
        examples: List of failure examples from _get_example_failures.
    """
    if not examples:
        return
    
    console.print("\n[bold]Example failures:[/bold]")
    
    for ex in examples:
        case_id = ex["case_id"]
        failure_type = ex["type"]
        detail = ex["detail"]
        
        if failure_type == "schema":
            console.print(f"  • {case_id}: schema validation - {detail}")
        elif failure_type == "json_parse":
            console.print(f"  • {case_id}: invalid JSON - \"{detail}\"")
        elif failure_type == "provider_error":
            console.print(f"  • {case_id}: provider error - {detail}")


def _build_json_output(
    project: str,
    run_id: Optional[str],
    providers: list[str],
    thresholds: dict,
    passed: bool,
    summary: dict,
) -> dict:
    """Build JSON output for CI mode."""
    per_provider = {}
    for provider_id, metrics in summary["per_provider"].items():
        per_provider[provider_id] = {
            "stability": round(metrics["stability_score"], 2),
            "compliance": round(metrics["schema_compliance"], 2),
            "latency_stats": {
                "mean_ms": round(metrics["latency_stats"]["mean"], 2),
                "p95_ms": round(metrics["latency_stats"]["p95"], 2),
                "std_ms": round(metrics["latency_stats"]["std"], 2),
            },
            "error_counts": {
                "json_parse_failures": metrics.get("json_parse_failures", 0),
                "schema_failures": metrics.get("schema_failures", 0),
                "provider_errors": metrics.get("provider_errors", 0),
                "timeouts": metrics.get("timeouts", 0),
            },
            "total_runs": metrics["total_runs"],
            "total_cost_usd": round(metrics["total_cost_usd"], 6),
        }
    
    result = {
        "project": project,
        "providers": providers,
        "thresholds": thresholds,
        "pass": passed,
        "per_provider": per_provider,
    }
    
    if run_id is not None:
        result["run_id"] = run_id
    
    return result


def _print_ci_summary(summary: dict, thresholds: dict, passed: bool, failures: list[str], run_dir: Optional[Path] = None, results: Optional[list[dict]] = None) -> None:
    """Print CI-friendly summary output.
    
    On pass: prints concise per-provider line with stability, compliance, p95 latency, cost, and PASS.
    On fail: prints failed thresholds, per-provider summary with FAIL, example failures, and artifacts path.
    
    Args:
        summary: Summary dictionary with per_provider metrics.
        thresholds: Thresholds dictionary.
        passed: Whether all thresholds passed.
        failures: List of threshold failure descriptions.
        run_dir: Optional run directory path.
        results: Optional list of result dictionaries for printing example failures.
    """
    if passed:
        console.print("\n[bold]CI Results[/bold]")
        for provider_id, metrics in summary["per_provider"].items():
            stability = f"{metrics['stability_score']:.1f}%"
            compliance = f"{metrics['schema_compliance']:.1f}%"
            latency_p95 = f"{metrics['latency_stats']['p95']:.0f}ms"
            cost = f"${metrics['total_cost_usd']:.4f}" if metrics['total_cost_usd'] > 0 else "$0.0000"
            console.print(f"{provider_id}: stability={stability} compliance={compliance} p95_latency={latency_p95} cost={cost} PASS")
    else:
        failed_thresholds = _get_failed_thresholds(summary, thresholds)
        console.print("\n[bold red]CI Results[/bold red]")
        console.print(f"Failed thresholds: {', '.join(failed_thresholds)}")
        console.print("\n[bold]Per-provider summary:[/bold]")
        for provider_id, metrics in summary["per_provider"].items():
            stability = f"{metrics['stability_score']:.1f}%"
            compliance = f"{metrics['schema_compliance']:.1f}%"
            latency_p95 = f"{metrics['latency_stats']['p95']:.0f}ms"
            cost = f"${metrics['total_cost_usd']:.4f}" if metrics['total_cost_usd'] > 0 else "$0.0000"
            console.print(f"{provider_id}: stability={stability} compliance={compliance} p95_latency={latency_p95} cost={cost} FAIL")
        
        # Print example failures if results are provided
        if results:
            examples = _get_example_failures(results)
            if examples:
                _print_example_failures(examples)
        
        if run_dir:
            console.print(f"\nArtifacts saved to: {run_dir}")


@app.command()
def doctor(
    config: str = typer.Argument(..., help="Path to configuration file"),
    check_connectivity: bool = typer.Option(
        False, "--check-connectivity", help="Check connectivity for openai_compatible providers"
    ),
) -> None:
    """Validate installation, configuration, and provider readiness.
    
    Performs comprehensive checks without making paid API calls.
    Exit code 0 if all checks pass, 1 otherwise.
    """
    from aicert.config import ConfigLoadError
    from aicert.doctor import run_doctor
    
    console.print("[bold]aicert doctor[/bold] - Validating installation and configuration")
    
    try:
        exit_code, failed_count = run_doctor(config, check_connectivity_flag=check_connectivity)
    except ConfigLoadError as e:
        # Print error to stderr and exit with code 3
        from rich.console import Console
        stderr_console = Console(file=sys.stderr)
        stderr_console.print(e)
        sys.exit(3)
    
    sys.exit(exit_code)


@app.command()
def init(
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing files"
    ),
) -> None:
    """Initialize a new aicert project scaffold in the current directory.
    
    Creates aicert.yaml, prompt.txt, cases.jsonl, schema.json, and aicert_baselines/ directory.
    Does not overwrite existing files unless --force is passed.
    """
    import os
    
    console.print("[bold]aicert init[/bold] - Initializing new project scaffold")
    
    # Get current directory name for project name
    cwd = Path.cwd()
    project_name = cwd.name or "my-project"
    
    # Files to create
    files_to_create = {
        "aicert.yaml": f'''# aicert configuration file
# Project: {project_name}
#
# To use with real providers (OpenAI, Anthropic), change the provider below
# and set your API key: export OPENAI_API_KEY="your-key"

project: {project_name}

# Fake adapter for testing - produces deterministic JSON output
# For real testing, change to: provider: openai, model: gpt-4
providers:
  - id: fake-test
    provider: fake
    model: fake-model
    temperature: 0.1

prompt_file: prompt.txt
cases_file: cases.jsonl
schema_file: schema.json

runs: 10
concurrency: 5
timeout_s: 30

validation:
  extract_json: true
  allow_extra_keys: false

thresholds:
  min_stability: 85
  min_compliance: 95

ci:
  runs: 10
  save_on_fail: true
''',
        "prompt.txt": '''# Prompt for LLM
# Output JSON only, matching the schema

User's request: $request
''',
        "cases.jsonl": '''{"name": "case_1", "request": "Classify the sentiment of this text: I love aicert!", "variables": {"request": "Classify the sentiment of this text: I love aicert!"}}
{"name": "case_2", "request": "Classify the sentiment of this text: aicert is okay.", "variables": {"request": "Classify the sentiment of this text: aicert is okay."}}
{"name": "case_3", "request": "Classify the sentiment of this text: I hate bugs.", "variables": {"request": "Classify the sentiment of this text: I hate bugs."}}
''',
        "schema.json": '''{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "label": {
      "type": "string",
      "description": "The classification label"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "Confidence score between 0 and 1"
    }
  },
  "required": ["label", "confidence"],
  "additionalProperties": false
}
''',
    }
    
    # Track what was created/skipped
    created = []
    skipped = []
    
    for filename, content in files_to_create.items():
        file_path = cwd / filename
        
        if file_path.exists():
            if force:
                file_path.write_text(content)
                created.append(filename)
                console.print(f"  [yellow]Overwrote:[/yellow] {filename}")
            else:
                skipped.append(filename)
                console.print(f"  [dim]Skipped (exists):[/dim] {filename}")
        else:
            file_path.write_text(content)
            created.append(filename)
            console.print(f"  [green]Created:[/green] {filename}")
    
    # Create aicert_baselines/ directory
    baselines_dir = cwd / "aicert_baselines"
    if baselines_dir.exists():
        if force:
            console.print(f"  [yellow]Kept (exists):[/yellow] aicert_baselines/")
        else:
            console.print(f"  [dim]Skipped (exists):[/dim] aicert_baselines/")
    else:
        baselines_dir.mkdir(exist_ok=True)
        created.append("aicert_baselines/")
        console.print(f"  [green]Created:[/green] aicert_baselines/")
    
    # Summary
    console.print(f"\n[bold]Summary:[/bold] {len(created)} created, {len(skipped)} skipped")
    
    if created:
        console.print(f"Project '{project_name}' is ready. Run 'aicert stability' to test!")


@app.command()
def run(
    config: str = typer.Argument(default="aicert.yaml", help="Path to configuration file"),
    output: Optional[str] = typer.Option(None, "-o", "--out", help="Output directory for artifacts"),
    no_store: bool = typer.Option(False, "--no-store", help="Don't save artifacts"),
    provider: Optional[str] = typer.Option(None, "-p", "--provider", help="Override provider (e.g., 'fake' for testing)"),
    extract_json: Optional[bool] = typer.Option(None, "--extract-json/--no-extract-json", help="Override extract_json setting"),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", help="Override number of concurrent requests"),
) -> None:
    """Run test cases once per case per provider (runs=1 override).
    
    Exits with code 1 if any ok_schema is false.
    """
    from aicert.config import Config, ProviderConfig, ConfigLoadError, load_config
    from aicert.metrics import compute_summary
    from aicert.runner import run_suite
    
    console.print("[bold]aicert run[/bold] - Running test cases (1 run per case)")
    
    try:
        config_obj, schema, prompt_hash, schema_hash = _load_config_and_schema(config)
    except SystemExit:
        raise
    
    # Override runs=1 for run command
    original_runs = config_obj.runs
    config_obj.runs = 1
    
    # Override extract_json if specified
    if extract_json is not None:
        config_obj.validation.extract_json = extract_json
    
    # Override concurrency if specified
    if concurrency is not None:
        config_obj.concurrency = concurrency
    
    # Override provider if specified
    if provider:
        typer.echo(f"Using provider override: {provider}")
        config_obj.providers = [
            ProviderConfig(
                id=provider,
                provider="fake",
                model=f"fake-{provider}",
                temperature=0.1,
            )
        ]
    
    try:
        # Determine output directory
        output_dir = output
        save_on_fail = True  # Always save on fail for run command
        
        # Run the suite
        typer.echo(f"Running with {len(config_obj.providers)} provider(s), 1 run per case")
        results = asyncio.run(run_suite(config_obj, output_dir=output_dir))
        
        # Compute summary
        summary = compute_summary(results, schema, prompt_hash=prompt_hash, schema_hash=schema_hash)
        
        # Check for any schema failures
        schema_failures = [r for r in results if not r.get("ok_schema", False)]
        
        # Print brief summary
        console.print(f"\n[bold]Results:[/bold] {summary['overall']['total_runs']} runs")
        for provider_id, metrics in summary["per_provider"].items():
            failures = sum(1 for r in results if r.get("provider_id") == provider_id and not r.get("ok_schema", False))
            status = "✓" if failures == 0 else "✗"
            console.print(f"  {status} {provider_id}: {metrics['schema_compliance']:.0f}% compliance ({failures} failures)")
        
        # Print artifact path if any failures
        if schema_failures:
            console.print(f"\n[bold red]Schema failures: {len(schema_failures)}[/bold red]")
            for r in schema_failures[:5]:  # Show first 5
                console.print(f"  - {r.get('provider_id')} / {r.get('case_id')}: {r.get('error', 'schema validation failed')}")
            if len(schema_failures) > 5:
                console.print(f"  ... and {len(schema_failures) - 5} more")
            
            # Find run directory
            from aicert.artifacts import create_run_dir
            run_dir = create_run_dir(output_dir)
            console.print(f"\n[bold]Artifacts saved to:[/bold] {run_dir}")
            sys.exit(1)
        else:
            console.print("\n[bold green]All schema validations passed[/bold green]")
            sys.exit(0)
            
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        sys.exit(1)
    finally:
        # Restore original runs
        config_obj.runs = original_runs


@app.command()
def stability(
    config: str = typer.Argument(default="aicert.yaml", help="Path to configuration file"),
    output: Optional[str] = typer.Option(None, "-o", "--out", help="Output directory for artifacts"),
    no_store: bool = typer.Option(False, "--no-store", help="Don't save artifacts"),
    provider: Optional[str] = typer.Option(None, "-p", "--provider", help="Override provider (e.g., 'fake' for testing)"),
    extract_json: Optional[bool] = typer.Option(None, "--extract-json/--no-extract-json", help="Override extract_json setting"),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", help="Override number of concurrent requests"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate config and print execution plan without running"),
    format: str = typer.Option("text", "--format", help="Output format: text or json", case_sensitive=False),
) -> None:
    """Run stability tests with config.runs per case.
    
    Prints per-provider stability summary.
    """
    from aicert.config import ProviderConfig, ConfigLoadError, load_config
    from aicert.metrics import compute_summary
    from aicert.runner import run_suite
    from aicert.doctor import run_doctor, load_cases, print_dry_run_plan
    
    # Only print header for text mode
    if format == "text":
        console.print("[bold]aicert stability[/bold] - Running stability tests")
    
    # Dry-run mode
    if dry_run:
        # Suppress doctor output when format is json
        import io
        import contextlib
        
        if format == "json":
            # Capture and discard doctor output
            with contextlib.redirect_stdout(io.StringIO()) as f:
                exit_code, _ = run_doctor(config, check_connectivity_flag=False)
        else:
            exit_code, _ = run_doctor(config, check_connectivity_flag=False)
        
        if exit_code != 0:
            if format == "json":
                typer.echo(json.dumps({"error": "Doctor checks failed", "success": False}))
            sys.exit(1)
        
        # Load config and print plan
        try:
            config_obj = load_config(config)
        except ConfigLoadError as e:
            if format == "json":
                typer.echo(json.dumps({"error": str(e), "success": False}))
            else:
                console.print(e)
            sys.exit(3)
        
        config_dir = Path(config).parent
        cases_file = config_dir / config_obj.cases_file
        cases, case_errors = load_cases(str(cases_file))
        if case_errors:
            error_msg = "Failed to load cases: " + ", ".join(case_errors)
            if format == "json":
                typer.echo(json.dumps({"error": error_msg, "success": False}))
            else:
                console.print("[bold red]Error:[/bold red] Failed to load cases")
                for err in case_errors:
                    console.print(f"  - {err}")
            sys.exit(1)
        
        # Calculate total requests
        providers_count = len(config_obj.providers)
        cases_count = len(cases)
        runs = config_obj.runs
        total_requests = providers_count * cases_count * runs
        
        if format == "json":
            # Output JSON execution plan
            providers_list = [{"id": p.id, "provider": p.provider, "model": p.model} for p in config_obj.providers]
            plan = {
                "project": config_obj.project,
                "providers": providers_list,
                "cases_count": cases_count,
                "runs_per_case": runs,
                "total_requests": total_requests,
                "concurrency": config_obj.concurrency,
                "timeout_s": config_obj.timeout_s,
                "validation": {
                    "extract_json": config_obj.validation.extract_json,
                    "allow_extra_keys": config_obj.validation.allow_extra_keys,
                },
            }
            typer.echo(json.dumps(plan, separators=(',', ':')))
        else:
            print_dry_run_plan(config_obj, cases)
            console.print("[bold green]Dry run complete - no requests made[/bold green]")
        sys.exit(0)
    
    try:
        config_obj, schema, prompt_hash, schema_hash = _load_config_and_schema(config)
    except SystemExit:
        raise
    
    # Override extract_json if specified
    if extract_json is not None:
        config_obj.validation.extract_json = extract_json
    
    # Override concurrency if specified
    if concurrency is not None:
        config_obj.concurrency = concurrency
    
    # Override provider if specified
    if provider:
        typer.echo(f"Using provider override: {provider}")
        config_obj.providers = [
            ProviderConfig(
                id=provider,
                provider="fake",
                model=f"fake-{provider}",
                temperature=0.1,
            )
        ]
    
    try:
        if format == "text":
            typer.echo(f"Running {config_obj.runs} runs per case with {len(config_obj.providers)} provider(s)")
        results = asyncio.run(run_suite(config_obj, output_dir=output))
        
        summary = compute_summary(results, schema, prompt_hash=prompt_hash, schema_hash=schema_hash)
        
        if format == "json":
            # Output JSON summary
            providers_list = [p.id for p in config_obj.providers]
            json_output = _build_json_output(
                project=config_obj.project,
                run_id=None,
                providers=providers_list,
                thresholds={},
                passed=True,  # Stability doesn't have pass/fail threshold
                summary=summary,
            )
            typer.echo(json.dumps(json_output, separators=(',', ':')))
        else:
            _print_stability_summary(summary, "Stability Results")
        
    except Exception as e:
        if format == "json":
            # In JSON mode, output error as JSON to stderr
            from rich.console import Console
            stderr_console = Console(file=sys.stderr)
            error_json = json.dumps({"error": str(e), "pass": False})
            stderr_console.print(error_json)
        else:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
        sys.exit(1)


@app.command()
def compare(
    config: str = typer.Argument(default="aicert.yaml", help="Path to configuration file"),
    output: Optional[str] = typer.Option(None, "-o", "--out", help="Output directory for artifacts"),
    no_store: bool = typer.Option(False, "--no-store", help="Don't save artifacts"),
    provider: Optional[str] = typer.Option(None, "-p", "--provider", help="Override provider (e.g., 'fake' for testing)"),
    extract_json: Optional[bool] = typer.Option(None, "--extract-json/--no-extract-json", help="Override extract_json setting"),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", help="Override number of concurrent requests"),
) -> None:
    """Compare providers with ranked table by stability, compliance, and cost.
    
    Like stability but prints ranked comparison table.
    """
    from aicert.config import ProviderConfig, ConfigLoadError, load_config
    from aicert.metrics import compute_summary
    from aicert.runner import run_suite
    
    console.print("[bold]aicert compare[/bold] - Comparing providers")
    
    try:
        config_obj, schema, prompt_hash, schema_hash = _load_config_and_schema(config)
    except SystemExit:
        raise
    
    # Override extract_json if specified
    if extract_json is not None:
        config_obj.validation.extract_json = extract_json
    
    # Override concurrency if specified
    if concurrency is not None:
        config_obj.concurrency = concurrency
    
    # Override provider if specified
    if provider:
        typer.echo(f"Using provider override: {provider}")
        config_obj.providers = [
            ProviderConfig(
                id=provider,
                provider="fake",
                model=f"fake-{provider}",
                temperature=0.1,
            )
        ]
    
    try:
        typer.echo(f"Running {config_obj.runs} runs per case with {len(config_obj.providers)} provider(s)")
        results = asyncio.run(run_suite(config_obj, output_dir=output))
        
        summary = compute_summary(results, schema, prompt_hash=prompt_hash, schema_hash=schema_hash)
        _print_ranked_table(summary)
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        sys.exit(1)


@app.command()
def ci(
    config: str = typer.Argument(default="aicert.yaml", help="Path to configuration file"),
    output: Optional[str] = typer.Option(None, "-o", "--out", help="Output directory for artifacts"),
    always_store: bool = typer.Option(False, "--always-store", help="Always save artifacts, not just on fail"),
    provider: Optional[str] = typer.Option(None, "-p", "--provider", help="Override provider (e.g., 'fake' for testing)"),
    extract_json: Optional[bool] = typer.Option(None, "--extract-json/--no-extract-json", help="Override extract_json setting"),
    concurrency: Optional[int] = typer.Option(None, "--concurrency", help="Override number of concurrent requests"),
    format: str = typer.Option("text", "--format", help="Output format: text or json", case_sensitive=False),
) -> None:
    """CI mode: evaluate against thresholds and exit with appropriate code.
    
    Exit codes:
      0 - All thresholds passed
      2 - Threshold check failed
      3 - Config/schema error
      4 - Provider/auth error
    
    Uses config.ci.runs for number of runs.
    Default: save artifacts only on fail (unless --always-store is passed).
    """
    from aicert.config import ProviderConfig
    from aicert.metrics import compute_summary
    from aicert.runner import run_suite
    from aicert.artifacts import create_run_dir
    
    # Only print header for text mode
    if format == "text":
        console.print("[bold]aicert ci[/bold] - CI mode threshold evaluation")
    
    try:
        config_obj, schema, prompt_hash, schema_hash = _load_config_and_schema(config)
    except SystemExit:
        raise
    
    # Use ci.runs instead of config.runs
    original_runs = config_obj.runs
    config_obj.runs = config_obj.ci.runs
    
    # Override extract_json if specified
    if extract_json is not None:
        config_obj.validation.extract_json = extract_json
    
    # Override concurrency if specified
    if concurrency is not None:
        config_obj.concurrency = concurrency
    
    # Build thresholds dict
    thresholds = {}
    if config_obj.thresholds.min_stability is not None:
        thresholds["min_stability"] = config_obj.thresholds.min_stability
    if config_obj.thresholds.min_compliance is not None:
        thresholds["min_compliance"] = config_obj.thresholds.min_compliance
    if config_obj.thresholds.max_cost_usd is not None:
        thresholds["max_cost_usd"] = config_obj.thresholds.max_cost_usd
    if config_obj.thresholds.p95_latency_ms is not None:
        thresholds["p95_latency_ms"] = config_obj.thresholds.p95_latency_ms
    
    try:
        if format == "text":
            typer.echo(f"Running {config_obj.runs} runs per case with {len(config_obj.providers)} provider(s)")
        results = asyncio.run(run_suite(config_obj, output_dir=output))
        
        summary = compute_summary(results, schema, prompt_hash=prompt_hash, schema_hash=schema_hash)
        
        # Evaluate thresholds
        passed, failures = _evaluate_thresholds(summary, thresholds)
        
        # Determine if we should store artifacts
        store_artifacts = _should_store(always_store, config_obj.ci.save_on_fail, not passed)
        run_dir = None
        run_id = None
        if store_artifacts:
            run_dir = create_run_dir(output)
            run_id = run_dir.name
        
        if format == "json":
            # Output JSON to stdout
            providers_list = [p.id for p in config_obj.providers]
            json_output = _build_json_output(
                project=config_obj.project,
                run_id=run_id,
                providers=providers_list,
                thresholds=thresholds,
                passed=passed,
                summary=summary,
            )
            typer.echo(json.dumps(json_output, separators=(',', ':')))
        elif format == "junit":
            # Output JUnit XML to stdout
            providers_list = [p.id for p in config_obj.providers]
            junit_output = _build_junit_output(
                project=config_obj.project,
                providers=providers_list,
                thresholds=thresholds,
                passed=passed,
                summary=summary,
            )
            typer.echo(junit_output)
            sys.exit(0 if passed else 2)
        else:
            # Text output (existing behavior)
            _print_ci_summary(summary, thresholds, passed, failures, run_dir, results=results)
            
            if passed:
                console.print("\n[bold green]All thresholds passed[/bold green]")
                sys.exit(0)
            else:
                console.print("\n[bold red]Threshold failures:[/bold red]")
                for failure in failures:
                    console.print(f"  - {failure}")
                sys.exit(2)
            
    except Exception as e:
        if format == "json":
            # In JSON mode, output error as JSON to stderr
            from rich.console import Console
            stderr_console = Console(file=sys.stderr)
            error_json = json.dumps({"error": str(e), "pass": False})
            stderr_console.print(error_json)
        elif format == "junit":
            # In JUnit mode, output error as a testsuite with an error testcase
            import datetime
            timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
            error_msg = _escape_xml(str(e))
            junit_error = f'''<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="aicert" tests="1" failures="0" errors="1" timestamp="{timestamp}">
<testcase name="ci_execution" classname="aicert"><error message="{error_msg}">{error_msg}</error></testcase>
</testsuite>'''
            typer.echo(junit_error)
        else:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")
        sys.exit(1)
    finally:
        # Restore original runs
        config_obj.runs = original_runs


@app.command()
def validate(
    config: str = typer.Argument(default="aicert.yaml", help="Path to configuration file"),
) -> None:
    """Validate configuration file and referenced files.
    
    Exits with code 3 if config is invalid.
    """
    from aicert.config import load_config, ConfigLoadError
    
    console.print("[bold]aicert validate[/bold] - Validating configuration")
    
    try:
        config_obj = load_config(config)
        console.print(f"[bold green]Configuration is valid[/bold green]")
        console.print(f"  Project: {config_obj.project}")
        console.print(f"  Providers: {len(config_obj.providers)}")
        console.print(f"  Runs: {config_obj.runs}")
        console.print(f"  Concurrency: {config_obj.concurrency}")
        sys.exit(0)
    except ConfigLoadError as e:
        console.print(e, file=sys.stderr)
        sys.exit(3)


@app.command()
def report(
    run_arg: str = typer.Argument(..., help="Run directory path or run ID (resolved to .aicert/runs/<run_id>/)"),
    format: str = typer.Option("text", "--format", help="Output format: text or json", case_sensitive=False),
) -> None:
    """Generate a report from a previous run.
    
    Reads summary.json from the run directory and prints a readable report.
    If report.txt exists, prints it; otherwise generates a report from summary.json.
    
    Accepts either a path to a run directory or a run ID. If a run ID is given,
    it will be resolved to .aicert/runs/<run_id>/ in the current working directory.
    
    Exit codes:
      0 - Success
      3 - Missing/invalid run_dir or cannot parse summary/report
    """
    # Resolve run_arg to actual run directory
    run_path = _resolve_run_dir(run_arg)
    
    # Validate run_dir exists
    if not run_path.exists():
        console.print(f"[bold red]Error:[/bold red] Run directory not found: {run_path}")
        sys.exit(3)
    
    if not run_path.is_dir():
        console.print(f"[bold red]Error:[/bold red] Path is not a directory: {run_path}")
        sys.exit(3)
    
    # Get run_id from directory name
    run_id = run_path.name
    
    # Check for report.txt first (only for text format)
    report_path = run_path / "report.txt"
    if format == "text" and report_path.exists():
        console.print("[bold]aicert report[/bold] - Report from stored file")
        typer.echo(report_path.read_text(encoding="utf-8"))
        sys.exit(0)
    
    # Generate report from summary.json
    try:
        summary = _load_summary(run_path)
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/bold red] summary.json not found in {run_path}")
        sys.exit(3)
    except json.JSONDecodeError as e:
        console.print(f"[bold red]Error:[/bold red] Invalid JSON in summary.json: {e}")
        sys.exit(3)
    
    if format == "json":
        # Output JSON: print ONLY the summary.json content augmented with run_id and run_dir
        summary_output = dict(summary)
        summary_output["run_id"] = run_id
        summary_output["run_dir"] = str(run_path)
        typer.echo(json.dumps(summary_output, separators=(',', ':')))
        sys.exit(0)
    else:
        # Text format: generate and print the text report
        report_text = _generate_text_report(summary, run_id)
        console.print("[bold]aicert report[/bold] - Generated from summary.json")
        typer.echo(report_text)
        sys.exit(0)


def _generate_text_report(summary: dict, run_id: str) -> str:
    """Generate a text report from summary data."""
    lines = []
    
    project = summary.get("project", "unknown")
    lines.append(f"Project: {project}")
    lines.append(f"Run ID: {run_id}")
    
    providers = summary.get("per_provider", {})
    if providers:
        lines.append(f"Providers ({len(providers)}):")
        
        for provider_id, metrics in sorted(providers.items()):
            lines.append(f"\n  {provider_id}:")
            
            stability = metrics.get("stability_score", "N/A")
            compliance = metrics.get("schema_compliance", "N/A")
            latency_stats = metrics.get("latency_stats", {})
            p95_latency = latency_stats.get("p95", "N/A")
            mean_latency = latency_stats.get("mean", "N/A")
            total_cost = metrics.get("total_cost_usd", 0)
            total_runs = metrics.get("total_runs", 0)
            
            # Calculate mean cost
            mean_cost = total_cost / total_runs if total_runs > 0 else 0
            
            lines.append(f"    Stability: {stability:.1f}%" if isinstance(stability, float) else f"    Stability: {stability}")
            lines.append(f"    Compliance: {compliance:.1f}%" if isinstance(compliance, float) else f"    Compliance: {compliance}")
            
            if isinstance(p95_latency, float):
                lines.append(f"    P95 Latency: {p95_latency:.0f}ms")
            else:
                lines.append(f"    P95 Latency: {p95_latency}")
                
            if isinstance(mean_latency, float):
                lines.append(f"    Mean Latency: {mean_latency:.0f}ms")
            else:
                lines.append(f"    Mean Latency: {mean_latency}")
                
            if isinstance(mean_cost, float):
                lines.append(f"    Mean Cost: ${mean_cost:.4f}")
            
            # Error counts
            json_parse_fail = metrics.get("json_parse_failures", 0)
            schema_fail = metrics.get("schema_failures", 0)
            provider_err = metrics.get("provider_errors", 0)
            timeouts = metrics.get("timeouts", 0)
            
            lines.append(f"    JSON Parse Failures: {json_parse_fail}")
            lines.append(f"    Schema Failures: {schema_fail}")
            lines.append(f"    Provider Errors: {provider_err}")
            lines.append(f"    Timeouts: {timeouts}")
    else:
        lines.append("  No providers in run summary")
    
    return "\n".join(lines)


def _resolve_run_dir(arg: str) -> Path:
    """Resolve run argument to run directory path.
    
    If arg looks like an existing path, return it as-is.
    Otherwise, treat as run_id and resolve to .aicert/runs/<run_id>/ in cwd.
    
    Args:
        arg: Either a path (existing or absolute/relative) or a run_id.
    
    Returns:
        Path to the run directory.
    """
    # Check if arg looks like a path
    # Paths: starts with /, ./, ../, or contains / or \, or exists
    arg_path = Path(arg)
    
    # If the path exists, use it directly
    if arg_path.exists():
        return arg_path
    
    # If it's an absolute path, use it directly
    if arg_path.is_absolute():
        return arg_path
    
    # If it starts with ./ or ../, treat as relative path
    if arg.startswith('./') or arg.startswith('../') or '/' in arg or '\\' in arg:
        return arg_path
    
    # Otherwise, treat as run_id and resolve to .aicert/runs/<run_id>/
    runs_dir = Path.cwd() / ".aicert" / "runs"
    return runs_dir / arg



    """Compare two run directories and show delta between them.
    
    Exit code is always 0 (informational only).
    """
    console.print("[bold]aicert diff[/bold] - Comparing run results")
    
    # Load both summaries
    try:
        summary_a = _load_summary(run_a)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(3)
    
    try:
        summary_b = _load_summary(run_b)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(3)
    
    console.print(f"\nRun A: {run_a}")
    console.print(f"Run B: {run_b}\n")
    
    # Get providers from both summaries
    providers_a = summary_a.get("per_provider", {})
    providers_b = summary_b.get("per_provider", {})
    
    all_providers = set(providers_a.keys()) | set(providers_b.keys())
    
    for provider_id in sorted(all_providers):
        metrics_a = providers_a.get(provider_id, {})
        metrics_b = providers_b.get(provider_id, {})
        
        if not metrics_a:
            console.print(f"[bold cyan]{provider_id}[/bold cyan] - [yellow]Only in Run B[/yellow]")
            continue
        if not metrics_b:
            console.print(f"[bold cyan]{provider_id}[/bold cyan] - [yellow]Only in Run A[/yellow]")
            continue
        
        console.print(f"[bold cyan]{provider_id}[/bold cyan]")
        
        # Calculate deltas
        stability_a = metrics_a.get("stability_score", 0)
        stability_b = metrics_b.get("stability_score", 0)
        stability_delta = stability_b - stability_a
        
        compliance_a = metrics_a.get("schema_compliance", 0)
        compliance_b = metrics_b.get("schema_compliance", 0)
        compliance_delta = compliance_b - compliance_a
        
        p95_a = metrics_a.get("latency_stats", {}).get("p95", 0)
        p95_b = metrics_b.get("latency_stats", {}).get("p95", 0)
        p95_delta = p95_b - p95_a
        
        cost_a = metrics_a.get("total_cost_usd", 0)
        cost_b = metrics_b.get("total_cost_usd", 0)
        cost_delta = cost_b - cost_a
        
        json_fail_a = metrics_a.get("json_parse_failures", 0)
        json_fail_b = metrics_b.get("json_parse_failures", 0)
        json_fail_delta = json_fail_b - json_fail_a
        
        schema_fail_a = metrics_a.get("schema_failures", 0)
        schema_fail_b = metrics_b.get("schema_failures", 0)
        schema_fail_delta = schema_fail_b - schema_fail_a
        
        # Print deltas (only show if regressions_only is False or if there's a regression)
        def print_delta(label, value_a, value_b, delta, higher_is_better=True):
            delta_sign = "+" if delta > 0 else ""
            if delta == 0:
                return  # No change
            
            if regressions_only:
                # Only show if it's a regression
                if higher_is_better:
                    if delta >= 0:
                        return  # Improvement or no change
                else:
                    if delta <= 0:
                        return  # Improvement or no change
            
            # Determine if it's good or bad
            if higher_is_better:
                if delta > 0:
                    style = "green"
                else:
                    style = "red"
            else:
                if delta < 0:
                    style = "green"
                else:
                    style = "red"
            
            console.print(f"  {label}: {value_a:.1f} → {value_b:.1f} ({delta_sign}{delta:.1f})", style=style)
        
        print_delta("Stability", stability_a, stability_b, stability_delta)
        print_delta("Compliance", compliance_a, compliance_b, compliance_delta)
        print_delta("Latency P95", p95_a, p95_b, p95_delta, higher_is_better=False)
        print_delta("Cost", cost_a, cost_b, cost_delta, higher_is_better=False)
        
        # Error counts (lower is better)
        if not regressions_only or json_fail_delta > 0:
            if json_fail_delta != 0:
                style = "red" if json_fail_delta > 0 else "green"
                console.print(f"  JSON parse failures: {json_fail_a} → {json_fail_b} ({'+' if json_fail_delta > 0 else ''}{json_fail_delta})", style=style)
        
        if not regressions_only or schema_fail_delta > 0:
            if schema_fail_delta != 0:
                style = "red" if schema_fail_delta > 0 else "green"
                console.print(f"  Schema failures: {schema_fail_a} → {schema_fail_b} ({'+' if schema_fail_delta > 0 else ''}{schema_fail_delta})", style=style)


@app.command()
def version() -> None:
    """Show version information."""
    from aicert import __version__
    console.print(f"aicert version: {__version__}")


def _load_summary(path: str) -> dict:
    """Load summary.json from a run directory."""
    from aicert.artifacts import create_run_dir
    
    summary_path = Path(path) / "summary.json"
    
    if not summary_path.exists():
        raise FileNotFoundError(f"summary.json not found in {path}")
    
    with open(summary_path, "r", encoding="utf-8") as f:
        return json.load(f)
