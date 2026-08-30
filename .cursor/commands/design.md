---
name: /design
description: 记录满足已冻结规格所需的当前有效架构决定
---

先执行 `python3 quwoquan_ops/cli/workflow_host_adapter.py --schema-version 1 --host cursor --adapter cursor-command-shell --canonical-command /design --manifest-ref <repo-relative-manifest.json> --expected-target <target> [--expected-scope <scope>]`。
仅当输出 `result=selected`、`next_segment=PRE` 且 verification valid 后，按输出的 `.agents/skills/design/SKILL.md` 执行；否则按 typed recovery 停止。
