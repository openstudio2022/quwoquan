package mongo

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

// NewCommandMonitor returns a MongoDB event.CommandMonitor that records
// Prometheus metrics for every command. Latency is taken from the driver's
// CommandFinishedEvent.Duration on success/failure.
func NewCommandMonitor() *event.CommandMonitor {
	return &event.CommandMonitor{
		Succeeded: func(_ context.Context, e *event.CommandSucceededEvent) {
			db := e.DatabaseName
			if db == "" {
				db = "unknown"
			}
			cmd := e.CommandName
			if cmd == "" {
				cmd = "unknown"
			}
			dur := e.Duration.Seconds()
			mongoCommandDurationSeconds.WithLabelValues(cmd, db).Observe(dur)
			mongoCommandTotal.WithLabelValues(cmd, db, "ok").Inc()
		},
		Failed: func(_ context.Context, e *event.CommandFailedEvent) {
			db := e.DatabaseName
			if db == "" {
				db = "unknown"
			}
			cmd := e.CommandName
			if cmd == "" {
				cmd = "unknown"
			}
			dur := e.Duration.Seconds()
			mongoCommandDurationSeconds.WithLabelValues(cmd, db).Observe(dur)
			mongoCommandTotal.WithLabelValues(cmd, db, "error").Inc()
		},
	}
}

// NewPoolMonitor returns a MongoDB event.PoolMonitor that maps driver v2 pool
// events (see event.ConnectionCreated, event.ConnectionCheckedOut, …) to
// Prometheus gauges and counters.
func NewPoolMonitor() *event.PoolMonitor {
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
