"""Async runner utilities for aicert."""

import asyncio
import json
import random
import time
from typing import Any, Dict, List, Optional

from aicert.artifacts import append_result, create_run_dir
from aicert.config import Config, ProviderConfig, ChaosConfig
from aicert.providers.base import BaseProvider
from aicert.templating import build_schema_hint, render_prompt
from aicert.validation import validate_output


class RetriableError(Exception):
    """Exception for retriable errors (429, 5xx, etc.)."""
    pass


class ProviderError(Exception):
    """Exception for provider errors (429, 500, etc.)."""
    
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Provider error {status_code}: {message}")


class FakeAdapter(BaseProvider):
    """Fake adapter for testing the runner end-to-end.
    
    Returns deterministic JSON output based on prompt content.
    By default, produces stable output with no errors for testing.
    When chaos mode is enabled (via chaos config or AICERT_FAKE_CHAOS env var),
    simulates various failure modes including invalid JSON, schema drift,
    timeouts, and HTTP errors.
    """
    
    def __init__(
        self,
        model: str = "fake-model",
        error_rate: float = 0.0,
        latency_ms: int = 10,
        seed: Optional[int] = None,
        chaos: Optional[ChaosConfig] = None,
    ):
        super().__init__(model=model)
        self.error_rate = error_rate
        self.latency_ms = latency_ms
        self.call_count = 0
        
        # Chaos mode: enabled via config or environment variable
        self.chaos_enabled = chaos is not None
        self.chaos = chaos or ChaosConfig()
        
        # Set random seed for reproducibility if provided
        if seed is not None:
            random.seed(seed)
        elif self.chaos_enabled:
            # Use chaos config seed for reproducible chaos
            random.seed(self.chaos.seed)
    
    def _generate_base_response(self, prompt: str) -> Dict[str, Any]:
        """Generate the base deterministic response based on prompt content."""
        # Generate deterministic output based on prompt
        # These mappings ensure stable output for testing
        if "2 + 2" in prompt or "What is 2 + 2" in prompt:
            answer = "4"
            greeting = "Hello!"
        elif "capital of France" in prompt:
            answer = "Paris"
            greeting = "Hi there!"
        elif "How many planets" in prompt:
            answer = "8"
            greeting = "Greetings!"
        else:
            answer = "test answer"
            greeting = "Hello!"
        
        confidence = 0.95
        
        return {
            "greeting": greeting,
            "answer": answer,
            "confidence": confidence,
        }
    
    def _apply_chaos(self, prompt: str, base_response: Dict[str, Any]) -> tuple[str, Optional[Exception]]:
        """Apply chaos transformations to the response.
        
        Returns:
            Tuple of (content, exception) where exception is not None if an error should be raised
        """
        chaos = self.chaos
        
        # Roll for timeout (raises asyncio.TimeoutError)
        if random.random() < chaos.p_timeout:
            return "", asyncio.TimeoutError("Chaos timeout")
        
        # Roll for HTTP 429
        if random.random() < chaos.p_http_429:
            return "", ProviderError(429, "Rate limited - chaos mode")
        
        # Roll for HTTP 500
        if random.random() < chaos.p_http_500:
            return "", ProviderError(500, "Internal server error - chaos mode")
        
        # Roll for non-JSON response
        if random.random() < chaos.p_non_json:
            return "This is just plain text, not JSON at all!", None
        
        # Roll for wrapped JSON (markdown fence with json language)
        if random.random() < chaos.p_wrapped_json:
            json_str = json.dumps(base_response)
            return f"```json\n{json_str}\n```\n\nHere is your response!", None
        
        # Roll for extra keys (valid JSON but with extra fields)
        if random.random() < chaos.p_extra_keys:
            response = base_response.copy()
            response["extra_field_1"] = "should not be here"
            response["extra_field_2"] = 12345
            return json.dumps(response), None
        
        # Roll for wrong schema (missing required fields or wrong types)
        if random.random() < chaos.p_wrong_schema:
            # Create a response missing required fields
            wrong_response = {
                "greeting": "Hi",
                # Missing 'answer' field
                # 'confidence' is string instead of number
                "confidence": "high",
            }
            return json.dumps(wrong_response), None
        
        # Roll for invalid JSON
        if random.random() < chaos.p_invalid_json:
            valid_json = json.dumps(base_response)
            # Truncate to make it invalid JSON
            truncated = valid_json[:-10] if len(valid_json) > 10 else "{"
            return truncated, None
        
        # Return valid JSON (normal case)
        return json.dumps(base_response), None
    
    async def generate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate a fake response with optional chaos mode."""
        self.call_count += 1
        
        # Calculate latency: simulate realistic distribution (100-2000ms) if chaos enabled
        if self.chaos_enabled:
            # Use uniform distribution in range, or exponential for more realism
            latency = random.uniform(100, 2000) / 1000.0  # Convert to seconds
        else:
            latency = self.latency_ms / 1000.0
        
        await asyncio.sleep(latency)
        
        # Simulate occasional retriable errors in normal mode (only if error_rate > 0)
        if not self.chaos_enabled and self.error_rate > 0 and random.random() < self.error_rate:
            error_type = random.choice([429, 500, 502, 503])
            raise RetriableError(f"Simulated error {error_type}")
        
        # Generate base response
        base_response = self._generate_base_response(prompt)
        
        # Apply chaos if enabled
        if self.chaos_enabled:
            content, exception = self._apply_chaos(prompt, base_response)
            
            # Raise exception if chaos generated one
            if exception is not None:
                raise exception
        else:
            content = json.dumps(base_response)
        
        return {
            "choices": [
                {
                    "message": {
                        "content": content
                    }
                }
            ],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": 50,
            }
        }
    
    async def generate_stream(self, prompt: str, **kwargs):
        """Streaming not supported for FakeAdapter."""
        raise NotImplementedError("Streaming not supported for FakeAdapter")
    
    @property
    def provider_type(self) -> str:
        return "fake"


def create_provider_adapter(config: ProviderConfig) -> BaseProvider:
    """Create a provider adapter from config.
    
    Args:
        config: Provider configuration.
        
    Returns:
        Initialized provider adapter.
    """
    from aicert.providers import OpenAIProvider, AnthropicProvider, OpenAICompatibleProvider
    
    provider_map = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "openai_compatible": OpenAICompatibleProvider,
    }
    
    provider_class = provider_map.get(config.provider)
    if provider_class is None:
        raise ValueError(f"Unknown provider type: {config.provider}")
    
    return provider_class(
        model=config.model,
        api_key=None,  # Will be loaded from environment
        base_url=config.base_url,
        temperature=config.temperature,
    )


async def run_single_with_retry(
    adapter: BaseProvider,
    prompt: str,
    timeout_s: int,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Run a single prompt with timeout and retries.
    
    Args:
        adapter: Provider adapter.
        prompt: The prompt to send.
        timeout_s: Timeout in seconds.
        max_retries: Maximum retry attempts.
        
    Returns:
        Response dict with timing and result info.
        
    Raises:
        RetriableError: After exhausting retries.
    """
    base_delay = 0.5  # seconds
    
    for attempt in range(max_retries + 1):
        try:
            start_time = time.perf_counter()
            response = await asyncio.wait_for(
                adapter.generate(prompt),
                timeout=timeout_s
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            # Extract content and token usage
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = response.get("usage", {})
            
            return {
                "ok": True,
                "content": content,
                "latency_ms": latency_ms,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "error": None,
                "attempt": attempt,
            }
        except asyncio.TimeoutError:
            elapsed = time.perf_counter() - start_time
            if attempt < max_retries:
                # Exponential backoff with jitter
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                continue
            else:
                return {
                    "ok": False,
                    "content": "",
                    "latency_ms": elapsed * 1000,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "error": f"Timeout after {timeout_s}s",
                    "attempt": attempt,
                }
        except ProviderError as e:
            # Handle provider errors (429, 500, etc.) - these are retriable
            if attempt < max_retries:
                # Exponential backoff with jitter
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                continue
            else:
                return {
                    "ok": False,
                    "content": "",
                    "latency_ms": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "error": str(e),
                    "attempt": attempt,
                }
        except RetriableError as e:
            if attempt < max_retries:
                # Exponential backoff with jitter
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
                continue
            else:
                return {
                    "ok": False,
                    "content": "",
                    "latency_ms": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "error": str(e),
                    "attempt": attempt,
                }
        except Exception as e:
            # Non-retriable error
            return {
                "ok": False,
                "content": "",
                "latency_ms": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "error": str(e),
                "attempt": attempt,
            }
    
    # Should not reach here
    return {
        "ok": False,
        "content": "",
        "latency_ms": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "error": "Max retries exceeded",
        "attempt": max_retries,
    }


async def execute_case(
    adapter: BaseProvider,
    case: Dict[str, Any],
    case_id: str,
    schema: Dict[str, Any],
    schema_hint: str,
    config: Config,
    run_index: int,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """Execute a single test case with concurrency control.
    
    Args:
        adapter: Provider adapter.
        case: Test case dict.
        case_id: Unique case identifier.
        schema: JSON schema for validation.
        schema_hint: Compact schema hint string.
        config: Main config.
        run_index: Index of this run (0-based).
        semaphore: Concurrency semaphore.
        
    Returns:
        Result dict for this execution.
    """
    async with semaphore:
        # Render prompt
        prompt_template = case.get("prompt", "")
        variables = case.get("variables", {})
        
        try:
            rendered_prompt = render_prompt(
                template=prompt_template,
                case=variables,
                schema_hint=schema_hint,
                case_id=case_id,
            )
        except Exception as e:
            return {
                "provider_id": adapter.model,
                "case_id": case_id,
                "run_index": run_index,
                "ok_json": False,
                "ok_schema": False,
                "extra_keys": [],
                "output_json": None,
                "latency_ms": 0,
                "cost_usd": 0,
                "error": f"Prompt rendering error: {str(e)}",
            }
        
        # Call adapter with timeout and retries
        result = await run_single_with_retry(
            adapter=adapter,
            prompt=rendered_prompt,
            timeout_s=config.timeout_s,
            max_retries=3,
        )
        
        if not result["ok"]:
            return {
                "provider_id": adapter.model,
                "case_id": case_id,
                "run_index": run_index,
                "ok_json": False,
                "ok_schema": False,
                "extra_keys": [],
                "output_json": None,
                "latency_ms": result.get("latency_ms", 0),
                "cost_usd": 0,
                "error": result.get("error", "Unknown error"),
            }
        
        # Validate output
        validation_result = validate_output(
            text=result["content"],
            schema=schema,
            extract_json=config.validation.extract_json,
            allow_extra_keys=config.validation.allow_extra_keys,
        )
        
        # Calculate cost (simplified - based on tokens)
        cost_usd = estimate_cost(
            prompt_tokens=result.get("prompt_tokens", 0),
            completion_tokens=result.get("completion_tokens", 0),
            model=adapter.model,
        )
        
        return {
            "provider_id": adapter.model,
            "case_id": case_id,
            "run_index": run_index,
            "ok_json": validation_result.ok_json,
            "ok_schema": validation_result.ok_schema,
            "extra_keys": validation_result.extra_keys,
            "output_json": validation_result.parsed,
            "latency_ms": result["latency_ms"],
            "cost_usd": cost_usd,
            "error": validation_result.error,
        }


def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """Estimate cost in USD based on token counts.
    
    This is a simplified estimator. In production, you'd use
    actual provider pricing.
    """
    # Simplified pricing (placeholder values)
    pricing = {
        "gpt-4": {"prompt": 0.00003, "completion": 0.00006},
        "gpt-4o": {"prompt": 0.000005, "completion": 0.000015},
        "gpt-3.5-turbo": {"prompt": 0.0000015, "completion": 0.000002},
        "claude-3-opus-20240229": {"prompt": 0.000015, "completion": 0.000075},
        "claude-3-sonnet-20240229": {"prompt": 0.000003, "completion": 0.000015},
        "fake-model": {"prompt": 0.0, "completion": 0.0},
    }
    
    # Try exact match first, then fall back to basic estimates
    if model in pricing:
        rates = pricing[model]
    elif "gpt-4" in model:
        rates = pricing["gpt-4"]
    elif "claude" in model:
        rates = pricing["claude-3-sonnet-20240229"]
    else:
        # Default to zero cost for unknown models
        rates = {"prompt": 0.0, "completion": 0.0}
    
    return (prompt_tokens * rates["prompt"]) + (completion_tokens * rates["completion"])


async def run_provider_cases(
    adapter: BaseProvider,
    cases: List[Dict[str, Any]],
    schema: Dict[str, Any],
    schema_hint: str,
    config: Config,
) -> List[Dict[str, Any]]:
    """Run all cases for a single provider.
    
    Args:
        adapter: Provider adapter.
        cases: List of test cases.
        schema: JSON schema for validation.
        schema_hint: Compact schema hint string.
        config: Main config.
        
    Returns:
        List of result dicts.
    """
    results = []
    semaphore = asyncio.Semaphore(config.concurrency)
    
    # Create tasks for all runs
    tasks = []
    for case in cases:
        case_id = case.get("name", case.get("id", str(cases.index(case))))
        for run_idx in range(config.runs):
            task = execute_case(
                adapter=adapter,
                case=case,
                case_id=case_id,
                schema=schema,
                schema_hint=schema_hint,
                config=config,
                run_index=run_idx,
                semaphore=semaphore,
            )
            tasks.append(task)
    
    # Execute all tasks concurrently
    results = await asyncio.gather(*tasks)
    
    return results


def load_cases(cases_file: str) -> List[Dict[str, Any]]:
    """Load test cases from JSONL file.
    
    Args:
        cases_file: Path to JSONL file.
        
    Returns:
        List of case dicts.
    """
    cases = []
    with open(cases_file, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def load_schema(schema_file: str) -> Dict[str, Any]:
    """Load JSON schema from file.
    
    Args:
        schema_file: Path to schema file.
        
    Returns:
        Schema dict.
    """
    import yaml
    with open(schema_file, "r") as f:
        return yaml.safe_load(f)


async def run_suite(config: Config, output_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Run the test suite for all providers and cases.
    
    Args:
        config: Aicert configuration.
        output_dir: Optional output directory for results.
        
    Returns:
        List of all execution result dicts.
    """
    from pathlib import Path
    
    # Create run directory
    run_dir = create_run_dir(output_dir)
    
    # Resolve paths relative to config file location if possible
    config_path = getattr(config, '_config_path', None)
    if config_path:
        config_dir = Path(config_path).parent
    else:
        config_dir = Path.cwd()
    
    # Load cases and schema (resolve relative to config directory)
    cases_file = config_dir / config.cases_file if not Path(config.cases_file).is_absolute() else config.cases_file
    schema_file = config_dir / config.schema_file if not Path(config.schema_file).is_absolute() else config.schema_file
    
    cases = load_cases(str(cases_file))
    schema = load_schema(str(schema_file))
    schema_hint = build_schema_hint(schema)
    
    all_results = []
    
    # Run each provider
    for provider_config in config.providers:
        # Create adapter (use FakeAdapter if specified, otherwise real adapter)
        if provider_config.provider == "fake":
            # Pass chaos config if available
            adapter = FakeAdapter(
                model=provider_config.id,
                chaos=provider_config.chaos,
            )
        else:
            adapter = create_provider_adapter(provider_config)
        
        try:
            # Run all cases for this provider
            provider_results = await run_provider_cases(
                adapter=adapter,
                cases=cases,
                schema=schema,
                schema_hint=schema_hint,
                config=config,
            )
        finally:
            # Close the adapter if it has a close method
            if hasattr(adapter, 'close'):
                await adapter.close()
        
        # Append results to artifacts
        for result in provider_results:
            append_result(run_dir, result)
        
        all_results.extend(provider_results)
    
    return all_results
