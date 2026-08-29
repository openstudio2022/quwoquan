# ops · design · gate

- [MUST] gate 的触发范围、阻断终态与修复方式单义。
  check: 读取 gate 契约；缺路径范围、typed failure 或修复动作时判失败。
- [MUST] 正反 fixture 能证明违规被拦、合规被放行。
  evidence: agent-context-budget
- [MUST NOT] 用 allowlist、warn-only 或基线放宽掩盖新增债务。
  check: 读取 diff；新增豁免或违规返回成功时判失败。
