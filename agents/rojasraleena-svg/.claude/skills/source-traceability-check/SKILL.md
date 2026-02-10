---
name: source-traceability-check
description: Validate whether each key claim is backed by an accessible and relevant source URL.
---

# Source Traceability Check

用于发布前的来源核查。

## 检查清单

1. 每条关键结论是否有 URL。
2. URL 是否可访问。
3. URL 内容是否支持对应结论。
4. 是否存在“结论强于证据”的情况。

## 输出格式

## Traceability Matrix
- claim: [关键结论]
  - url: [来源链接]
  - status: [pass|warn|fail]
  - note: [说明]

## Blockers
- [必须修复的问题]
