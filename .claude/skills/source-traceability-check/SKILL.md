---
name: source-traceability-check
description: Validate claim-source traceability before final output.
---

# Source Traceability Check

Use this skill before finalizing conclusions.

## Checks

1. Every key claim has at least one URL.
2. URL is accessible and relevant.
3. Claim does not overstate what source supports.
4. Conflicts are explicitly disclosed.

## Output

## Traceability Matrix
- claim: [text]
  - url: [https://...]
  - status: [pass|warn|fail]
  - note: [reason]
