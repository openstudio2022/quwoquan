package recommendation

import "testing"

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md#req-001

func TestRecordBehaviorMetricRequiresCanonicalContentType(t *testing.T) {
	before := SnapshotEngagementMetrics()

	RecordBehaviorMetric(BehaviorSignal{
		Action:      "impression",
		ContentType: "",
		Tags:        []string{"video"},
	})
	for _, contentType := range []string{"photo", "micro", "moment", "unknown"} {
		RecordBehaviorMetric(BehaviorSignal{
			Action:      "impression",
			ContentType: contentType,
		})
	}

	after := SnapshotEngagementMetrics()
	if after["impression_total"] != before["impression_total"] {
		t.Fatalf(
			"missing or retired contentType must not update typed metrics: before=%d after=%d",
			before["impression_total"],
			after["impression_total"],
		)
	}
}

func TestRecordBehaviorMetricUsesCanonicalContentTypes(t *testing.T) {
	before := SnapshotEngagementMetrics()
	actions := map[string]string{
		"impression": "impression", "click": "click", "content_depth": "deep_engage",
		"like": "like", "share": "share", "comment": "comment",
	}
	for action := range actions {
		for _, contentType := range []string{"image", "video", "article"} {
			RecordBehaviorMetric(BehaviorSignal{
				Action: action, ContentType: contentType, EngagementDepth: 2,
			})
		}
	}

	after := SnapshotEngagementMetrics()
	for _, prefix := range actions {
		for _, contentType := range []string{"image", "video", "article"} {
			key := prefix + "_" + contentType
			if got := after[key] - before[key]; got != 1 {
				t.Errorf("canonical %s metric delta = %d, want 1", key, got)
			}
		}
	}
	for key, want := range map[string]int64{
		"impression_total": 3, "click_total": 3, "deep_engage_total": 3, "interaction_total": 9,
	} {
		if got := after[key] - before[key]; got != want {
			t.Errorf("%s delta = %d, want %d", key, got, want)
		}
	}
}

func TestSnapshotEngagementMetricsHasExactCanonicalKeys(t *testing.T) {
	// 完整键集合同时锁住 canonical 类型与现存非类型指标；退役键不能作为零值保留。
	expected := make(map[string]bool)
	for _, prefix := range []string{"impression", "click", "deep_engage", "like", "share", "comment"} {
		for _, contentType := range []string{"image", "video", "article"} {
			expected[prefix+"_"+contentType] = true
		}
	}
	for _, key := range []string{
		"impression_total", "click_total", "deep_engage_total", "interaction_total",
		"dislike_total", "skip_total", "social_impressions", "social_positive_actions",
		"source_organic_feed", "source_friend_share", "source_chat_link", "source_circle_post",
		"source_author_profile", "source_entity_page", "source_search", "source_push_notification",
		"model_hits", "rule_hits", "model_fallbacks", "model_timeouts", "total_requests", "empty_feed_results",
	} {
		expected[key] = true
	}
	snapshot := SnapshotEngagementMetrics()
	for key := range snapshot {
		if !expected[key] {
			t.Errorf("unexpected metric key %q", key)
		}
	}
	for key := range expected {
		if _, ok := snapshot[key]; !ok {
			t.Errorf("missing metric key %q", key)
		}
	}
}
