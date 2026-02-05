"""Metrics utilities for aicert."""

import json
import re
import statistics
from typing import Any, Dict, List, Optional


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max."""
    return max(min_val, min(value, max_val))


def canonicalize_json(obj: Any) -> Any:
    """Recursively canonicalize JSON by sorting keys."""
    if isinstance(obj, dict):
        return sorted((k, canonicalize_json(v)) for k, v in obj.items())
    elif isinstance(obj, list):
        return [canonicalize_json(item) for item in obj]
    return obj


def stringify_compact(obj: Any) -> str:
    """Convert canonicalized JSON to compact string."""
    return json.dumps(obj, separators=(',', ':'))


def tokenize(text: str) -> set:
    """Tokenize text by regex into tokens."""
    # Tokenize by alphanumeric sequences
    tokens = re.findall(r'\w+', text.lower())
    return set(tokens)


def jaccard_similarity(set1: set, set2: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set1 and not set2:
        return 1.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def compute_similarity(outputs: List[Optional[Dict]]) -> float:
    """Compute similarity score based on Jaccard similarity of canonicalized tokens."""
    # Filter valid outputs (non-None)
    valid_outputs = [o for o in outputs if o is not None]
    
    if not valid_outputs:
        return 0.0
    
    # Canonicalize and tokenize each output
    canonicalized = [stringify_compact(canonicalize_json(o)) for o in valid_outputs]
    token_sets = [tokenize(c) for c in canonicalized]
    
    # Choose first valid as baseline
    baseline_tokens = token_sets[0]
    
    # Compute Jaccard similarity with baseline for each other
    similarities = [jaccard_similarity(baseline_tokens, ts) for ts in token_sets]
    
    # Average * 100
    return sum(similarities) / len(similarities) * 100 if similarities else 0.0


def compute_structural_consistency(outputs: List[Optional[Dict]], required_keys: List[str]) -> float:
    """Compute structural consistency based on required key frequency."""
    if not required_keys:
        return 100.0
    
    valid_outputs = [o for o in outputs if o is not None]
    
    if not valid_outputs:
        return 0.0
    
    # For each required key, compute frequency present
    key_frequencies = []
    for key in required_keys:
        present_count = sum(1 for o in valid_outputs if isinstance(o, dict) and key in o)
        freq = present_count / len(valid_outputs)
        key_frequencies.append(freq)
    
    # Average across required keys * 100
    return (sum(key_frequencies) / len(key_frequencies)) * 100 if key_frequencies else 0.0


def compute_latency_stats(latencies: List[float]) -> Dict[str, float]:
    """Compute latency statistics: mean, p95, std."""
    if not latencies:
        return {"mean": 0.0, "p95": 0.0, "std": 0.0}
    
    mean_val = statistics.mean(latencies)
    
    # Calculate p95
    sorted_latencies = sorted(latencies)
    p95_idx = int(len(sorted_latencies) * 0.95)
    p95_val = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
    
    # Calculate std
    std_val = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
    
    return {
        "mean": mean_val,
        "p95": p95_val,
        "std": std_val
    }


def compute_latency_stability(latency_stats: Dict[str, float]) -> float:
    """Compute latency stability score."""
    mean = latency_stats.get("mean", 0)
    std = latency_stats.get("std", 0)
    
    if mean <= 0:
        return 0.0
    
    return clamp(100 * (1 - std / mean), 0, 100)


def compute_stability_score(
    compliance: float,
    structural: float,
    similarity: float,
    latency_stability: float
) -> float:
    """Compute final stability score."""
    return compliance * 0.40 + structural * 0.25 + similarity * 0.25 + latency_stability * 0.10


def compute_summary(
    results: List[Dict[str, Any]],
    schema: Dict[str, Any],
    prompt_hash: Optional[str] = None,
    schema_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compute metrics summary from execution results.
    
    Args:
        results: List of execution result dicts with fields:
            provider_id, case_id, ok_json, ok_schema, extra_keys, 
            latency_ms, cost_usd, output_json (parsed JSON when ok_json), error
        schema: JSON schema dict
        prompt_hash: Optional SHA-256 hash of the prompt file
        schema_hash: Optional SHA-256 hash of the schema file
    
    Returns:
        Dict containing per-provider metrics and overall summary
    """
    # Group results by provider
    providers: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        provider_id = result.get("provider_id", "unknown")
        if provider_id not in providers:
            providers[provider_id] = []
        providers[provider_id].append(result)
    
    # Get required keys from schema
    required_keys = schema.get("required", []) if schema else []
    
    # Compute per-provider metrics
    per_provider: Dict[str, Dict[str, Any]] = {}
    for provider_id, provider_results in providers.items():
        total_runs = len(provider_results)
        
        # Count ok_json and ok_schema
        ok_json_count = sum(1 for r in provider_results if r.get("ok_json", False))
        ok_schema_count = sum(1 for r in provider_results if r.get("ok_schema", False))
        
        # Count error types
        json_parse_failures = sum(1 for r in provider_results if not r.get("ok_json", False))
        schema_failures = sum(1 for r in provider_results if r.get("ok_json", False) and not r.get("ok_schema", False))
        provider_errors = sum(1 for r in provider_results if r.get("error") and any(x in r.get("error", "") for x in ["429", "500", "Provider error"]))
        timeouts = sum(1 for r in provider_results if r.get("error") and "Timeout" in r.get("error", ""))
        
        # Compute rates
        json_parse_rate = (ok_json_count / total_runs * 100) if total_runs > 0 else 0.0
        schema_compliance = (ok_schema_count / total_runs * 100) if total_runs > 0 else 0.0
        
        # Collect outputs for structural consistency and similarity
        outputs = [r.get("output_json") for r in provider_results]
        
        # Compute structural consistency
        structural_consistency = compute_structural_consistency(outputs, required_keys)
        
        # Compute similarity
        similarity = compute_similarity(outputs)
        
        # Collect latencies
        latencies = [r.get("latency_ms", 0) for r in provider_results]
        latency_stats = compute_latency_stats(latencies)
        
        # Compute latency stability
        latency_stability = compute_latency_stability(latency_stats)
        
        # Compute final stability score
        stability_score = compute_stability_score(
            schema_compliance,
            structural_consistency,
            similarity,
            latency_stability
        )
        
        # Collect costs
        costs = [r.get("cost_usd", 0) for r in provider_results]
        total_cost = sum(costs)
        
        per_provider[provider_id] = {
            "prompt_hash": prompt_hash,
            "schema_hash": schema_hash,
            "total_runs": total_runs,
            "ok_json_count": ok_json_count,
            "ok_schema_count": ok_schema_count,
            "json_parse_failures": json_parse_failures,
            "schema_failures": schema_failures,
            "provider_errors": provider_errors,
            "timeouts": timeouts,
            "json_parse_rate": json_parse_rate,
            "schema_compliance": schema_compliance,
            "structural_consistency": structural_consistency,
            "similarity": similarity,
            "latency_stats": latency_stats,
            "latency_stability": latency_stability,
            "stability_score": stability_score,
            "total_cost_usd": total_cost,
        }
    
    # Compute overall metrics
    all_results = list(results)
    all_outputs = [r.get("output_json") for r in all_results]
    all_latencies = [r.get("latency_ms", 0) for r in all_results]
    all_costs = [r.get("cost_usd", 0) for r in all_results]
    
    # Overall error counts
    overall_json_parse_failures = sum(1 for r in all_results if not r.get("ok_json", False))
    overall_schema_failures = sum(1 for r in all_results if r.get("ok_json", False) and not r.get("ok_schema", False))
    overall_provider_errors = sum(1 for r in all_results if r.get("error") and any(x in r.get("error", "") for x in ["429", "500", "Provider error"]))
    overall_timeouts = sum(1 for r in all_results if r.get("error") and "Timeout" in r.get("error", ""))
    
    overall = {
        "total_runs": len(all_results),
        "providers_count": len(providers),
        "json_parse_failures": overall_json_parse_failures,
        "schema_failures": overall_schema_failures,
        "provider_errors": overall_provider_errors,
        "timeouts": overall_timeouts,
        "json_parse_rate": (sum(1 for r in all_results if r.get("ok_json", False)) / len(all_results) * 100) if all_results else 0.0,
        "schema_compliance": (sum(1 for r in all_results if r.get("ok_schema", False)) / len(all_results) * 100) if all_results else 0.0,
        "structural_consistency": compute_structural_consistency(all_outputs, required_keys),
        "similarity": compute_similarity(all_outputs),
        "latency_stats": compute_latency_stats(all_latencies),
        "latency_stability": compute_latency_stability(compute_latency_stats(all_latencies)),
        "total_cost_usd": sum(all_costs),
    }
    
    overall["stability_score"] = compute_stability_score(
        overall["schema_compliance"],
        overall["structural_consistency"],
        overall["similarity"],
        overall["latency_stability"]
    )
    
    return {
        "prompt_hash": prompt_hash,
        "schema_hash": schema_hash,
        "per_provider": per_provider,
        "overall": overall,
    }


class Metrics:
    """Container for validation metrics."""

    def __init__(self):
        self.total: int = 0
        self.passed: int = 0
        self.failed: int = 0
        self.errors: List[Dict[str, Any]] = []

    def add_result(self, passed: bool, error: str = None) -> None:
        """Add a validation result."""
        self.total += 1
        if passed:
            self.passed += 1
        else:
            self.failed += 1
            if error:
                self.errors.append({"error": error})

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "success_rate": self.success_rate,
            "errors": self.errors,
        }
