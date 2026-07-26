package projection

import "github.com/prometheus/client_golang/prometheus"

// Interest-profile projection metrics (user-service side). These observe the
// consumption end of the cross-service flywheel: projection success/failure and
// freshness lag (recomputedAt → projection apply), feeding the evaluation
// dashboard's coverage/freshness panels.
var (
	interestProjectionTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "quwoquan_interest_projection_total",
		Help: "Interest profile projections by result (ok|parse_error|write_error).",
	}, []string{"result"})

	interestFreshnessLag = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "quwoquan_interest_projection_freshness_lag_seconds",
		Help:    "Lag between profile recomputedAt and projection apply time.",
		Buckets: prometheus.ExponentialBuckets(1, 4, 9),
	})
)

func init() {
	prometheus.MustRegister(interestProjectionTotal, interestFreshnessLag)
}
