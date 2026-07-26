package stream

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	accountSecurityConsumerTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "realtime_account_security_consumer_total",
			Help: "Durable account-security consumer outcomes by bounded event class and outcome.",
		},
		[]string{"event_class", "outcome"},
	)
	accountSecurityConsumerDuration = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Name: "realtime_account_security_consumer_duration_seconds",
			Help: "Duration of an applied account-security terminal event.",
		},
	)
)
