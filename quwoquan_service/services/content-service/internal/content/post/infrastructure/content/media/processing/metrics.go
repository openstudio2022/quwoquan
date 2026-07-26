package processing

import (
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	processingJobsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_media_processing_jobs_total",
			Help: "Media processing worker jobs by media type, input size class, and terminal result.",
		},
		[]string{"media_type", "input_size_class", "result"},
	)
	processingDurationSeconds = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name: "content_media_processing_duration_seconds",
			Help: "Wall time of one media processing job by media type, input size class, and terminal result.",
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
		[]string{"media_type", "input_size_class", "result"},
	)
	processingOutboxBatchEvents = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "content_media_processing_outbox_batch_events",
			Help: "Media outbox events returned by the most recent worker scan.",
		},
	)
	processingOutboxConsecutiveFullBatches = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "content_media_processing_outbox_consecutive_full_batches",
			Help: "Consecutive media outbox scans that reached the worker batch limit.",
		},
	)
	processingOutboxOldestEventAgeSeconds = promauto.NewGauge(
		prometheus.GaugeOpts{
			Name: "content_media_processing_outbox_oldest_event_age_seconds",
			Help: "Age of the oldest media outbox event observed in the current worker scan.",
		},
	)
	processingCompleteToReadySeconds = promauto.NewHistogramVec(
		prometheus.HistogramOpts{
			Name: "content_media_processing_complete_to_ready_seconds",
			Help: "Elapsed time from the durable upload-complete event to ready result.",
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
				1800,
				3600,
			},
		},
		[]string{"media_type", "input_size_class"},
	)
	processingPoisonEventsTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_media_processing_poison_events_total",
			Help: "Invalid media outbox source events detected by the worker.",
		},
		[]string{"reason"},
	)
	processingPoisonQuarantineFailuresTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_media_processing_poison_quarantine_failures_total",
			Help: "Media poison events that could not be durably quarantined before checkpoint advancement.",
		},
		[]string{"reason"},
	)
	processingDLQEventAgeSeconds = promauto.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "content_media_processing_dlq_event_age_seconds",
			Help: "Age of an event at durable media-processing DLQ admission, by poison reason.",
		},
		[]string{"reason"},
	)
)

// MetricsObserver is the production mediaprocessing.Observer.
type MetricsObserver struct {
	mu                     sync.Mutex
	consecutiveFullBatches int
}

func NewMetricsObserver() *MetricsObserver {
	return &MetricsObserver{}
}

func (*MetricsObserver) JobCompleted(
	mediaType string,
	inputSizeClass string,
	result string,
	duration time.Duration,
) {
	processingJobsTotal.WithLabelValues(mediaType, inputSizeClass, result).Inc()
	processingDurationSeconds.WithLabelValues(mediaType, inputSizeClass, result).Observe(duration.Seconds())
}

func (m *MetricsObserver) BatchObserved(eventCount int, batchLimit int) {
	if eventCount < 0 {
		eventCount = 0
	}
	processingOutboxBatchEvents.Set(float64(eventCount))

	m.mu.Lock()
	defer m.mu.Unlock()
	if batchLimit > 0 && eventCount >= batchLimit {
		m.consecutiveFullBatches++
	} else {
		m.consecutiveFullBatches = 0
	}
	processingOutboxConsecutiveFullBatches.Set(float64(m.consecutiveFullBatches))
}

func (*MetricsObserver) OutboxOldestEventAge(age time.Duration) {
	processingOutboxOldestEventAgeSeconds.Set(age.Seconds())
}

func (*MetricsObserver) CompleteToReady(
	mediaType string,
	inputSizeClass string,
	duration time.Duration,
) {
	processingCompleteToReadySeconds.WithLabelValues(mediaType, inputSizeClass).Observe(duration.Seconds())
}

func (*MetricsObserver) Poisoned(reason string, eventAge time.Duration) {
	processingPoisonEventsTotal.WithLabelValues(reason).Inc()
	processingDLQEventAgeSeconds.WithLabelValues(reason).Set(eventAge.Seconds())
}

func (*MetricsObserver) PoisonQuarantineFailed(reason string) {
	processingPoisonQuarantineFailuresTotal.WithLabelValues(reason).Inc()
}
