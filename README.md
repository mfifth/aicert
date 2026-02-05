# aicert

**CI for structured LLM outputs.**

Validate, test, and measure JSON outputs from LLMs for stability, compliance, and latency.

---

## Why aicert?

LLMs are non-deterministic.

If you rely on structured JSON outputs, you need to know:

* Do they consistently match your schema?
* Are they stable across repeated runs?
* Are latency and cost within bounds?
* Will a model or prompt change break production?

`aicert` gives you automated answers — locally and in CI.

---

## Installation

```bash
pip install aicert
```

For development:

```bash
pip install -e .
```

---

## Quickstart (No API Keys Required)

Run with the built-in fake adapter:

```bash
aicert doctor examples/fake_chaos/aicert.yaml
aicert stability examples/fake_chaos/aicert.yaml
```

Or run the extraction example:

```bash
aicert stability examples/extraction/aicert.yaml
```

---

## What It Measures

* **Compliance** — % of outputs matching JSON Schema
* **Stability** — % of identical outputs across repeated runs
* **Latency** — P50 / P95 response times
* **Similarity** — Structural or semantic output similarity
* **CI Gating** — Threshold-based pass/fail automation

---

## Basic Workflow

### 1. Create `aicert.yaml`

```yaml
project: my-project

providers:
  - id: openai-gpt4
    provider: openai
    model: gpt-4
    temperature: 0.1

prompt_file: prompt.txt
cases_file: cases.jsonl
schema_file: schema.json

runs: 50
concurrency: 10
timeout_s: 30

validation:
  extract_json: true
  allow_extra_keys: false

thresholds:
  min_stability: 85
  min_compliance: 95
  p95_latency_ms: 5000

ci:
  runs: 10
  save_on_fail: true
```

---

### 2. Run Stability Tests

```bash
aicert stability aicert.yaml
```

---

### 3. Run in CI Mode

```bash
aicert ci aicert.yaml
```

This exits non-zero if thresholds fail.

---

## Provider Configuration

```yaml
providers:
  - id: openai
    provider: openai
    model: gpt-4
    temperature: 0.1

  - id: anthropic
    provider: anthropic
    model: claude-sonnet-4-20250514
    temperature: 0.1

  - id: local
    provider: openai_compatible
    model: llama-3.1-8b
    base_url: http://localhost:8000/v1
    temperature: 0.1

  - id: fake
    provider: fake
    model: fake-model
```

---

## Commands

```bash
aicert init
aicert doctor aicert.yaml
aicert run aicert.yaml
aicert stability aicert.yaml
aicert compare aicert.yaml
aicert ci aicert.yaml
aicert diff <run_a> <run_b>
aicert report <run_dir>
```

---

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
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - run: pip install aicert
      
      - run: aicert ci aicert.yaml
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

---

## JSON Schema Validation

`aicert` validates outputs against your JSON Schema:

```json
{
  "type": "object",
  "properties": {
    "answer": { "type": "string" },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
  },
  "required": ["answer", "confidence"],
  "additionalProperties": false
}
```

---

## Aicert Pro

Aicert Pro adds baseline regression enforcement for CI:

- Save and commit baselines
- Detect stability/compliance regressions
- Prompt and schema drift detection
- Cost regression protection

### Pricing

- $29 / month
- $290 / year (2 months free)

Purchase: https://yourdomain.com

---

## Exit Codes

| Code | Meaning                     |
| ---- | --------------------------- |
| 0    | Success                     |
| 2    | Threshold failure (CI mode) |
| 3    | Config/schema error         |
| 4    | Provider/auth error         |

---

## License

MIT