package processing

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	processingJobsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_media_processing_jobs_total",
			Help: "Media processing worker jobs by terminal result.",
		},
		[]string{"result"},
	)
	processingDurationSeconds = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name: "content_media_processing_duration_seconds",
			Help: "Wall time of one media processing job (download, transcode, artifacts, upload).",
			Buckets: []float64{
				1,
				5,
				15,
				30,
				60,
				120,
				300,
				600,
				900,
			},
		},
		[]string{"result"},
	)
	processingOutboxPending = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "content_media_processing_outbox_pending",
			Help: "Media outbox events seen by the last worker scan (0 = fully drained).",
		},
	)
)

// MetricsObserver is the production mediaprocessing.Observer.
type MetricsObserver struct{}

func (MetricsObserver) JobCompleted(result string, duration time.Duration) {
	processingJobsTotal.WithLabelValues(result).Inc()
	processingDurationSeconds.WithLabelValues(result).Observe(duration.Seconds())
}

func (MetricsObserver) OutboxLag(pending int) {
	processingOutboxPending.Set(float64(pending))
}
