# aicert Private Beta

aicert is a CI tool for LLM JSON outputs that validates, tests, and measures LLM outputs for stability and compliance. It helps you ensure your LLM applications produce consistent, schema-compliant JSON responses across multiple runs and providers.

## What's Included in v0.1.0-beta

- **Stability testing** - Run multiple iterations of test cases to measure output consistency
- **Provider comparison** - Compare multiple LLM providers side-by-side
- **JSON Schema validation** - Validate all outputs against your defined JSON schema
- **CI/CD integration** - Threshold-based pass/fail gates for automated workflows
- **Template-based prompts** - Variable substitution for flexible test case definitions
- **Multiple provider support** - OpenAI, Anthropic, and OpenAI-compatible endpoints
- **Example packs** - Ready-to-use examples for common use cases (extraction, RAG citations, chaos testing)

## What's NOT Included Yet

- **Drift detection** - Alerting when outputs change over time
- **Dashboard** - Web UI for viewing results and trends
- **Historical tracking** - Storing and comparing results across versions
- **Custom metrics** - User-defined evaluation metrics
- **Team collaboration** - Shared workspaces and result sharing
- **Scheduled runs** - Automated periodic testing

## Installation

Install from the private GitHub repository:

```bash
pip install git+https://github.com/<org>/<repo>.git@v0.1.0-beta
```

## Required Environment Variables

Configure the appropriate provider API keys:

```bash
# OpenAI
export OPENAI_API_KEY="your-api-key"

# Anthropic
export ANTHROPIC_API_KEY="your-api-key"
```

## Support

For access requests or issues, contact: **support@example.com**
