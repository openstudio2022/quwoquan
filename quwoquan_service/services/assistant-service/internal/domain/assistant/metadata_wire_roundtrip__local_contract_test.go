package assistant

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// F4/F5: JSON shape for ops summary stays aligned with contracts/metadata/assistant/assistant_run/fields.yaml (AssistantLearningOpsSummaryView).
func TestAssistantLearningOpsSummaryView_JSONRoundTrip(t *testing.T) {
	in := AssistantLearningOpsSummaryView{
		UserID:                "u1",
		TotalFeedbackCount:    3,
		PositiveFeedbackCount: 2,
		NegativeFeedbackCount: 1,
		TextFeedbackCount:     1,
		HighPriorityCount:     0,
		MediumPriorityCount:   1,
		LastFeedbackType:      "thumb",
		LastFeedbackScore:     0.5,
		LastFeedbackAt:        "2026-04-11T00:00:00Z",
		LastMetricID:          "m1",
		LastMetricScore:       0.8,
		TopReasonCodes:        []string{"a", "b"},
		MetricAverages:        map[string]float64{"x": 0.1},
		LatestMetricScores:    map[string]float64{"y": 0.2},
		UpdatedAt:             "2026-04-11T01:00:00Z",
	}
	raw, err := json.Marshal(&in)
	if err != nil {
		t.Fatal(err)
	}
	var out AssistantLearningOpsSummaryView
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatal(err)
	}
	if out.UserID != in.UserID || out.TotalFeedbackCount != in.TotalFeedbackCount {
		t.Fatalf("mismatch after round-trip: %+v vs %+v", out, in)
	}
	if len(out.TopReasonCodes) != 2 || out.MetricAverages["x"] != 0.1 {
		t.Fatalf("nested fields: %+v", out)
	}
}

func TestAssistantLearningOpsSummaryView_DecodeSharedFixture(t *testing.T) {
	// Shared with contracts/metadata/assistant/assistant_run/fixtures/ (F5).
	rel := filepath.Join(
		"..", "..", "..", "..", "..",
		"contracts", "metadata", "assistant", "assistant_run", "fixtures",
		"assistant_learning_ops_summary.sample.json",
	)
	raw, err := os.ReadFile(rel)
	if err != nil {
		t.Fatalf("read fixture %s: %v", rel, err)
	}
	var v AssistantLearningOpsSummaryView
	if err := json.Unmarshal(raw, &v); err != nil {
		t.Fatal(err)
	}
	if v.UserID != "user_fixture_1" || len(v.TopReasonCodes) != 2 {
		t.Fatalf("fixture decode: %+v", v)
	}
}
