package feedmetrics

import (
	"context"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

type Observer struct{}

var (
	blockedKeywordCandidatesTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "content_feed_blocked_keyword_candidates_total",
			Help: "Feed candidates evaluated against user blocked keywords.",
		},
	)
	blockedKeywordFilteredTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "content_feed_blocked_keyword_filtered_total",
			Help: "Feed candidates removed by user blocked keywords.",
		},
	)
)

func (Observer) ObserveBlockedKeywordFilter(
	_ context.Context,
	evaluated int,
	filtered int,
) {
	if evaluated > 0 {
		blockedKeywordCandidatesTotal.Add(float64(evaluated))
	}
	if filtered > 0 {
		blockedKeywordFilteredTotal.Add(float64(filtered))
	}
}
