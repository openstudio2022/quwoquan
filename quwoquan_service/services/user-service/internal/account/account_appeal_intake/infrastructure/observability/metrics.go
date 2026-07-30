package observability

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/ports"
)

var (
	commands = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "user_account_appeal_intake_commands_total",
			Help: "Account appeal intake commands by bounded operation and outcome.",
		},
		[]string{"operation", "outcome"},
	)
	commandDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "user_account_appeal_intake_command_duration_seconds",
			Help:    "Account appeal intake command duration.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"operation", "outcome"},
	)
	purged = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "user_account_appeal_retention_purged_total",
			Help: "Expired account appeal records deleted by bounded entity kind.",
		},
		[]string{"entity"},
	)
)

type Recorder struct{}

func (Recorder) ObserveCommand(operation string, outcome string, duration time.Duration) {
	commands.WithLabelValues(operation, outcome).Inc()
	commandDuration.WithLabelValues(operation, outcome).Observe(duration.Seconds())
}

func (Recorder) AddPurged(entity string, count float64) {
	purged.WithLabelValues(entity).Add(count)
}

var _ ports.Metrics = Recorder{}
