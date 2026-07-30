// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/learning-event-ingestion/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/feedback-aggregation/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
)

type learningOpsProjectionReader struct {
	projection *learningmodel.LearningProjection
	err        error
}

func (reader learningOpsProjectionReader) GetLearningProjection(
	context.Context,
	string,
) (*learningmodel.LearningProjection, error) {
	return reader.projection, reader.err
}

func TestAssistantLearningOpsSummaryUsesObjectOwnedProjection(t *testing.T) {
	updatedAt := time.Date(2026, 7, 29, 9, 30, 0, 0, time.UTC)
	service := learningapplication.NewOpsQueryService(
		learningOpsProjectionReader{projection: &learningmodel.LearningProjection{
			UserID:                "u1",
			TotalFeedbackCount:    4,
			PositiveFeedbackCount: 2,
			NegativeFeedbackCount: 1,
			TextFeedbackCount:     1,
			HighPriorityCount:     1,
			MediumPriorityCount:   2,
			ReasonCodeCounts: map[string]int64{
				"incorrect": 3,
				"stale":     3,
				"verbose":   1,
			},
			MetricSampleCounts: map[string]int64{"groundedness": 2},
			MetricScoreSums:    map[string]float64{"groundedness": 7},
			LatestMetricScores: map[string]float64{"groundedness": 4},
			UpdatedAt:          updatedAt,
		}},
	)
	summary, err := service.GetLearningOpsSummary(t.Context(), "u1")
	if err != nil {
		t.Fatalf("get learning ops summary: %v", err)
	}
	if summary.UserID != "u1" ||
		summary.TotalFeedbackCount != 4 ||
		summary.MetricAverages["groundedness"] != 3.5 ||
		summary.LatestMetricScores["groundedness"] != 4 ||
		summary.UpdatedAt != updatedAt.Format(time.RFC3339) ||
		!reflect.DeepEqual(summary.TopReasonCodes, []string{"incorrect", "stale", "verbose"}) {
		t.Fatalf("unexpected object-owned learning summary: %+v", summary)
	}
}

func TestAssistantLearningOpsSummaryFailsClosedWhenProjectionUnavailable(t *testing.T) {
	service := learningapplication.NewOpsQueryService(
		learningOpsProjectionReader{err: errors.New("mongo unavailable")},
	)
	if _, err := service.GetLearningOpsSummary(t.Context(), "u1"); !errors.Is(err, learningapplication.ErrStoreUnavailable) {
		t.Fatalf("projection failure must map to unavailable, got %v", err)
	}
	if _, err := service.GetLearningOpsSummary(t.Context(), ""); !errors.Is(err, learningapplication.ErrUnauthorized) {
		t.Fatalf("missing trusted owner must fail closed, got %v", err)
	}
}

func TestAssistantLearningOpsSummaryViewJSONRoundTrip(t *testing.T) {
	in := learningmodel.AssistantLearningOpsSummaryView{
		UserID:                "u1",
		TotalFeedbackCount:    3,
		PositiveFeedbackCount: 2,
		NegativeFeedbackCount: 1,
		TopReasonCodes:        []string{"a", "b"},
		MetricAverages:        map[string]float64{"x": 0.1},
	}
	raw, err := json.Marshal(&in)
	if err != nil {
		t.Fatal(err)
	}
	var out learningmodel.AssistantLearningOpsSummaryView
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatal(err)
	}
	if out.UserID != in.UserID ||
		out.TotalFeedbackCount != in.TotalFeedbackCount ||
		len(out.TopReasonCodes) != 2 ||
		out.MetricAverages["x"] != 0.1 {
		t.Fatalf("mismatch after round-trip: %+v vs %+v", out, in)
	}
}

func TestAssistantLearningOpsSummaryViewDecodesSharedFixture(t *testing.T) {
	rel := filepath.Join(
		"..", "..", "..", "support", "contract_fixtures",
		"assistant_learning_ops_summary.sample.json",
	)
	raw, err := os.ReadFile(rel)
	if err != nil {
		t.Fatalf("read fixture %s: %v", rel, err)
	}
	var view learningmodel.AssistantLearningOpsSummaryView
	if err := json.Unmarshal(raw, &view); err != nil {
		t.Fatal(err)
	}
	if view.UserID != "user_fixture_1" || len(view.TopReasonCodes) != 2 {
		t.Fatalf("fixture decode: %+v", view)
	}
}
