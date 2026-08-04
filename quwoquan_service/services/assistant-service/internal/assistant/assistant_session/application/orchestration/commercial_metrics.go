package orchestration

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// 小趣商用业务指标（真相源：specs/feature-tree/assistant-run-learning/
// commercial_slo_observability.md）。告警规则见
// quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml
// 的 quwoquan_l2_assistant_objects 组；
// assistant_grounding_success_rate 由 recording rule 从 counter 对派生。

// assistantWrongDestinationIncidentsTotal 主动投递目的地校验失败计数；
// 非零立即 P0（告警 AssistantWrongDestinationIncident）。
var assistantWrongDestinationIncidentsTotal = promauto.NewCounter(prometheus.CounterOpts{
	Name: "assistant_wrong_destination_incidents_total",
	Help: "Proactive delivery destination validation failures (potential mis-delivery).",
})

// assistantMentionedConsumerDLQTotal records messages durably moved from the
// @小趣 consumer group to its replayable dead-letter stream.
var assistantMentionedConsumerDLQTotal = promauto.NewCounter(prometheus.CounterOpts{
	Name: "assistant_mentioned_consumer_dlq_total",
	Help: "Assistant-mentioned consumer messages moved to the replayable dead-letter stream.",
})

// RecordAssistantWrongDestinationIncident 由投递目的地校验点调用（messaging/
// subscription 投递前校验失败时）。
func RecordAssistantWrongDestinationIncident() {
	assistantWrongDestinationIncidentsTotal.Inc()
}

// RecordAssistantMentionedConsumerDLQ is called only after a failed @小趣
// mention has been retained in the DLQ and ACKed from the source consumer
// group, so alert volume is a count of recoverable dead letters rather than
// repeated processing attempts.
func RecordAssistantMentionedConsumerDLQ() {
	assistantMentionedConsumerDLQTotal.Inc()
}
