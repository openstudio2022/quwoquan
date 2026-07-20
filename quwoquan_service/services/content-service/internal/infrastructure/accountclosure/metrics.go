package accountclosure

import "github.com/prometheus/client_golang/prometheus"

var (
	accountClosureConsumerTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_user_account_closed_consumer_total",
			Help: "UserAccountClosed durable consumer outcomes.",
		},
		[]string{"result"},
	)
	accountClosureDuration = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name: "content_user_account_closed_cleanup_seconds",
			Help: "UserAccountClosed deletion and anonymization latency.",
			Buckets: []float64{
				0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30,
			},
		},
	)
)

func init() {
	prometheus.MustRegister(
		accountClosureConsumerTotal,
		accountClosureDuration,
	)
}
