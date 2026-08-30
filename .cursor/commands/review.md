---
name: /review
description: 先执行去重命名 evidence，再有界派发主审与唯一专审
---

先执行 `python3 quwoquan_ops/cli/workflow_host_adapter.py --schema-version 1 --host cursor --adapter cursor-command-shell --canonical-command /review --manifest-ref <repo-relative-manifest.json> --expected-target <target> [--expected-scope <scope>]`。
仅当输出 `result=selected`、`next_segment=PRE` 且 verification valid 后，按输出的 `.agents/skills/review/SKILL.md` 执行；否则按 typed recovery 停止。
