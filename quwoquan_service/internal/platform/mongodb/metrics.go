package mongodb

import (
	"context"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"go.mongodb.org/mongo-driver/v2/event"
)

var (
	mongoCommandDurationSeconds = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "mongo",
		Name:      "command_duration_seconds",
		Help:      "MongoDB command latency in seconds.",
		Buckets:   []float64{0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5},
	}, []string{"command", "database"})

	mongoCommandTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "mongo",
		Name:      "command_total",
		Help:      "Total MongoDB commands by command name, database, and status.",
	}, []string{"command", "database", "status"})

	mongoPoolInUse = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "mongo",
		Name:      "pool_in_use",
		Help:      "Number of connections currently in use.",
	})

	mongoPoolIdle = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "mongo",
		Name:      "pool_idle",
		Help:      "Number of idle connections in the pool.",
	})

	mongoPoolCreatedTotal = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "mongo",
		Name:      "pool_created_total",
		Help:      "Total connections created.",
	})

	mongoPoolClosedTotal = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "mongo",
		Name:      "pool_closed_total",
		Help:      "Total connections closed.",
	})
)

func newCommandMonitor() *event.CommandMonitor {
	return &event.CommandMonitor{
		Succeeded: func(_ context.Context, e *event.CommandSucceededEvent) {
			database := normalizedMetricLabel(e.DatabaseName)
			command := normalizedMetricLabel(e.CommandName)
			mongoCommandDurationSeconds.WithLabelValues(command, database).Observe(e.Duration.Seconds())
			mongoCommandTotal.WithLabelValues(command, database, "ok").Inc()
		},
		Failed: func(_ context.Context, e *event.CommandFailedEvent) {
			database := normalizedMetricLabel(e.DatabaseName)
			command := normalizedMetricLabel(e.CommandName)
			mongoCommandDurationSeconds.WithLabelValues(command, database).Observe(e.Duration.Seconds())
			mongoCommandTotal.WithLabelValues(command, database, "error").Inc()
		},
	}
}

func newPoolMonitor() *event.PoolMonitor {
	return &event.PoolMonitor{
		Event: func(e *event.PoolEvent) {
			switch e.Type {
			case event.ConnectionCreated:
				mongoPoolCreatedTotal.Inc()
				mongoPoolIdle.Inc()
			case event.ConnectionClosed:
				mongoPoolClosedTotal.Inc()
				mongoPoolIdle.Dec()
			case event.ConnectionCheckedOut:
				mongoPoolInUse.Inc()
				mongoPoolIdle.Dec()
			case event.ConnectionCheckedIn:
				mongoPoolInUse.Dec()
				mongoPoolIdle.Inc()
			}
		},
	}
}

func normalizedMetricLabel(value string) string {
	if value == "" {
		return "unknown"
	}
	return value
}
