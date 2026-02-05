# Changelog

## v0.1.0-beta (2026-02-04)

### Initial Private Beta Release

This release introduces aicert, a CI tool for LLM JSON outputs.

### Commands Supported

- `aicert run` - Execute test cases once
- `aicert stability` - Run stability tests across multiple iterations
- `aicert compare` - Compare multiple providers side-by-side
- `aicert ci` - CI mode with threshold-based pass/fail gates
- `aicert doctor` - Validate configuration files

### Key Features

- **JSON-Only Enforcement** - All LLM outputs are validated for valid JSON format with strict schema compliance
- **Chaos Mode** - Test determinism by introducing controlled variance in outputs
- **CI Integration** - GitHub Actions support with threshold checking, artifact saving, and proper exit codes
- **JSON Output Format** - Machine-readable results for programmatic processing
- **Example Packs** - Ready-to-run examples demonstrating:
  - Basic stability testing
  - Chaos/determinism testing
  - Information extraction workflows
  - RAG citation verification

### Provider Support

- OpenAI (GPT-4, GPT-3.5-turbo, etc.)
- Anthropic (Claude Sonnet, Claude Haiku, etc.)
- OpenAI-compatible endpoints (local models, Azure, etc.)
- Fake adapter for testing without API keys

### Metrics Tracked

- Compliance percentage (schema validity)
- Stability percentage (output consistency)
- Latency (P50/P95)
- Cost estimation
- Semantic/structural similarity

### Exit Codes

- `0` - All checks passed
- `1` - Runtime error
- `2` - Threshold check failed (CI mode)
- `3` - Config/schema error
- `4` - Provider/auth error
