# 小趣商用主线 SLO / 观测 / 灰度回滚

## SLO

- 会话内 `@小趣` 首个可见响应：p95 <= 3s。
- `SearchXiaoquResults` grounding success：>= 95%，citation 均带 `objectTypeRef/recallSource/score`。
- 主动投递 wrong-destination incidents：0。
- `AssistantMentioned` stream consumer ack success：>= 99.9%，DLQ 必须 15 分钟内告警。

## KPI

- citation click-through rate。
- proactive open rate / ack rate。
- suggested action adoption / undo rate。
- explicit thumbs up/down 与 low-score reason 分布。
- persona drift：用户撤销偏好事实或负反馈中“个性化不合适”的占比。

## 告警

- `assistant_mentioned_consumer_dlq_total > 0` 连续 15 分钟告警。
- `assistant_grounding_success_rate < 95%` 连续 30 分钟告警。
- `assistant_first_visible_response_p95_ms > 3000` 连续 30 分钟告警。
- `assistant_wrong_destination_incidents > 0` 立即 P0。

## 灰度与回滚

- `SearchXiaoquResults` grounding orchestration 独立 feature flag，异常时降级到站内 canonical search fallback。
- proactive `conversation/group` destination 独立灰度，默认只对 inviter opt-in 会话开启。
- `AssistantMentionedConsumer` 可通过停止 consumer 回滚；chat-service 继续保留 stream 事件，恢复后可重放。
- 群/会话主动投递异常时，保留 user AppMessage destination，不走 chat-service SendMessage。
