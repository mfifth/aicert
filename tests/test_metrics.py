"""Tests for metrics module."""

import pytest

from aicert.metrics import (
    Metrics,
    clamp,
    canonicalize_json,
    stringify_compact,
    tokenize,
    jaccard_similarity,
    compute_similarity,
    compute_structural_consistency,
    compute_latency_stats,
    compute_latency_stability,
    compute_stability_score,
    compute_summary,
)


def test_metrics_initial_state():
    """Test metrics initial state."""
    metrics = Metrics()
    assert metrics.total == 0
    assert metrics.passed == 0
    assert metrics.failed == 0
    assert metrics.success_rate == 0.0


def test_metrics_add_passed():
    """Test adding a passed result."""
    metrics = Metrics()
    metrics.add_result(passed=True)
    assert metrics.total == 1
    assert metrics.passed == 1
    assert metrics.failed == 0
    assert metrics.success_rate == 1.0


def test_metrics_add_failed():
    """Test adding a failed result."""
    metrics = Metrics()
    metrics.add_result(passed=False, error="Test error")
    assert metrics.total == 1
    assert metrics.passed == 0
    assert metrics.failed == 1
    assert metrics.success_rate == 0.0
    assert len(metrics.errors) == 1


def test_metrics_multiple_results():
    """Test adding multiple results."""
    metrics = Metrics()
    metrics.add_result(passed=True)
    metrics.add_result(passed=True)
    metrics.add_result(passed=False, error="Error 1")
    metrics.add_result(passed=False, error="Error 2")
    assert metrics.total == 4
    assert metrics.passed == 2
    assert metrics.failed == 2
    assert metrics.success_rate == 0.5


def test_metrics_to_dict():
    """Test converting metrics to dictionary."""
    metrics = Metrics()
    metrics.add_result(passed=True)
    metrics.add_result(passed=False, error="Test error")

    result = metrics.to_dict()
    assert result["total"] == 2
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["success_rate"] == 0.5
    assert len(result["errors"]) == 1


def test_metrics_empty_success_rate():
    """Test success rate with no results."""
    metrics = Metrics()
    assert metrics.success_rate == 0.0


def test_clamp():
    """Test clamp function."""
    assert clamp(5, 0, 10) == 5
    assert clamp(-5, 0, 10) == 0
    assert clamp(15, 0, 10) == 10


def test_canonicalize_json():
    """Test JSON canonicalization - dict keys are sorted."""
    obj = {"b": 2, "a": 1, "c": [3, 2, 1]}
    result = canonicalize_json(obj)
    # Dict keys sorted, but lists maintain order (as they have no "keys")
    assert result == [("a", 1), ("b", 2), ("c", [3, 2, 1])]


def test_stringify_compact():
    """Test compact stringification."""
    obj = [("a", 1), ("b", 2)]
    result = stringify_compact(obj)
    assert result == '[["a",1],["b",2]]'


def test_tokenize():
    """Test tokenization."""
    text = '[["a",1],["b",2]]'
    tokens = tokenize(text)
    assert tokens == {"a", "1", "b", "2"}


def test_jaccard_similarity():
    """Test Jaccard similarity."""
    set1 = {"a", "b", "c"}
    set2 = {"b", "c", "d"}
    similarity = jaccard_similarity(set1, set2)
    assert similarity == 2 / 4  # intersection=2, union=4


def test_compute_similarity_identical():
    """Test similarity is 100% for identical JSON."""
    outputs = [
        {"a": 1, "b": 2},
        {"a": 1, "b": 2},
        {"a": 1, "b": 2},
    ]
    similarity = compute_similarity(outputs)
    assert similarity == 100.0


def test_compute_similarity_different():
    """Test similarity for different JSON."""
    outputs = [
        {"a": 1, "b": 2},
        {"a": 1, "b": 3},
        {"a": 1, "b": 4},
    ]
    similarity = compute_similarity(outputs)
    # Should be less than 100% due to different values
    assert similarity < 100.0
    assert similarity > 0.0


def test_compute_similarity_empty():
    """Test similarity with empty outputs."""
    outputs = [None, None, None]
    similarity = compute_similarity(outputs)
    assert similarity == 0.0


def test_compute_structural_consistency():
    """Test structural consistency computation."""
    outputs = [
        {"key1": "a", "key2": "b"},
        {"key1": "a", "key2": "b"},
        {"key1": "a"},  # Missing key2
    ]
    required_keys = ["key1", "key2"]
    consistency = compute_structural_consistency(outputs, required_keys)
    # key1 present in 3/3, key2 present in 2/3, average = (1 + 0.666) / 2 = 0.833
    assert consistency == pytest.approx(83.333, rel=1e-2)


def test_compute_structural_consistency_all_present():
    """Test structural consistency when all required keys present."""
    outputs = [
        {"key1": "a", "key2": "b"},
        {"key1": "x", "key2": "y"},
    ]
    required_keys = ["key1", "key2"]
    consistency = compute_structural_consistency(outputs, required_keys)
    assert consistency == 100.0


def test_compute_structural_consistency_no_required_keys():
    """Test structural consistency with no required keys."""
    outputs = [{"a": 1}, {"b": 2}]
    consistency = compute_structural_consistency(outputs, [])
    assert consistency == 100.0


def test_compute_latency_stats():
    """Test latency statistics."""
    latencies = [100, 200, 300, 400, 500]
    stats = compute_latency_stats(latencies)
    assert stats["mean"] == 300
    assert stats["p95"] == 500  # p95 of [100,200,300,400,500]
    assert stats["std"] > 0


def test_compute_latency_stats_empty():
    """Test latency stats with empty list."""
    stats = compute_latency_stats([])
    assert stats["mean"] == 0.0
    assert stats["p95"] == 0.0
    assert stats["std"] == 0.0


def test_compute_latency_stability():
    """Test latency stability computation."""
    # Low std relative to mean = high stability
    stats = {"mean": 100, "std": 10}
    stability = compute_latency_stability(stats)
    assert stability == pytest.approx(90.0, rel=1e-2)  # 100 * (1 - 10/100) = 90

    # High std relative to mean = low stability
    stats = {"mean": 100, "std": 90}
    stability = compute_latency_stability(stats)
    assert stability == pytest.approx(10.0, rel=1e-2)  # 100 * (1 - 90/100) = 10


def test_compute_latency_stability_zero_mean():
    """Test latency stability with zero mean."""
    stats = {"mean": 0, "std": 0}
    stability = compute_latency_stability(stats)
    assert stability == 0.0


def test_compute_stability_score():
    """Test stability score formula."""
    score = compute_stability_score(100.0, 100.0, 100.0, 100.0)
    assert score == 100.0

    score = compute_stability_score(50.0, 50.0, 50.0, 50.0)
    # 50*0.40 + 50*0.25 + 50*0.25 + 50*0.10 = 20 + 12.5 + 12.5 + 5 = 50
    assert score == 50.0


def test_compute_summary_basic():
    """Test basic compute_summary."""
    results = [
        {
            "provider_id": "provider_a",
            "case_id": "case1",
            "ok_json": True,
            "ok_schema": True,
            "extra_keys": False,
            "latency_ms": 100,
            "cost_usd": 0.01,
            "output_json": {"greeting": "hello", "answer": "world"},
            "error": None,
        },
        {
            "provider_id": "provider_a",
            "case_id": "case2",
            "ok_json": True,
            "ok_schema": True,
            "extra_keys": False,
            "latency_ms": 200,
            "cost_usd": 0.02,
            "output_json": {"greeting": "hello", "answer": "there"},
            "error": None,
        },
    ]
    schema = {
        "type": "object",
        "properties": {
            "greeting": {"type": "string"},
            "answer": {"type": "string"},
        },
        "required": ["greeting", "answer"],
    }

    summary = compute_summary(results, schema)

    assert "per_provider" in summary
    assert "overall" in summary
    assert "provider_a" in summary["per_provider"]

    provider_metrics = summary["per_provider"]["provider_a"]
    assert provider_metrics["total_runs"] == 2
    assert provider_metrics["json_parse_rate"] == 100.0
    assert provider_metrics["schema_compliance"] == 100.0
    assert provider_metrics["structural_consistency"] == 100.0  # Both have required keys


def test_compute_summary_multiple_providers():
    """Test compute_summary with multiple providers."""
    results = [
        {
            "provider_id": "provider_a",
            "case_id": "case1",
            "ok_json": True,
            "ok_schema": True,
            "extra_keys": False,
            "latency_ms": 100,
            "cost_usd": 0.01,
            "output_json": {"greeting": "hello"},
            "error": None,
        },
        {
            "provider_id": "provider_b",
            "case_id": "case1",
            "ok_json": True,
            "ok_schema": True,
            "extra_keys": False,
            "latency_ms": 150,
            "cost_usd": 0.02,
            "output_json": {"greeting": "hi"},
            "error": None,
        },
    ]
    schema = {
        "type": "object",
        "properties": {"greeting": {"type": "string"}},
        "required": ["greeting"],
    }

    summary = compute_summary(results, schema)

    assert len(summary["per_provider"]) == 2
    assert "provider_a" in summary["per_provider"]
    assert "provider_b" in summary["per_provider"]
    assert summary["overall"]["providers_count"] == 2
    assert summary["overall"]["total_runs"] == 2


def test_compute_summary_json_parse_failures():
    """Test compute_summary with JSON parse failures."""
    results = [
        {
            "provider_id": "provider_a",
            "case_id": "case1",
            "ok_json": True,
            "ok_schema": True,
            "extra_keys": False,
            "latency_ms": 100,
            "cost_usd": 0.01,
            "output_json": {"key": "value"},
            "error": None,
        },
        {
            "provider_id": "provider_a",
            "case_id": "case2",
            "ok_json": False,  # JSON parse failed
            "ok_schema": False,
            "extra_keys": False,
            "latency_ms": 50,
            "cost_usd": 0.01,
            "output_json": None,
            "error": "Parse error",
        },
    ]
    schema = {
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
    }

    summary = compute_summary(results, schema)

    provider_metrics = summary["per_provider"]["provider_a"]
    assert provider_metrics["total_runs"] == 2
    assert provider_metrics["json_parse_rate"] == 50.0
    # Compliance based on ok_schema
    assert provider_metrics["schema_compliance"] == 50.0


def test_compute_summary_empty_results():
    """Test compute_summary with empty results."""
    summary = compute_summary([], {})
    assert summary["overall"]["total_runs"] == 0
    assert summary["overall"]["providers_count"] == 0
    assert summary["per_provider"] == {}


def test_compute_summary_with_hashes():
    """Test compute_summary includes prompt_hash and schema_hash at top level and per provider."""
    results = [
        {
            "provider_id": "provider_a",
            "case_id": "case1",
            "ok_json": True,
            "ok_schema": True,
            "extra_keys": False,
            "latency_ms": 100,
            "cost_usd": 0.01,
            "output_json": {"greeting": "hello"},
            "error": None,
        },
    ]
    schema = {
        "type": "object",
        "properties": {"greeting": {"type": "string"}},
        "required": ["greeting"],
    }
    prompt_hash = "sha256:abc123"
    schema_hash = "sha256:def456"

    summary = compute_summary(results, schema, prompt_hash=prompt_hash, schema_hash=schema_hash)

    # Check top-level hashes
    assert summary["prompt_hash"] == prompt_hash
    assert summary["schema_hash"] == schema_hash

    # Check per-provider hashes
    assert summary["per_provider"]["provider_a"]["prompt_hash"] == prompt_hash
    assert summary["per_provider"]["provider_a"]["schema_hash"] == schema_hash


def test_compute_summary_hashes_default_none():
    """Test compute_summary has None hashes when not provided."""
    results = [
        {
            "provider_id": "provider_a",
            "case_id": "case1",
            "ok_json": True,
            "ok_schema": True,
            "extra_keys": False,
            "latency_ms": 100,
            "cost_usd": 0.01,
            "output_json": {"greeting": "hello"},
            "error": None,
        },
    ]
    schema = {
        "type": "object",
        "properties": {"greeting": {"type": "string"}},
        "required": ["greeting"],
    }

    summary = compute_summary(results, schema)

    # Check top-level hashes are None
    assert summary["prompt_hash"] is None
    assert summary["schema_hash"] is None

    # Check per-provider hashes are None
    assert summary["per_provider"]["provider_a"]["prompt_hash"] is None
    assert summary["per_provider"]["provider_a"]["schema_hash"] is None
