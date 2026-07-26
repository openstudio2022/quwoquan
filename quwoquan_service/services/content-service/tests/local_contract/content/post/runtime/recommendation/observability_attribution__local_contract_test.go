// spec_ref: specs/feature-tree/recommendation-platform/evaluation-and-flywheel/recommendation-observability-dashboard/spec.md#gwt-001
package recommendationlocalcontract

import (
	"testing"

	"quwoquan_service/runtime/recommendation"

	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"
)

func TestRecommendationObservabilityAttributionLocalContractTest(t *testing.T) {
	servedLabels := map[string]string{
		"channel":            "travel",
		"vertical":           "travel_photography",
		"supply_source":      "data_engineering",
		"recall_path":        "collab_i2i",
		"ranking_version":    "rank-local",
		"reason_version":     "reason-local",
		"intersection_class": "none",
		"experiment_bucket":  "premium",
	}
	servedBefore := counterValue(t, "recommendation_feed_served_by_attribution_total", servedLabels)
	recommendation.RecordServedItemsByAttribution([]recommendation.FeedItem{{
		ContentID:       "post_attr_local_1",
		ContentVertical: "travel_photography",
		SupplySource:    "data_engineering",
		RecallPath:      "collab_i2i",
	}}, "travel", "rank-local", "reason-local", "premium")
	if got := counterValue(t, "recommendation_feed_served_by_attribution_total", servedLabels) - servedBefore; got != 1 {
		t.Fatalf("served attribution metric delta = %v, want 1", got)
	}

	behaviorLabels := map[string]string{
		"state":              "click",
		"action":             "click",
		"channel":            "travel",
		"vertical":           "travel_photography",
		"supply_source":      "data_engineering",
		"recall_path":        "collab_u2i",
		"ranking_version":    "rank-local",
		"reason_version":     "reason-local",
		"intersection_class": "fact",
		"experiment_bucket":  "premium",
	}
	behaviorBefore := counterValue(t, "recommendation_behavior_by_attribution_total", behaviorLabels)
	recommendation.RecordBehaviorIngest(recommendation.BehaviorSignal{
		Action:            "click",
		State:             "click",
		ChannelID:         "travel",
		ContentVertical:   "travel_photography",
		SupplySource:      "data_engineering",
		RecallPath:        "collab_u2i",
		RankingVersion:    "rank-local",
		ReasonVersion:     "reason-local",
		IntersectionClass: "fact",
		ExperimentBucket:  "premium",
	})
	if got := counterValue(t, "recommendation_behavior_by_attribution_total", behaviorLabels) - behaviorBefore; got != 1 {
		t.Fatalf("behavior attribution metric delta = %v, want 1", got)
	}

	// N1-3：experiment_bucket 缺失时收敛为 unknown（bounded 语义，无高基数）。
	unknownLabels := map[string]string{
		"state":             "click",
		"action":            "click",
		"channel":           "travel",
		"experiment_bucket": "unknown",
	}
	unknownBefore := counterValue(t, "recommendation_behavior_by_attribution_total", unknownLabels)
	recommendation.RecordBehaviorIngest(recommendation.BehaviorSignal{
		Action:    "click",
		State:     "click",
		ChannelID: "travel",
	})
	if got := counterValue(t, "recommendation_behavior_by_attribution_total", unknownLabels) - unknownBefore; got != 1 {
		t.Fatalf("unknown experiment_bucket fallback delta = %v, want 1", got)
	}
}

func counterValue(t *testing.T, metricName string, labels map[string]string) float64 {
	t.Helper()
	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		t.Fatalf("gather prometheus metrics: %v", err)
	}
	for _, family := range families {
		if family.GetName() != metricName {
			continue
		}
		for _, metric := range family.GetMetric() {
			if metricLabelsMatch(metric, labels) {
				if metric.GetCounter() == nil {
					t.Fatalf("metric %s matching %v is not a counter", metricName, labels)
				}
				return metric.GetCounter().GetValue()
			}
		}
		return 0
	}
	return 0
}

func metricLabelsMatch(metric *dto.Metric, labels map[string]string) bool {
	remaining := make(map[string]string, len(labels))
	for key, value := range labels {
		remaining[key] = value
	}
	for _, pair := range metric.GetLabel() {
		if want, ok := remaining[pair.GetName()]; ok && want == pair.GetValue() {
			delete(remaining, pair.GetName())
		}
	}
	return len(remaining) == 0
}
