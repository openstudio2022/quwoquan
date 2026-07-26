package mq

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

var (
	circleGroupChatSyncConsumerTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "chat_circle_group_sync_consumer_total",
			Help: "CircleGroup to Chat durable consumer outcomes.",
		},
		[]string{"stream", "result"},
	)
	circleGroupChatSyncApplyDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "chat_circle_group_sync_apply_seconds",
			Help:    "CircleGroup to Chat projection transaction duration.",
			Buckets: []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30},
		},
		[]string{"stream"},
	)
	circleGroupChatSyncLag = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "chat_circle_group_sync_event_lag_seconds",
			Help:    "Age of Circle source event when Chat projection completes.",
			Buckets: []float64{0.1, 0.5, 1, 3, 5, 10, 30, 60, 300, 900},
		},
		[]string{"stream"},
	)
)

func init() {
	prometheus.MustRegister(
		circleGroupChatSyncConsumerTotal,
		circleGroupChatSyncApplyDuration,
		circleGroupChatSyncLag,
	)
}

func recordCircleGroupChatSyncOutcome(stream, result string) {
	circleGroupChatSyncConsumerTotal.WithLabelValues(stream, result).Inc()
}

func observeCircleGroupChatSyncApply(stream string, duration time.Duration) {
	circleGroupChatSyncApplyDuration.WithLabelValues(stream).Observe(duration.Seconds())
}

func observeCircleGroupChatSyncLag(stream string, occurredAt time.Time) {
	if occurredAt.IsZero() {
		return
	}
	lag := time.Since(occurredAt).Seconds()
	if lag >= 0 {
		circleGroupChatSyncLag.WithLabelValues(stream).Observe(lag)
	}
}
