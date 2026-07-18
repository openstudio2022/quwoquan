package recommendation

import "testing"

func TestRecordBehaviorMetricRequiresCanonicalContentType(t *testing.T) {
	before := SnapshotEngagementMetrics()

	RecordBehaviorMetric(BehaviorSignal{
		Action:      "impression",
		ContentType: "",
		Tags:        []string{"video"},
	})
	RecordBehaviorMetric(BehaviorSignal{
		Action:      "impression",
		ContentType: "photo",
	})

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

	RecordBehaviorMetric(BehaviorSignal{
		Action:      "impression",
		ContentType: "image",
	})
	RecordBehaviorMetric(BehaviorSignal{
		Action:      "impression",
		ContentType: "micro",
	})

	after := SnapshotEngagementMetrics()
	if got := after["impression_photo"] - before["impression_photo"]; got != 1 {
		t.Fatalf("canonical image metric delta = %d, want 1", got)
	}
	if got := after["impression_moment"] - before["impression_moment"]; got != 1 {
		t.Fatalf("canonical micro metric delta = %d, want 1", got)
	}
}
