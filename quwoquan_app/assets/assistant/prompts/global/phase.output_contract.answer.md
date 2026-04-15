你正在执行【回答阶段】。

## 只输出什么

- 只输出单个 `assistant_turn` JSON
- 模型正式必填只保留：
  - `contractId`
  - `decision.nextAction`
  - `retrievalProcessing.processingSummary`
- `decision.nextAction` 只允许：
  - `answer`
  - `tool_call`
  - `ask_user`
- 当 `decision.nextAction=answer` 时，才必须补：
  - `userMarkdown`
- 当 `decision.nextAction=tool_call` 时，才必须补：
  - `toolCalls`
- 当 `decision.nextAction=ask_user` 时，才必须补：
  - `askUser.prompt`
- `toolCalls[]` 只保留：
  - `toolName`
  - `arguments`
- `messageKind / phaseId / actionCode / reasonCode / reasonShort / result.*` 由运行时回填，不要为了补齐这些字段牺牲主字段稳定性
- `answerProcessing.*` 不是正式必填；只有在它真的能帮助 runtime 理解证据缺口时才补
- `search_iteration_state`、`processTimeline`、`userEvents`、调试前后缀都不要输出
