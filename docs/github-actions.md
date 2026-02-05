# GitHub Actions Integration

You can integrate aicert into your CI/CD pipeline using GitHub Actions. This page provides an example workflow and guidance on setting up continuous integration for your AI certifier tests.

## Example Workflow

Copy the following workflow file to `.github/workflows/aicert.yml`:

```yaml
name: aicert CI

on:
  pull_request:
    paths:
      - '**.yaml'
      - '**.txt'
      - '**.jsonl'
      - 'pyproject.toml'

jobs:
  aicert:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -e .

      - name: Run tests
        run: python -m pytest

      - name: Run aicert CI
        run: aicert ci examples/fake_chaos/aicert.yaml
```

## Configuration

### Triggering on Pull Requests

The example workflow triggers on pull requests that modify:
- YAML configuration files (`**.yaml`)
- Prompt files (`**.txt`)
- Test case files (`**.jsonl`)
- Project dependencies (`pyproject.toml`)

Adjust the `paths` filter as needed for your project structure.

### Using Real LLM Providers

The example uses the `fake` provider, which simulates AI responses without requiring API keys. To use real providers, set the appropriate secrets in your GitHub repository:

1. Go to your repository settings → Secrets and variables → Actions
2. Add the following secrets:
   - `OPENAI_API_KEY` - For OpenAI models
   - `ANTHROPIC_API_KEY` - For Anthropic models

Then update your aicert configuration file to use a real provider:

```yaml
providers:
  - id: openai-gpt4
    provider: openai
    model: gpt-4
    temperature: 0.1
```

## CI Mode

The `aicert ci` command runs your tests in CI mode, which:
- Executes a fixed number of runs
- Validates against configured thresholds
- Fails the workflow if stability or compliance falls below thresholds
- Saves artifacts on failure for debugging

## Best Practices

- **Run on PRs**: Test AI behavior before merging to catch regressions early
- **Limit triggers**: Use path filters to avoid unnecessary runs
- **Cache dependencies**: Consider caching pip dependencies for faster builds
