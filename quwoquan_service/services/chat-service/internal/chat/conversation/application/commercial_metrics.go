package application

import (
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	chatMentionCommandTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "chat_mention_command_total",
			Help: "Mention-bearing SendMessage command outcomes by bounded mention scope.",
		},
		[]string{"result", "scope"},
	)
	chatReadWatermarkCommandTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "chat_read_watermark_command_total",
			Help: "MarkAsRead command outcomes.",
		},
		[]string{"result"},
	)
	chatInboxProjectionEventLagSeconds = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "chat_inbox_projection_event_lag_seconds",
			Help:    "Age of a MessageSent fact when its Inbox projection is applied.",
			Buckets: []float64{0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 300},
		},
	)
	chatInboxProjectionDrainTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "chat_inbox_projection_drain_total",
			Help: "Inbox projector drain outcomes.",
		},
		[]string{"result"},
	)
)

func init() {
	// CounterVec 在首个 label 子序列创建前不会出现在 Gather 结果中；
	// 预置有限标签集合，使零流量环境也能暴露稳定的商业指标时序。
	for _, result := range []string{"succeeded", "failed"} {
		for _, scope := range []string{"all", "members"} {
			chatMentionCommandTotal.WithLabelValues(result, scope)
		}
		chatReadWatermarkCommandTotal.WithLabelValues(result)
		chatInboxProjectionDrainTotal.WithLabelValues(result)
	}
}

func recordChatMentionCommand(mentions []string, err error) {
	scope := chatMentionScope(mentions)
	if scope == "" {
		return
	}
	result := "succeeded"
	if err != nil {
		result = "failed"
	}
	chatMentionCommandTotal.WithLabelValues(result, scope).Inc()
}

func chatMentionScope(mentions []string) string {
	for _, mention := range mentions {
		if strings.TrimSpace(mention) == "__all__" {
			return "all"
		}
	}
	if len(mentions) > 0 {
		return "members"
	}
	return ""
}

func recordChatReadWatermarkCommand(err error) {
	result := "succeeded"
	if err != nil {
		result = "failed"
	}
	chatReadWatermarkCommandTotal.WithLabelValues(result).Inc()
}

func observeChatInboxProjectionEventLag(occurredAt time.Time) {
	if occurredAt.IsZero() {
		return
	}
	lag := time.Since(occurredAt).Seconds()
	if lag >= 0 {
		chatInboxProjectionEventLagSeconds.Observe(lag)
	}
}
