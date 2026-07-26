package recommendation

import "github.com/prometheus/client_golang/prometheus"

// Interest-profile derivation metrics (content-service side). These feed the
// large-loop flywheel evaluation dashboard: recompute throughput, profile
// richness (top-interest count), lifecycle mix, and interest diversity (entropy).
var (
	interestRecomputeTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "quwoquan_interest_profile_recompute_total",
		Help: "Interest profile recompute attempts by result (ok|empty|error).",
	}, []string{"result"})

	interestTopInterestCount = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "quwoquan_interest_profile_top_interests",
		Help:    "Number of ranked top interests in a recomputed profile.",
		Buckets: []float64{0, 1, 2, 4, 6, 8, 12},
	})

	interestLifecycleTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "quwoquan_interest_profile_lifecycle_total",
		Help: "Recomputed profiles by lifecycle stage (new|active|dormant).",
	}, []string{"stage"})

	interestEntropy = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "quwoquan_interest_profile_entropy_bits",
		Help:    "Shannon entropy (bits) of the top-interest score distribution; higher = more diverse.",
		Buckets: prometheus.LinearBuckets(0, 0.5, 9),
	})

	interestSegmentMembership = prometheus.NewHistogram(prometheus.HistogramOpts{
		Name:    "quwoquan_interest_profile_segment_membership",
		Help:    "Number of rule-based segments a recomputed profile falls into.",
		Buckets: []float64{0, 1, 2, 3, 5},
	})

	interestSegmentHitTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "quwoquan_interest_profile_segment_hit_total",
		Help: "Per-segment membership hits during interest recompute.",
	}, []string{"segment"})
)

func init() {
	prometheus.MustRegister(
		interestRecomputeTotal, interestTopInterestCount, interestLifecycleTotal,
		interestEntropy, interestSegmentMembership, interestSegmentHitTotal,
	)
}
