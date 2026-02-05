# Structured Extraction Example

This example demonstrates structured extraction using aicert with the fake provider.

## Running Stability Tests

```bash
aicert stability examples/extraction/aicert.yaml
```

## Running in CI Mode

```bash
aicert ci examples/extraction/aicert.yaml --format text
```

## Overview

This example extracts structured data from user inputs with:
- **Intent classification**: refund, bug, account, billing, other
- **Confidence score**: 0-1 scale
- **Reasoning**: Explanation for the classification
