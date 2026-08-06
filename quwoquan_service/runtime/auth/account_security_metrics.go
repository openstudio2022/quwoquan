package auth

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	accountSecurityAuthorityChecksTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Namespace: "runtime",
			Subsystem: "auth",
			Name:      "account_security_authority_checks_total",
			Help:      "Synchronous account-security authority checks by fixed outcome.",
		},
		[]string{"outcome"},
	)
	accountSecurityAuthorityCheckDurationSeconds = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Namespace: "runtime",
			Subsystem: "auth",
			Name:      "account_security_authority_check_duration_seconds",
			Help:      "Synchronous account-security authority check latency.",
			Buckets:   []float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.15, 0.25, 0.5, 1},
		},
		[]string{"outcome"},
	)
)

func recordAccountSecurityAuthorityCheck(
	outcome string,
	startedAt time.Time,
) {
	accountSecurityAuthorityChecksTotal.WithLabelValues(outcome).Inc()
	accountSecurityAuthorityCheckDurationSeconds.WithLabelValues(outcome).Observe(
		time.Since(startedAt).Seconds(),
	)
}
