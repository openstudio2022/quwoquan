package reportmetrics

import (
	"context"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

const reportClosureSLO = 72 * time.Hour

type Observer struct{}

var (
	reportLifecycleTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_report_lifecycle_total",
			Help: "Report aggregate lifecycle transitions.",
		},
		[]string{"transition"},
	)
	reportClosureSeconds = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name: "content_report_closure_seconds",
			Help: "Seconds from report creation to resolved or dismissed.",
			Buckets: []float64{
				60,
				300,
				1800,
				3600,
				21600,
				86400,
				259200,
				604800,
			},
		},
		[]string{"status"},
	)
	reportClosureSLOTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_report_closure_slo_total",
			Help: "Closed reports split by the 72-hour lifecycle SLO.",
		},
		[]string{"status", "within_72h"},
	)
)

func (Observer) ReportCreated(context.Context) {
	reportLifecycleTotal.WithLabelValues("created").Inc()
}

func (Observer) ReportClosed(
	_ context.Context,
	status string,
	createdAt time.Time,
	closedAt time.Time,
) {
	duration := closedAt.Sub(createdAt)
	if duration < 0 {
		duration = 0
	}
	reportLifecycleTotal.WithLabelValues(status).Inc()
	reportClosureSeconds.WithLabelValues(status).Observe(duration.Seconds())
	within := "false"
	if duration <= reportClosureSLO {
		within = "true"
	}
	reportClosureSLOTotal.WithLabelValues(status, within).Inc()
}
