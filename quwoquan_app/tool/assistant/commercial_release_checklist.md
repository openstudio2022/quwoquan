# 个人助手商用封板检查单（19 垂类）

## 运行时封板
- [ ] `assistant_agent_loop` 已启用 19 垂类自动路由（无 `domainId` 也可分类）。
- [ ] 每轮请求注入 `dialogueRoundScript`（状态、事件、下一状态、必填字段、硬失败码）。
- [ ] 结构化响应包含 `domainId`、`dialogueRuntime`、`roundTrace`，并通过 `runArtifacts.displayMarkdown` 提供用户可见答案。
- [ ] 对话续转已接入：上一轮 `dialogueState` 参与下一轮状态推进。

## 模板与状态机封板
- [ ] 每个垂类 `dialogue` 六件套完整（`state_machine/state_prompts/state_contracts/state_transition_contract/state_transition_test_cases/dialogue_judge_prompt`）。
- [ ] `state_transition_contract` 均满足：7 固定评分项、`weightedScoringEnabled=false`、分项阈值 80、关键项阈值 90。
- [ ] `state_prompts` 显式约束总分总、`missingContextSlots`、`fillGuidance`、`followupPrompt`。
- [ ] 每域 `state_transition_test_cases` 用例数量 >= 8。

## 评测与验收封板
- [ ] 运行 `state_transition_e2e_runner.py --all-domains --spotcheck-ratio 1.0`。
- [ ] 每域输出以下文件到 `app_log/personal_assistant_eval/<domain>/`：
  - `state_transition_eval_report.json`
  - `state_transition_eval_report.md`
  - `manual_spotcheck_report.md`
  - `round_trace.jsonl`
- [ ] 全域聚合文件输出到 `app_log/personal_assistant_eval/all_domains/`：
  - `state_transition_eval_report.json`
  - `state_transition_eval_report.md`
- [ ] GO 条件：所有域 `goNoGo=GO`，且无 critical hard-fail。

## UI 封板
- [ ] 小趣聊天页直接发问可完成：路由 -> 状态机 -> 回答 -> 下一轮续转。
- [ ] 助手消息优先展示 `userFacingMarkdown`（总分总可读文本）。
- [ ] 失败场景有降级文案，不暴露技术错误细节给用户。
