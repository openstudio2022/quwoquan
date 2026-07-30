package observability

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/ports"
)

var (
	caseCommands = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "product_ops_account_enforcement_case_commands_total",
			Help: "Account enforcement case commands by bounded operation and outcome.",
		},
		[]string{"operation", "outcome"},
	)
	caseCommandDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "product_ops_account_enforcement_case_command_duration_seconds",
			Help:    "Account enforcement case command duration.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"operation", "outcome"},
	)
	deliveryAttempts = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "product_ops_account_enforcement_delivery_attempts_total",
			Help: "UserAccount enforcement delivery attempts by action and bounded outcome.",
		},
		[]string{"action", "outcome"},
	)
	deliveryDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "product_ops_account_enforcement_delivery_duration_seconds",
			Help:    "UserAccount enforcement delivery duration.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"action", "outcome"},
	)
	deliveryBacklog = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "product_ops_account_enforcement_delivery_backlog",
			Help: "Account enforcement delivery backlog by bounded state.",
		},
		[]string{"state"},
	)
)

type Recorder struct{}

func (Recorder) ObserveCaseCommand(operation string, outcome string, duration time.Duration) {
	caseCommands.WithLabelValues(operation, outcome).Inc()
	caseCommandDuration.WithLabelValues(operation, outcome).Observe(duration.Seconds())
}

func (Recorder) ObserveDelivery(action string, outcome string, duration time.Duration) {
	deliveryAttempts.WithLabelValues(action, outcome).Inc()
	deliveryDuration.WithLabelValues(action, outcome).Observe(duration.Seconds())
}

func (Recorder) SetDeliveryBacklog(state string, count float64) {
	deliveryBacklog.WithLabelValues(state).Set(count)
}

var _ ports.Metrics = Recorder{}
