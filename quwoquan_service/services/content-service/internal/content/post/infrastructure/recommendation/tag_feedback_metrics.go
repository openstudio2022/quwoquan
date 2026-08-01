package recommendation

import "github.com/prometheus/client_golang/prometheus"

var (
	tagFeedbackConsumerTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "content_tag_feedback_fact_consumer_total",
			Help: "TagFeedbackRecorded durable consumer outcomes.",
		},
		[]string{"result"},
	)
	tagFeedbackConsumerLagSeconds = prometheus.NewHistogram(
		prometheus.HistogramOpts{
			Name: "content_tag_feedback_fact_consumer_lag_seconds",
			Help: "Elapsed time from TagFeedbackRecorded to committed feature projection.",
			Buckets: []float64{
				0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 300, 900, 3600,
			},
		},
	)
	tagFeedbackConsumerLastSuccessUnix = prometheus.NewGauge(
		prometheus.GaugeOpts{
			Name: "content_tag_feedback_fact_consumer_last_success_unixtime",
			Help: "Unix time of the latest successful TagFeedbackRecorded consumer scan.",
		},
	)
)

func init() {
	prometheus.MustRegister(
		tagFeedbackConsumerTotal,
		tagFeedbackConsumerLagSeconds,
		tagFeedbackConsumerLastSuccessUnix,
	)
}
