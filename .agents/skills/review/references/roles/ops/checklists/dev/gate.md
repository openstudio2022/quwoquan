# ops · dev · gate

- [MUST] gate 声明触发范围、阻断条件、修复方式与正反 fixture。
  evidence: agent-context-budget
- [MUST] 违规退出非零；不得包装成 warning 或成功。
  check: 读取判失败分支与反例输出；违规退出零时判失败。
- [MUST NOT] 放宽棘轮或新增 allowlist 让本次改动转绿。
  check: 读取 diff；新增豁免或上调 baseline 时判失败。
