"""Artifact management for aicert runs."""

import json
import random
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def generate_run_id() -> str:
    """Generate a unique run ID with ISO-like timestamp and random suffix."""
    # Get current UTC time in ISO format, replacing colons and periods for safety
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    # Add 6 character random suffix
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{timestamp}-{random_suffix}"


def create_run_dir(out_dir: Optional[str] = None) -> Path:
    """Create a run directory.

    Args:
        out_dir: Optional custom output directory. If None, uses default
                 `.aicert/runs/<run_id>/` under current working directory.

    Returns:
        Path to the created run directory.
    """
    if out_dir is None:
        run_id = generate_run_id()
        run_dir = Path.cwd() / ".aicert" / "runs" / run_id
    else:
        run_dir = Path(out_dir)

    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_config(run_dir: Path, config: Dict[str, Any]) -> Path:
    """Write the resolved config to config.resolved.yaml.

    Args:
        run_dir: Path to the run directory.
        config: Configuration dictionary to write.

    Returns:
        Path to the written file.
    """
    import yaml

    config_path = run_dir / "config.resolved.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    return config_path


def append_result(run_dir: Path, result_dict: Dict[str, Any]) -> Path:
    """Append a result to results.jsonl.

    Args:
        run_dir: Path to the run directory.
        result_dict: Result dictionary to append.

    Returns:
        Path to the results file.
    """
    results_path = run_dir / "results.jsonl"
    with open(results_path, "a", encoding="utf-8") as f:
        json_line = json.dumps(result_dict, ensure_ascii=False)
        f.write(json_line + "\n")
    return results_path


def write_summary(run_dir: Path, summary_dict: Dict[str, Any]) -> Path:
    """Write summary to summary.json.

    Args:
        run_dir: Path to the run directory.
        summary_dict: Summary dictionary to write.

    Returns:
        Path to the written file.
    """
    summary_path = run_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_dict, f, indent=2, ensure_ascii=False)
    return summary_path


def write_report(run_dir: Path, report_text: str) -> Path:
    """Write report to report.txt.

    Args:
        run_dir: Path to the run directory.
        report_text: Report text to write.

    Returns:
        Path to the written file.
    """
    report_path = run_dir / "report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    return report_path
