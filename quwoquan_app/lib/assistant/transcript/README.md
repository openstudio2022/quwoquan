# Assistant 对话时间轴（Transcript）有界上下文

本目录实现 **多上下文 DTO**，与 UI 层 `Map<String, dynamic>` 时间轴解耦。依赖方向：**transcript（纯 Dart）→ application（Assembler/Codec）→ ui/assistant（Controller/Widget）**。

## 与 `AssistantTurn` codegen 的边界

- `lib/assistant/generated/contracts/assistant_turn.g.dart`：**Planner / contract** 语义（`AssistantTurnOutput` 等）。
- **本目录** `PersistedAssistantTimelinePayload`：**历史时间轴行**上的 `assistant_turn_v1` 持久化块与 UI 信封字段的组合模型。
- **禁止**混用命名：不在 transcript 类型上使用 `AssistantTurn` 前缀指代时间轴行。

## 上下文一览

| ID | 名称 | 职责 |
|----|------|------|
| C1 | TranscriptIdentity | 行 id、会话归属 |
| C2 | UserUtterance | 用户文本与发送态（无 runArtifacts） |
| C3 | AssistantAnswerAnchor | runId/traceId/sourceQuery/降级与质量锚点 |
| C4 | PersistedAssistantTimeline | 与 `buildPersistedAssistantTurnFields` 对齐的持久化载荷 |
| C6 | ReplayAudit | 学习回放记录（独立于时间轴排序展示） |
| C7 | Citation | 引用打开 WebView 的不可变快照 |
| Row | AssistantTranscriptTimelineRow | `sealed` 用户行 / 助手行 / 错误行 |

## 禁止事项

- `lib/ui/assistant/widgets/**` **不得**直接解析 `PersistedAssistantTimelinePayload` 内部 JSON 键；展示用数据经 `AssistantTranscriptTimelineRow` 或 Assembler 暴露。
- 磁盘读写边界外出现的 `Map<String, dynamic>` 须在 **Codec** 入口立即转为 Row。

## Codec 与 fixture

- 单测夹具：`quwoquan_app/test/assistant/transcript/fixtures/`
- 编解码：[`persisted_timeline_turn_codec.dart`](persisted_timeline/persisted_timeline_turn_codec.dart)
