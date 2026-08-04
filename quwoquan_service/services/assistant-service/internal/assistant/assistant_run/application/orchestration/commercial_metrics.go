package orchestration

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Run-owned response and grounding SLOs live beside the execution pipeline;
// Session retains only delivery/consumer metrics.
var assistantFirstVisibleResponseMs = promauto.NewHistogram(prometheus.HistogramOpts{
	Name:    "assistant_first_visible_response_ms",
	Help:    "Milliseconds from run start to first user-visible answer event.",
	Buckets: []float64{100, 250, 500, 1000, 1500, 2000, 3000, 5000, 8000, 15000, 30000},
})

var assistantGroundingTotal = promauto.NewCounterVec(prometheus.CounterOpts{
	Name: "assistant_grounding_total",
	Help: "Assistant grounding outcomes (answer produced with usable evidence vs failed).",
}, []string{"outcome"})

func recordAssistantFirstVisibleResponse(elapsed time.Duration) {
	if elapsed <= 0 {
		return
	}
	assistantFirstVisibleResponseMs.Observe(float64(elapsed.Milliseconds()))
}

func recordAssistantGroundingOutcome(success bool) {
	outcome := "failure"
	if success {
		outcome = "success"
	}
	assistantGroundingTotal.WithLabelValues(outcome).Inc()
}
