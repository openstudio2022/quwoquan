package messaging

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

var (
	userAccountClosedConsumerTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "circle_user_account_closed_consumer_total",
			Help: "UserAccountClosed durable consumer outcomes.",
		},
		[]string{"result"},
	)
	userAccountClosedCleanupSeconds = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name: "circle_user_account_closed_cleanup_seconds",
			Help: "UserAccountClosed deletion and anonymization latency.",
			Buckets: []float64{
				0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30,
			},
		},
	)
)

func init() {
	prometheus.MustRegister(
		userAccountClosedConsumerTotal,
		userAccountClosedCleanupSeconds,
	)
}

func recordUserAccountClosedOutcome(result string) {
	userAccountClosedConsumerTotal.WithLabelValues(result).Inc()
}

func observeUserAccountClosedDuration(duration time.Duration) {
	userAccountClosedCleanupSeconds.Observe(duration.Seconds())
}
