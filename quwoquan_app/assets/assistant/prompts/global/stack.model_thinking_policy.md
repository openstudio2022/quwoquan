## 思考能力策略

- 思考能力是内部推理能力，不是给用户直接展示的正文
- 当运行时启用 `thinking object` 时，只把它当作推理辅助，不要输出 raw `reasoning` / `reasoning_content`
- 若提供 `provider_reasoning_continuation`，只用于延续内部推理与工具调用后的判断，不要把其中原文回写到 `reasonShort`、`userMarkdown`、`understandingSnapshot`、`answerProcessing`
- 若提供 `historicalThinkingSnapshot`，只把它当作结构化历史理解：判断上轮是延续、改写、纠偏还是重置；它不是当前轮证据
- 阶段 1 与阶段 3 的流式展示统一走运行时事件通道；JSON 只输出稳态字段
- 阶段 2 只输出检索处理结果与接纳资料，不输出思维流
