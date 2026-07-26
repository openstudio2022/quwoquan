package stream

import "github.com/prometheus/client_golang/prometheus"

var (
	userAccountClosedConsumerTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "notification_user_account_closed_consumer_total",
			Help: "UserAccountClosed durable consumer outcomes.",
		},
		[]string{"result"},
	)
	userAccountClosedCleanupDuration = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name: "notification_user_account_closed_cleanup_seconds",
			Help: "UserAccountClosed notification cleanup latency.",
			Buckets: []float64{
				0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30,
			},
		},
	)
)

func init() {
	prometheus.MustRegister(
		userAccountClosedConsumerTotal,
		userAccountClosedCleanupDuration,
	)
}
