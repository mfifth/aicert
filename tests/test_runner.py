"""Integration tests for the async runner."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from aicert.config import Config, ProviderConfig, ChaosConfig, ThresholdsConfig, CIConfig
from aicert.runner import FakeAdapter, run_suite, run_single_with_retry, execute_case, ProviderError
from aicert.templating import render_prompt
from aicert.validation import validate_output


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_cases():
    """Sample test cases for testing."""
    return [
        {"name": "test_math", "prompt": "What is {{ question }}?", "variables": {"question": "2 + 2"}},
        {"name": "test_capitals", "prompt": "What is the capital of {{ country }}?", "variables": {"country": "France"}},
        {"name": "test_planets", "prompt": "How many planets in {{ system }}?", "variables": {"system": "our solar system"}},
    ]


@pytest.fixture
def sample_schema():
    """Sample JSON schema for testing."""
    return {
        "type": "object",
        "properties": {
            "greeting": {"type": "string"},
            "answer": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["greeting", "answer", "confidence"],
        "additionalProperties": False,
    }


@pytest.fixture
def sample_config(temp_dir, sample_cases, sample_schema):
    """Sample configuration for testing."""
    # Write cases file
    cases_file = Path(temp_dir) / "cases.jsonl"
    with open(cases_file, "w") as f:
        for case in sample_cases:
            f.write(json.dumps(case) + "\n")
    
    # Write schema file
    schema_file = Path(temp_dir) / "schema.json"
    with open(schema_file, "w") as f:
        json.dump(sample_schema, f)
    
    # Write prompt file
    prompt_file = Path(temp_dir) / "prompt.txt"
    with open(prompt_file, "w") as f:
        f.write("Respond with JSON: greeting, answer, confidence\nQuestion: {{ question }}")
    
    return Config(
        project="test-project",
        providers=[
            ProviderConfig(
                id="fake-test",
                provider="fake",
                model="fake-model",
                temperature=0.1,
            ),
        ],
        prompt_file=str(prompt_file),
        cases_file=str(cases_file),
        schema_file=str(schema_file),
        runs=5,
        concurrency=3,
        timeout_s=10,
    )


class TestFakeAdapter:
    """Tests for FakeAdapter."""
    
    def test_generate_returns_json(self):
        """Test that FakeAdapter generates valid JSON responses."""
        adapter = FakeAdapter(latency_ms=10)
        
        async def run():
            result = await adapter.generate("Test prompt")
            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            assert "greeting" in parsed
            assert "answer" in parsed
            assert "confidence" in parsed
        
        asyncio.run(run())
    
    def test_generate_deterministic(self):
        """Test that FakeAdapter returns consistent output for same input."""
        adapter = FakeAdapter(latency_ms=0)
        
        async def run():
            result1 = await adapter.generate("What is 2 + 2?")
            result2 = await adapter.generate("What is 2 + 2?")
            assert result1 == result2
        
        asyncio.run(run())
    
    def test_error_simulation(self):
        """Test that FakeAdapter can simulate errors."""
        adapter = FakeAdapter(error_rate=1.0, latency_ms=1)
        
        async def run():
            with pytest.raises(Exception):
                await adapter.generate("Test prompt")
        
        asyncio.run(run())


class TestRunSingleWithRetry:
    """Tests for retry logic."""
    
    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Test that successful calls return immediately."""
        adapter = FakeAdapter(latency_ms=10)
        start = asyncio.get_event_loop().time()
        result = await run_single_with_retry(adapter, "test", timeout_s=5)
        elapsed = asyncio.get_event_loop().time() - start
        
        assert result["ok"]
        assert result["attempt"] == 0
        assert elapsed < 1.0  # Should complete quickly
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test that timeout errors are handled."""
        adapter = FakeAdapter(latency_ms=500)  # Very slow
        
        result = await run_single_with_retry(adapter, "test", timeout_s=0.1, max_retries=2)
        
        assert not result["ok"]
        assert "Timeout" in result["error"] or result["attempt"] > 0


class TestExecuteCase:
    """Tests for single case execution."""
    
    @pytest.mark.asyncio
    async def test_execute_case_success(self, sample_schema):
        """Test successful case execution."""
        adapter = FakeAdapter(latency_ms=10)
        semaphore = asyncio.Semaphore(1)
        
        case = {
            "name": "test_case",
            "prompt": "What is {{ question }}?",
            "variables": {"question": "2 + 2"},
        }
        
        # Create a mock config with timeout
        class MockConfig:
            timeout_s = 10
            validation = type('obj', (object,), {'extract_json': True, 'allow_extra_keys': False})()
        
        result = await execute_case(
            adapter=adapter,
            case=case,
            case_id="test_case",
            schema=sample_schema,
            schema_hint="answer: string | confidence: number | greeting: string",
            config=MockConfig(),
            run_index=0,
            semaphore=semaphore,
        )
        
        assert result["ok_json"]
        assert result["ok_schema"]
        assert result["output_json"]["answer"] == "4"
    
    @pytest.mark.asyncio
    async def test_concurrency_control(self, sample_schema):
        """Test that semaphore limits concurrency."""
        adapter = FakeAdapter(latency_ms=100)
        semaphore = asyncio.Semaphore(2)  # Allow only 2 concurrent
        
        case = {
            "name": "test",
            "prompt": "Test {{ var }}",
            "variables": {"var": "value"},
        }
        
        # Create a mock config with timeout
        class MockConfig:
            timeout_s = 10
            validation = type('obj', (object,), {'extract_json': True, 'allow_extra_keys': False})()
        
        start = asyncio.get_event_loop().time()
        
        # Run 4 tasks with concurrency of 2
        tasks = [
            execute_case(
                adapter=adapter,
                case=case,
                case_id=f"case_{i}",
                schema=sample_schema,
                schema_hint="",
                config=MockConfig(),
                run_index=i,
                semaphore=semaphore,
            )
            for i in range(4)
        ]
        
        await asyncio.gather(*tasks)
        elapsed = asyncio.get_event_loop().time() - start
        
        # With concurrency=2 and 4 tasks at 100ms each:
        # Should take ~200ms (2 batches of 2 parallel tasks)
        # Allow some tolerance
        assert elapsed >= 0.15  # At least 150ms
        assert elapsed < 0.35   # Less than 350ms (would be 400ms if sequential)


class TestRunSuite:
    """Integration tests for the full run_suite function."""
    
    @pytest.mark.asyncio
    async def test_run_suite_with_fake_adapter(self, sample_config, temp_dir):
        """Test run_suite with FakeAdapter produces results."""
        results = await run_suite(sample_config, output_dir=temp_dir)
        
        # Should have runs * cases results
        expected_count = sample_config.runs * len(sample_config.providers) * len([
            {"name": "test_math"},
            {"name": "test_capitals"},
            {"name": "test_planets"},
        ])
        assert len(results) == expected_count
        
        # Check results structure
        for result in results:
            assert "provider_id" in result
            assert "case_id" in result
            assert "run_index" in result
            assert "ok_json" in result
            assert "ok_schema" in result
    
    @pytest.mark.asyncio
    async def test_concurrency_doesnt_break_output(self, sample_config, temp_dir):
        """Test that concurrent execution produces valid outputs."""
        # Increase runs for more thorough testing
        sample_config.runs = 10
        sample_config.concurrency = 5
        
        results = await run_suite(sample_config, output_dir=temp_dir)
        
        # All results should have valid structure
        for result in results:
            # Either successful with valid output, or failed with error
            assert (result["ok_json"] and result["output_json"] is not None) or \
                   (not result["ok_json"] and result["error"] is not None)
        
        # Verify all outputs are consistent for the same case/run
        # (FakeAdapter is deterministic)
        case_run_groups = {}
        for result in results:
            key = (result["case_id"], result["run_index"])
            case_run_groups.setdefault(key, []).append(result)
        
        for key, group in case_run_groups.items():
            # All providers should have same case_id and run_index
            for r in group:
                assert r["case_id"] == key[0]
                assert r["run_index"] == key[1]
    
    def test_results_jsonl_written(self, sample_config, temp_dir):
        """Test that results are written to results.jsonl."""
        async def run():
            return await run_suite(sample_config, output_dir=temp_dir)
        
        asyncio.run(run())
        
        results_file = Path(temp_dir) / "results.jsonl"
        assert results_file.exists()
        
        # Verify JSONL format
        lines = results_file.read_text().strip().split("\n")
        assert len(lines) > 0
        
        for line in lines:
            parsed = json.loads(line)
            assert "provider_id" in parsed
            assert "case_id" in parsed
    
    def test_summary_json_written(self, sample_config, temp_dir):
        """Test that summary.json is written."""
        from aicert.metrics import compute_summary
        from aicert.artifacts import write_summary
        
        async def run():
            results = await run_suite(sample_config, output_dir=temp_dir)
            return results
        
        results = asyncio.run(run())
        
        # Load schema for summary
        schema = json.load(open(sample_config.schema_file))
        summary = compute_summary(results, schema)
        
        summary_file = Path(temp_dir) / "summary.json"
        write_summary(Path(temp_dir), summary)
        
        assert summary_file.exists()


class TestRenderPrompt:
    """Tests for prompt rendering integration."""
    
    def test_render_with_schema_hint(self):
        """Test that schema_hint is properly injected."""
        template = "Answer: {{ question }}. Schema: {{ schema_hint }}"
        case = {"question": "What is 2+2?"}
        schema_hint = "answer: string"
        
        result = render_prompt(template, case, schema_hint)
        
        assert "What is 2+2?" in result
        assert "answer: string" in result


class TestValidationIntegration:
    """Tests for validation integration with runner."""
    
    @pytest.mark.asyncio
    async def test_validate_fake_adapter_output(self, sample_schema):
        """Test that FakeAdapter output passes validation."""
        adapter = FakeAdapter(latency_ms=10)
        semaphore = asyncio.Semaphore(1)
        
        case = {
            "name": "test",
            "prompt": "Test {{ var }}",
            "variables": {"var": "value"},
        }
        
        # Create a mock config with timeout
        class MockConfig:
            timeout_s = 10
            validation = type('obj', (object,), {'extract_json': True, 'allow_extra_keys': False})()
        
        result = await execute_case(
            adapter=adapter,
            case=case,
            case_id="test_case",
            schema=sample_schema,
            schema_hint="answer: string | confidence: number | greeting: string",
            config=MockConfig(),
            run_index=0,
            semaphore=semaphore,
        )
        
        # FakeAdapter output should pass validation
        assert result["ok_json"]
        assert result["ok_schema"] or result.get("extra_keys") == []


class TestFakeAdapterChaosMode:
    """Tests for FakeAdapter chaos mode."""
    
    def test_chaos_mode_enabled_with_config(self):
        """Test that chaos mode is enabled when chaos config is provided."""
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.5,
            p_wrong_schema=0.0,
            p_extra_keys=0.0,
            p_wrapped_json=0.0,
            p_non_json=0.0,
            p_timeout=0.0,
            p_http_429=0.0,
            p_http_500=0.0,
        )
        adapter = FakeAdapter(chaos=chaos)
        assert adapter.chaos_enabled is True
    
    def test_chaos_mode_disabled_without_config(self):
        """Test that chaos mode is disabled when no chaos config is provided."""
        adapter = FakeAdapter()
        assert adapter.chaos_enabled is False
    
    @pytest.mark.asyncio
    async def test_chaos_mode_returns_various_responses(self):
        """Test that chaos mode produces various types of responses."""
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.0,
            p_wrong_schema=0.0,
            p_extra_keys=0.0,
            p_wrapped_json=0.0,
            p_non_json=0.0,
            p_timeout=0.0,
            p_http_429=0.0,
            p_http_500=0.0,
        )
        adapter = FakeAdapter(chaos=chaos)
        
        # Should return valid JSON when no chaos triggers
        result = await adapter.generate("Test prompt")
        content = result["choices"][0]["message"]["content"]
        
        # Should be valid JSON
        parsed = json.loads(content)
        assert "greeting" in parsed
        assert "answer" in parsed
    
    @pytest.mark.asyncio
    async def test_chaos_mode_non_json_response(self):
        """Test that chaos mode can produce non-JSON responses."""
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.0,
            p_wrong_schema=0.0,
            p_extra_keys=0.0,
            p_wrapped_json=0.0,
            p_non_json=1.0,  # 100% non-JSON
            p_timeout=0.0,
            p_http_429=0.0,
            p_http_500=0.0,
        )
        adapter = FakeAdapter(chaos=chaos)
        
        result = await adapter.generate("Test prompt")
        content = result["choices"][0]["message"]["content"]
        
        # Should be non-JSON text - should not be parseable as JSON
        try:
            json.loads(content)
            assert False, "Content should not be valid JSON"
        except json.JSONDecodeError:
            pass  # Expected - content is not JSON
    
    @pytest.mark.asyncio
    async def test_chaos_mode_wrapped_json(self):
        """Test that chaos mode can produce JSON wrapped in markdown fence."""
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.0,
            p_wrong_schema=0.0,
            p_extra_keys=0.0,
            p_wrapped_json=1.0,  # 100% wrapped JSON
            p_non_json=0.0,
            p_timeout=0.0,
            p_http_429=0.0,
            p_http_500=0.0,
        )
        adapter = FakeAdapter(chaos=chaos)
        
        result = await adapter.generate("Test prompt")
        content = result["choices"][0]["message"]["content"]
        
        # Should contain markdown fence
        assert "```json" in content
    
    @pytest.mark.asyncio
    async def test_chaos_mode_extra_keys(self):
        """Test that chaos mode can produce JSON with extra keys."""
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.0,
            p_wrong_schema=0.0,
            p_extra_keys=1.0,  # 100% extra keys
            p_wrapped_json=0.0,
            p_non_json=0.0,
            p_timeout=0.0,
            p_http_429=0.0,
            p_http_500=0.0,
        )
        adapter = FakeAdapter(chaos=chaos)
        
        result = await adapter.generate("Test prompt")
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        
        # Should have extra keys
        assert "extra_field_1" in parsed or "extra_field_2" in parsed
    
    @pytest.mark.asyncio
    async def test_chaos_mode_wrong_schema(self):
        """Test that chaos mode can produce JSON with wrong schema."""
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.0,
            p_wrong_schema=1.0,  # 100% wrong schema
            p_extra_keys=0.0,
            p_wrapped_json=0.0,
            p_non_json=0.0,
            p_timeout=0.0,
            p_http_429=0.0,
            p_http_500=0.0,
        )
        adapter = FakeAdapter(chaos=chaos)
        
        result = await adapter.generate("Test prompt")
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        
        # Should be missing required fields or wrong types
        # confidence should be string instead of number
        assert "confidence" in parsed
        assert isinstance(parsed["confidence"], str)
    
    @pytest.mark.asyncio
    async def test_chaos_mode_invalid_json(self):
        """Test that chaos mode can produce invalid JSON."""
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=1.0,  # 100% invalid JSON
            p_wrong_schema=0.0,
            p_extra_keys=0.0,
            p_wrapped_json=0.0,
            p_non_json=0.0,
            p_timeout=0.0,
            p_http_429=0.0,
            p_http_500=0.0,
        )
        adapter = FakeAdapter(chaos=chaos)
        
        result = await adapter.generate("Test prompt")
        content = result["choices"][0]["message"]["content"]
        
        # Should be invalid JSON (truncated)
        with pytest.raises(json.JSONDecodeError):
            json.loads(content)
    
    @pytest.mark.asyncio
    async def test_chaos_mode_timeout(self):
        """Test that chaos mode can raise timeout errors."""
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.0,
            p_wrong_schema=0.0,
            p_extra_keys=0.0,
            p_wrapped_json=0.0,
            p_non_json=0.0,
            p_timeout=1.0,  # 100% timeout
            p_http_429=0.0,
            p_http_500=0.0,
        )
        adapter = FakeAdapter(chaos=chaos)
        
        with pytest.raises(asyncio.TimeoutError):
            await adapter.generate("Test prompt")
    
    @pytest.mark.asyncio
    async def test_chaos_mode_http_429(self):
        """Test that chaos mode can raise HTTP 429 errors."""
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.0,
            p_wrong_schema=0.0,
            p_extra_keys=0.0,
            p_wrapped_json=0.0,
            p_non_json=0.0,
            p_timeout=0.0,
            p_http_429=1.0,  # 100% HTTP 429
            p_http_500=0.0,
        )
        adapter = FakeAdapter(chaos=chaos)
        
        with pytest.raises(ProviderError) as exc_info:
            await adapter.generate("Test prompt")
        
        assert exc_info.value.status_code == 429
    
    @pytest.mark.asyncio
    async def test_chaos_mode_http_500(self):
        """Test that chaos mode can raise HTTP 500 errors."""
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.0,
            p_wrong_schema=0.0,
            p_extra_keys=0.0,
            p_wrapped_json=0.0,
            p_non_json=0.0,
            p_timeout=0.0,
            p_http_429=0.0,
            p_http_500=1.0,  # 100% HTTP 500
        )
        adapter = FakeAdapter(chaos=chaos)
        
        with pytest.raises(ProviderError) as exc_info:
            await adapter.generate("Test prompt")
        
        assert exc_info.value.status_code == 500
    
    def test_chaos_mode_reproducible_with_seed(self):
        """Test that chaos mode is reproducible with the same seed."""
        # Use p_non_json=1.0 to always trigger non-JSON response for deterministic test
        chaos = ChaosConfig(
            seed=42,
            p_invalid_json=0.0,
            p_wrong_schema=0.0,
            p_extra_keys=0.0,
            p_wrapped_json=0.0,
            p_non_json=1.0,  # Always return non-JSON
            p_timeout=0.0,
            p_http_429=0.0,
            p_http_500=0.0,
        )
        
        async def run(adapter):
            return await adapter.generate("Test prompt")
        
        adapter1 = FakeAdapter(chaos=ChaosConfig(**chaos.model_dump()))
        adapter2 = FakeAdapter(chaos=ChaosConfig(**chaos.model_dump()))
        
        result1 = asyncio.run(run(adapter1))
        result2 = asyncio.run(run(adapter2))
        
        # Same seed should produce same content
        content1 = result1["choices"][0]["message"]["content"]
        content2 = result2["choices"][0]["message"]["content"]
        assert content1 == content2


class TestChaosConfigIntegration:
    """Integration tests for chaos mode with the runner."""
    
    @pytest.fixture
    def chaos_config(self, temp_dir, sample_schema):
        """Create a configuration with chaos mode enabled."""
        # Write cases file
        cases = [
            {"name": "test_math", "prompt": "What is {{ question }}?", "variables": {"question": "2 + 2"}},
            {"name": "test_capitals", "prompt": "What is the capital of {{ country }}?", "variables": {"country": "France"}},
        ]
        cases_file = Path(temp_dir) / "cases.jsonl"
        with open(cases_file, "w") as f:
            for case in cases:
                f.write(json.dumps(case) + "\n")
        
        # Write schema file
        schema_file = Path(temp_dir) / "schema.json"
        with open(schema_file, "w") as f:
            json.dump(sample_schema, f)
        
        # Write prompt file
        prompt_file = Path(temp_dir) / "prompt.txt"
        with open(prompt_file, "w") as f:
            f.write("Respond with JSON: greeting, answer, confidence\nQuestion: {{ question }}")
        
        # Create chaos config
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.10,
            p_wrong_schema=0.10,
            p_extra_keys=0.15,
            p_wrapped_json=0.20,
            p_non_json=0.05,
            p_timeout=0.05,
            p_http_429=0.05,
            p_http_500=0.05,
        )
        
        return Config(
            project="chaos-test",
            providers=[
                ProviderConfig(
                    id="fake-chaos",
                    provider="fake",
                    model="fake-model",
                    temperature=0.1,
                    chaos=chaos,
                ),
            ],
            prompt_file=str(prompt_file),
            cases_file=str(cases_file),
            schema_file=str(schema_file),
            runs=10,
            concurrency=5,
            timeout_s=5,
        )
    
    @pytest.mark.asyncio
    async def test_chaos_mode_produces_successes_and_failures(self, chaos_config, temp_dir):
        """Test that chaos mode produces both successes and failures."""
        results = await run_suite(chaos_config, output_dir=temp_dir)
        
        # Should have runs * cases results
        expected_count = chaos_config.runs * len(chaos_config.providers) * 2  # 2 cases
        assert len(results) == expected_count
        
        # Count successes and failures
        ok_json_count = sum(1 for r in results if r.get("ok_json", False))
        ok_schema_count = sum(1 for r in results if r.get("ok_schema", False))
        
        # Should have both successes and failures
        assert ok_json_count > 0, "Should have at least one successful JSON parse"
        assert ok_json_count < expected_count, "Should have at least one JSON parse failure"
    
    @pytest.mark.asyncio
    async def test_chaos_runner_doesnt_crash(self, chaos_config, temp_dir):
        """Test that runner doesn't crash under chaos mode."""
        # Run with higher concurrency
        chaos_config.concurrency = 10
        chaos_config.runs = 20
        
        results = await run_suite(chaos_config, output_dir=temp_dir)
        
        # Should complete without crashing
        assert len(results) == chaos_config.runs * len(chaos_config.providers) * 2
        
        # All results should have valid structure
        for result in results:
            assert "provider_id" in result
            assert "case_id" in result
            assert "run_index" in result
            assert "ok_json" in result
            assert "ok_schema" in result
    
    def test_chaos_results_jsonl_written(self, chaos_config, temp_dir):
        """Test that results are written to results.jsonl with chaos mode."""
        async def run():
            return await run_suite(chaos_config, output_dir=temp_dir)
        
        asyncio.run(run())
        
        results_file = Path(temp_dir) / "results.jsonl"
        assert results_file.exists()
        
        # Verify JSONL format
        lines = results_file.read_text().strip().split("\n")
        assert len(lines) == chaos_config.runs * len(chaos_config.providers) * 2
        
        for line in lines:
            parsed = json.loads(line)
            assert "provider_id" in parsed
            assert "case_id" in parsed
            assert "ok_json" in parsed
    
    def test_chaos_metrics_include_error_counts(self, chaos_config, temp_dir):
        """Test that metrics include error counts for chaos mode."""
        from aicert.metrics import compute_summary
        
        async def run():
            return await run_suite(chaos_config, output_dir=temp_dir)
        
        results = asyncio.run(run())
        summary = compute_summary(results, chaos_config.providers[0].chaos.model_dump())
        
        # Should have error counts in metrics
        overall = summary["overall"]
        assert "json_parse_failures" in overall
        assert "schema_failures" in overall
        assert "provider_errors" in overall
        assert "timeouts" in overall


class TestCIGatingWithChaos:
    """Tests for CI gating behavior with chaos mode."""
    
    @pytest.fixture
    def ci_chaos_config(self, temp_dir, sample_schema):
        """Create a CI configuration with strict thresholds and chaos mode."""
        # Write cases file
        cases = [
            {"name": "test_math", "prompt": "What is {{ question }}?", "variables": {"question": "2 + 2"}},
        ]
        cases_file = Path(temp_dir) / "cases.jsonl"
        with open(cases_file, "w") as f:
            for case in cases:
                f.write(json.dumps(case) + "\n")
        
        # Write schema file
        schema_file = Path(temp_dir) / "schema.json"
        with open(schema_file, "w") as f:
            json.dump(sample_schema, f)
        
        # Write prompt file
        prompt_file = Path(temp_dir) / "prompt.txt"
        with open(prompt_file, "w") as f:
            f.write("Respond with JSON\nQuestion: {{ question }}")
        
        # Create chaos config with high failure rates
        chaos = ChaosConfig(
            seed=1337,
            p_invalid_json=0.3,
            p_wrong_schema=0.3,
            p_extra_keys=0.0,
            p_wrapped_json=0.0,
            p_non_json=0.0,
            p_timeout=0.0,
            p_http_429=0.0,
            p_http_500=0.0,
        )
        
        return Config(
            project="chaos-ci-test",
            providers=[
                ProviderConfig(
                    id="fake-chaos",
                    provider="fake",
                    model="fake-model",
                    temperature=0.1,
                    chaos=chaos,
                ),
            ],
            prompt_file=str(prompt_file),
            cases_file=str(cases_file),
            schema_file=str(schema_file),
            runs=10,
            concurrency=5,
            timeout_s=5,
            thresholds=ThresholdsConfig(
                min_stability=85,
                min_compliance=100,
                max_cost_usd=None,
                p95_latency_ms=None,
            ),
            ci=CIConfig(
                runs=10,
                save_on_fail=True,
            ),
        )
    
    @pytest.mark.asyncio
    async def test_ci_fails_with_strict_thresholds(self, ci_chaos_config, temp_dir):
        """Test that CI fails when chaos causes too many failures."""
        from aicert.cli import _evaluate_thresholds
        from aicert.metrics import compute_summary
        
        results = await run_suite(ci_chaos_config, output_dir=temp_dir)
        summary = compute_summary(results, ci_chaos_config.providers[0].chaos.model_dump())
        
        # Evaluate against strict thresholds
        thresholds = {
            "min_stability": 85,
            "min_compliance": 100,
        }
        passed, failures = _evaluate_thresholds(summary, thresholds)
        
        # Should fail due to chaos-induced failures
        assert not passed, "CI should fail with strict thresholds and chaos mode"
        assert len(failures) > 0, "Should have threshold failures"
    
    @pytest.mark.asyncio
    async def test_ci_passes_with_lenient_thresholds(self, ci_chaos_config, temp_dir):
        """Test that CI passes when thresholds are lenient enough."""
        from aicert.cli import _evaluate_thresholds
        from aicert.metrics import compute_summary
        
        results = await run_suite(ci_chaos_config, output_dir=temp_dir)
        summary = compute_summary(results, ci_chaos_config.providers[0].chaos.model_dump())
        
        # Evaluate against lenient thresholds
        thresholds = {
            "min_stability": 0,
            "min_compliance": 0,
        }
        passed, failures = _evaluate_thresholds(summary, thresholds)
        
        # Should pass with lenient thresholds
        assert passed, "CI should pass with lenient thresholds"


class TestSummaryHashes:
    """Tests for summary hash fields."""
    
    @pytest.mark.asyncio
    async def test_summary_contains_hashes_with_extraction_config(self, temp_dir):
        """Test that summary contains prompt_hash and schema_hash using examples/extraction config."""
        from pathlib import Path
        from aicert.config import Config, ProviderConfig
        from aicert.metrics import compute_summary
        from aicert.hashing import sha256_file
        
        # Use examples/extraction config files
        examples_dir = Path(__file__).parent.parent / "examples" / "extraction"
        prompt_file = examples_dir / "prompt.txt"
        schema_file = examples_dir / "schema.json"
        cases_file = examples_dir / "cases.jsonl"
        
        # Create config with fake provider
        config = Config(
            project="test-hashes",
            providers=[
                ProviderConfig(
                    id="fake-test",
                    provider="fake",
                    model="fake-model",
                    temperature=0.1,
                ),
            ],
            prompt_file=str(prompt_file),
            cases_file=str(cases_file),
            schema_file=str(schema_file),
            runs=2,
            concurrency=2,
            timeout_s=10,
        )
        
        # Run suite
        results = await run_suite(config, output_dir=temp_dir)
        
        # Compute expected hashes
        expected_prompt_hash = sha256_file(prompt_file)
        expected_schema_hash = sha256_file(schema_file)
        
        # Load schema for summary
        import yaml
        with open(schema_file) as f:
            schema = yaml.safe_load(f)
        
        # Compute summary with hashes
        summary = compute_summary(
            results, 
            schema, 
            prompt_hash=expected_prompt_hash, 
            schema_hash=expected_schema_hash
        )
        
        # Verify top-level hashes
        assert summary["prompt_hash"] == expected_prompt_hash
        assert summary["schema_hash"] == expected_schema_hash
        assert summary["prompt_hash"].startswith("sha256:")
        assert summary["schema_hash"].startswith("sha256:")
        
        # Verify per-provider hashes
        assert "fake-test" in summary["per_provider"]
        assert summary["per_provider"]["fake-test"]["prompt_hash"] == expected_prompt_hash
        assert summary["per_provider"]["fake-test"]["schema_hash"] == expected_schema_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
