---
name: /dev
description: 实现已冻结的 Story、能力或对象级扩展并闭环验证
---

先执行 `python3 quwoquan_ops/cli/workflow_host_adapter.py --schema-version 1 --host cursor --adapter cursor-command-shell --canonical-command /dev --manifest-ref <repo-relative-manifest.json> --expected-target <target> [--expected-scope <scope>]`。
仅当输出 `result=selected`、`next_segment=PRE` 且 verification valid 后，按输出的 `.agents/skills/dev/SKILL.md` 执行；否则按 typed recovery 停止。
