# L3 特性：run-stream-protocol

## 功能说明
- 定义小趣 AssistantRun 从服务端持久化事件到 App 时间线的单轨流式协议。
- 用户可见的事件集合固定为 `run_started`、`process_replace`、`process_append`、
  `process_commit`、`answer_delta`、`completed`、`failed`、`cancelled`；不向客户端
  暴露模型原始推理、prompt、tool input、provider trace 或调试字段。

## 交付边界
- `run_started` 后必须先以 `process_replace` 建立过程快照；每个 `seq` 对同一 run
  严格递增并可由 `Last-Event-ID` / `resumeToken` 从断点续传。
- `answer_delta` 只承载模型最终回答阶段实际产生的 token 文本；非流式模型回退只能产生
  一次完整回答增量，禁止定时器或字符串切片伪造逐字流。
- 每个 run 恰有一个终态：`completed`、`failed` 或 `cancelled`。`completed` 的
  `finalAnswer` 是客户端重放和最终渲染的权威文本。
- 过程条目仅投影真实的技能选择、规划、工具执行、证据审阅和回答生成；引用与计数来自
  实际工具观察，不能以固定叙事或演示数据补齐。
- 首个 `answer_delta` 必须写入 `assistant_first_visible_response_ms`，用于首 token
  SLO 与告警；运行事件先持久化，客户端断开不得取消后台 run。

## 验收标准
- A1：流式输出可完整收敛为 `completed.finalAnswer`，且累计 `answer_delta` 与最终
  文本的渲染语义一致。
- A2：客户端在 SSE 断开后携带最后 event id 续传，不重复投影既有序号。
- A3：未知事件类型、内部字段泄露、缺失或多重终态均按契约失败，不得静默降级。
- A4：流式链路的首 token、grounding 结果、失败终态和取消终态均具备可观测证据。
