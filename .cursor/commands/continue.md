---
name: /continue
description: 从会话停下的地方继续推进——中断续跑、收口后开下一轮或按既定计划开工
---

先执行 `python3 quwoquan_ops/cli/workflow_host_adapter.py --schema-version 1 --host cursor --adapter cursor-command-shell --canonical-command /continue --manifest-ref <repo-relative-manifest.json> --expected-target <target> [--expected-scope <scope>]`。
仅当输出 `result=selected`、`next_segment=PRE` 且 verification valid 后，按输出的 `.agents/skills/continue/SKILL.md` 执行；否则按 typed recovery 停止。
