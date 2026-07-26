package observability

import (
	"strconv"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	filtercatalogapp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/application"
)

type Observer struct{}

var (
	stageTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_filter_catalog_stage_total",
			Help: "Filter catalog Stage outcomes.",
		},
		[]string{"outcome", "replayed"},
	)
	activateTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_filter_catalog_activate_total",
			Help: "Filter catalog Activate outcomes.",
		},
		[]string{"outcome", "replayed"},
	)
	rollbackTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_filter_catalog_rollback_total",
			Help: "Filter catalog Rollback outcomes.",
		},
		[]string{"outcome", "replayed"},
	)
	getTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_filter_catalog_get_total",
			Help: "Active filter catalog reader outcomes.",
		},
		[]string{"outcome"},
	)
	operationDuration = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "content_filter_catalog_operation_duration_seconds",
			Help:    "Filter catalog operation latency by operation.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"operation", "outcome"},
	)
)

func (Observer) Observe(
	operation string,
	outcome string,
	replayed bool,
	duration time.Duration,
) {
	replayedLabel := strconv.FormatBool(replayed)
	switch operation {
	case filtercatalogapp.OperationStage:
		stageTotal.WithLabelValues(outcome, replayedLabel).Inc()
	case filtercatalogapp.OperationActivate:
		activateTotal.WithLabelValues(outcome, replayedLabel).Inc()
	case filtercatalogapp.OperationRollback:
		rollbackTotal.WithLabelValues(outcome, replayedLabel).Inc()
	case filtercatalogapp.OperationGet:
		getTotal.WithLabelValues(outcome).Inc()
	default:
		return
	}
	operationDuration.WithLabelValues(operation, outcome).Observe(duration.Seconds())
}
