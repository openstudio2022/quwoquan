---
name: /commit
description: 提交已通过评审的增量并复核门禁与工作树状态
---

先执行 `python3 quwoquan_ops/cli/workflow_host_adapter.py --schema-version 1 --host cursor --adapter cursor-command-shell --canonical-command /commit --manifest-ref <repo-relative-manifest.json> --expected-target <target> [--expected-scope <scope>]`。
仅当输出 `result=selected`、`next_segment=PRE` 且 verification valid 后，按输出的 `.agents/skills/commit/SKILL.md` 执行；否则按 typed recovery 停止。
