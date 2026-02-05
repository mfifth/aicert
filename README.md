# aicert

CI for LLM JSON outputs - Validate, test, and measure LLM outputs for stability and compliance.

## Quickstart (No API keys required)

```bash
# Validate config
aicert doctor examples/fake_chaos/aicert.yaml

# Run stability tests with chaotic output (tests determinism)
aicert stability examples/fake_chaos/aicert.yaml

# Run stability tests with extraction example
aicert stability examples/extraction/aicert.yaml
```

## What it measures

- **Compliance** - % of outputs matching JSON schema
- **Stability** - % of identical outputs across runs
- **Latency** - P50/P95 response times
- **Similarity** - Semantic/structural similarity of outputs
- **CI gating** - Threshold-based pass/fail for automation

## Installation

```bash
pip install -e .
```

## Quickstart

### 1. Run the example with FakeAdapter (no API key needed)

```bash
aicert stability examples/aicert.yaml
```

This runs stability tests using the built-in fake adapter that produces deterministic JSON output.

### 2. Run with real providers

Set your API key and run:

```bash
export OPENAI_API_KEY="your-api-key"
aicert stability examples/aicert.yaml -p openai
```

## Configuration

Create a `aicert.yaml` file in your project:

```yaml
# Project name
project: my-project

# Providers to test
providers:
  - id: openai-gpt4
    provider: openai
    model: gpt-4
    temperature: 0.1
  - id: anthropic-claude
    provider: anthropic
    model: claude-sonnet-4-20250514
    temperature: 0.1

# Files
prompt_file: prompt.txt
cases_file: cases.jsonl
schema_file: schema.json

# Test settings
runs: 50          # Number of runs per test case
concurrency: 10   # Concurrent requests
timeout_s: 30    # Request timeout

# Validation settings
validation:
  extract_json: true     # Try to extract JSON from ```json blocks
  allow_extra_keys: false # Fail on extra keys not in schema

# Threshold checks (for CI mode)
thresholds:
  min_stability: 85      # Minimum stability percentage
  min_compliance: 95     # Minimum schema compliance percentage
  max_cost_usd: 5.00    # Maximum cost in USD
  p95_latency_ms: 5000  # P95 latency threshold

# CI mode settings
ci:
  runs: 10              # Runs per case in CI mode
  save_on_fail: true   # Save artifacts on failure
```

### Config Fields

| Field | Required | Description |
|-------|----------|-------------|
| `project` | Yes | Project name for reporting |
| `providers` | Yes | List of provider configurations |
| `prompt_file` | Yes | Path to prompt template file |
| `cases_file` | Yes | Path to test cases (JSONL format) |
| `schema_file` | Yes | Path to JSON schema file |
| `runs` | No | Test runs per case (default: 50) |
| `concurrency` | No | Concurrent requests (default: 10) |
| `timeout_s` | No | Request timeout in seconds (default: 30) |
| `validation.extract_json` | No | Extract JSON from blocks (default: true) |
| `validation.allow_extra_keys` | No | Allow extra keys (default: false) |
| `thresholds.*` | No | Optional threshold values |
| `ci.runs` | No | CI mode runs (default: 10) |
| `ci.save_on_fail` | No | Save artifacts on failure (default: true) |

### Provider Configuration

```yaml
providers:
  # OpenAI
  - id: openai-gpt4
    provider: openai
    model: gpt-4
    temperature: 0.1

  # Anthropic
  - id: anthropic-claude
    provider: anthropic
    model: claude-sonnet-4-20250514
    temperature: 0.1

  # OpenAI-compatible (e.g., local models, Azure)
  - id: local-llama
    provider: openai_compatible
    model: llama-3.1-8b
    base_url: http://localhost:8000/v1
    temperature: 0.1

  # Fake adapter for testing
  - id: fake-test
    provider: fake
    model: fake-model
    temperature: 0.1
```

### Environment Variables

```bash
OPENAI_API_KEY      # OpenAI API key
ANTHROPIC_API_KEY   # Anthropic API key
```

## Prompt Templates

Prompts support variable substitution using `$variable` or `${variable}` syntax:

```text
You are a helpful assistant. Respond to this question: $question

Context: $context
```

## Test Cases (JSONL Format)

Each line is a JSON object with test case data:

```jsonl
{"name": "test_math", "prompt": "What is 2 + 2?", "variables": {"question": "What is 2 + 2?"}}
{"name": "test_capitals", "prompt": "What is the capital of France?", "variables": {"question": "What is the capital of France?"}}
```

Fields:
- `name`: Test case identifier
- `prompt`: Template string (variables will be substituted)
- `variables`: Dict of variables for substitution

## JSON Schema

Validate outputs against a JSON Schema:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "answer": {
      "type": "string",
      "description": "The answer to the question"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    }
  },
  "required": ["answer", "confidence"],
  "additionalProperties": false
}
```

## Example Commands

### Run test cases once

```bash
aicert run examples/aicert.yaml
```

### Run stability tests

```bash
aicert stability examples/aicert.yaml
```

### Compare providers

```bash
aicert compare examples/aicert.yaml
```

### CI mode with threshold checking

```bash
aicert ci examples/aicert.yaml
```

### Override settings

```bash
# Override provider
aicert stability examples/aicert.yaml -p fake

# Override concurrency
aicert stability examples/aicert.yaml --concurrency 5

# Disable JSON extraction
aicert stability examples/aicert.yaml --no-extract-json
```

### Save artifacts to specific directory

```bash
aicert stability examples/aicert.yaml -o ./results
```

## Baselines

Baselines allow you to track performance metrics over time and detect regressions. Save a baseline when your tests are performing well, then compare future runs against it.

### Recommended: Commit baselines to version control

For best results, commit your baseline files to your repository. This allows you to:
- Track performance trends over commits
- Detect regressions in pull requests
- Maintain baselines alongside your code

We recommend using a dedicated directory like `aicert_baselines/` (not `.aicert/`) for committed baselines:

```bash
# Save a baseline to the aicert_baselines/ directory
aicert baseline save examples/aicert.yaml --baseline-dir ./aicert_baselines

# Check against baseline
aicert baseline check examples/aicert.yaml --baseline-dir ./aicert_baselines
```

### Baseline Commands

#### Save a baseline from a run

```bash
# Save baseline from a previous run directory
aicert baseline from-run ./run_abc123 --baseline-dir ./aicert_baselines

# Run and save baseline in one command
aicert baseline save examples/aicert.yaml --baseline-dir ./aicert_baselines
```

#### Check against baseline

```bash
# Run CI evaluation and check against baseline
aicert baseline check examples/aicert.yaml --baseline-dir ./aicert_baselines

# Check existing run directory against baseline
aicert baseline check --from-run ./run_abc123 --baseline-dir ./aicert_baselines
```

### Baseline Directory Structure

When using `--baseline-dir`, baselines are saved as `<baseline-dir>/<project>.json`:

```
./
├── aicert.yaml
├── aicert_baselines/
│   ├── my-project.json    # Baseline for my-project
│   └── another-project.json
└── ...
```

## GitHub Actions Example

```yaml
name: LLM Stability Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  aicert:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -e .
      
      - name: Run stability tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: aicert ci examples/aicert.yaml
        id: aicert
      
      - name: Upload artifacts on failure
        if: failure() && steps.aicert.outcome == 'failure'
        uses: actions/upload-artifact@v4
        with:
          name: aicert-results
          path: .aicert/
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Runtime error |
| 2 | Threshold check failed (CI mode) |
| 3 | Config/schema error |
| 4 | Provider/auth error |

## Features

- **Template-based prompts** - Use variables in your prompts
- **JSON Schema validation** - Validate LLM outputs against schemas
- **Multiple providers** - Support for OpenAI, Anthropic, and OpenAI-compatible endpoints
- **Metrics and reporting** - Track stability, compliance, latency, and cost
- **Async execution** - Efficiently run multiple test cases concurrently
- **CI integration** - Threshold-based pass/fail with artifact saving

## License

MIT

---

## Beta Access

**aicert is currently in private beta.**

During this phase:
- You bring your own provider API keys (OpenAI, Anthropic, or OpenAI-compatible endpoints)
- No subscription or payment is required
- Access is invitation-only via private GitHub repository

### Request Access

To request access to the private beta, please contact: **support@example.com**

### Installation

Once granted access, install from the private repository:

```bash
pip install git+https://github.com/<org>/<repo>.git@v0.1.0-beta
```

See [BETA.md](BETA.md) for full beta documentation.
