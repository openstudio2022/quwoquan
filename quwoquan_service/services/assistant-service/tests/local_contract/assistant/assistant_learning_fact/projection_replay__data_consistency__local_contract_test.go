package local_contract

import (
	"reflect"
	"testing"
	"time"

	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
)

func TestApplyLearningFactDeterministicReplay(t *testing.T) {
	t.Parallel()
	facts := []learningmodel.Fact{
		{
			StorageID:       "feedback:1",
			EventID:         "feedback",
			EventVersion:    1,
			AppendSequence:  1,
			FactType:        learningmodel.FactTypeUserFeedback,
			UserID:          "account-1",
			PersonaID:       "persona-1",
			AssistantTurnID: "turn-1",
			FeedbackType:    "useful",
			FeedbackScore:   1,
			ReasonCodes:     []string{"clear"},
			OccurredAt:      time.Date(2026, 7, 26, 1, 2, 3, 0, time.UTC),
		},
		{
			StorageID:       "score:1",
			EventID:         "score",
			EventVersion:    1,
			AppendSequence:  2,
			FactType:        learningmodel.FactTypeServiceScorecard,
			UserID:          "account-1",
			PersonaID:       "persona-1",
			AssistantTurnID: "turn-1",
			MetricID:        "turn_completion",
			MetricValue:     1,
			MetricSource:    "service_auto",
			OccurredAt:      time.Date(2026, 7, 26, 1, 3, 3, 0, time.UTC),
		},
	}
	replay := func() learningmodel.LearningProjection {
		var projection learningmodel.LearningProjection
		for _, fact := range facts {
			projection = learningmodel.ApplyLearningFact(projection, fact)
		}
		return projection
	}
	first := replay()
	second := replay()
	if !reflect.DeepEqual(first, second) {
		t.Fatalf("ordered replay is not deterministic:\nfirst=%+v\nsecond=%+v", first, second)
	}
	if first.WatermarkSequence != 2 || first.Revision != 2 {
		t.Fatalf(
			"watermark/revision = %d/%d, want 2/2",
			first.WatermarkSequence,
			first.Revision,
		)
	}
	if first.PositiveFeedbackCount != 1 ||
		first.MetricSampleCounts["turn_completion"] != 1 {
		t.Fatalf("projection did not aggregate facts: %+v", first)
	}
}

func TestLearningProjectionContainsOnlyRedactedAggregates(t *testing.T) {
	t.Parallel()
	fact := learningmodel.Fact{
		StorageID:       "feedback:1",
		EventID:         "feedback",
		EventVersion:    1,
		AppendSequence:  1,
		FactType:        learningmodel.FactTypeUserFeedback,
		UserID:          "account-1",
		PersonaID:       "persona-1",
		AssistantTurnID: "turn-1",
		FeedbackType:    "text",
		FeedbackScore:   -1,
		FeedbackText:    "raw feedback must not be projected",
		QueryText:       "raw query must not be projected",
		AnswerText:      "raw answer must not be projected",
		CorrectionText:  "raw correction must not be projected",
		OccurredAt:      time.Date(2026, 7, 26, 1, 2, 3, 0, time.UTC),
	}
	projection := learningmodel.ApplyLearningFact(learningmodel.LearningProjection{}, fact)
	value := reflect.ValueOf(projection)
	typ := value.Type()
	for index := 0; index < value.NumField(); index++ {
		switch typ.Field(index).Name {
		case "FeedbackText", "QueryText", "AnswerText", "CorrectionText":
			t.Fatalf("raw sensitive field %s leaked into projection", typ.Field(index).Name)
		}
	}
	if projection.TextFeedbackCount != 1 ||
		projection.TotalFeedbackCount != 1 {
		t.Fatalf("redacted counters were not retained: %+v", projection)
	}
}

func TestMergeLearningProjectionBuildsAccountOpsSummary(t *testing.T) {
	t.Parallel()
	aggregate := learningmodel.NewLearningProjectionAggregate(
		learningmodel.LearningProjectionDefinitionVersion,
		"account-1",
	)
	first := learningmodel.LearningProjection{
		UserID:                "account-1",
		PersonaID:             "persona-1",
		Revision:              2,
		WatermarkSequence:     3,
		TotalFeedbackCount:    2,
		PositiveFeedbackCount: 2,
		MetricSampleCounts:    map[string]int64{"turn_completion": 1},
		MetricScoreSums:       map[string]float64{"turn_completion": 1},
		LatestMetricScores:    map[string]float64{"turn_completion": 1},
		ReasonCodeCounts:      map[string]int64{"clear": 1},
		DailyBuckets:          map[string]learningmodel.LearningProjectionBucket{},
		UpdatedAt:             time.Date(2026, 7, 26, 2, 0, 0, 0, time.UTC),
		LastEventID:           "newest",
	}
	second := learningmodel.LearningProjection{
		UserID:                "account-1",
		PersonaID:             "persona-2",
		Revision:              1,
		WatermarkSequence:     2,
		TotalFeedbackCount:    1,
		NegativeFeedbackCount: 1,
		MetricSampleCounts:    map[string]int64{"turn_completion": 1},
		MetricScoreSums:       map[string]float64{"turn_completion": 0},
		LatestMetricScores:    map[string]float64{"turn_completion": 0},
		ReasonCodeCounts:      map[string]int64{"unclear": 1},
		DailyBuckets:          map[string]learningmodel.LearningProjectionBucket{},
		UpdatedAt:             time.Date(2026, 7, 26, 1, 0, 0, 0, time.UTC),
		LastEventID:           "older",
	}

	learningmodel.MergeLearningProjection(&aggregate, first)
	learningmodel.MergeLearningProjection(&aggregate, second)

	if aggregate.TotalFeedbackCount != 3 ||
		aggregate.PositiveFeedbackCount != 2 ||
		aggregate.NegativeFeedbackCount != 1 ||
		aggregate.MetricSampleCounts["turn_completion"] != 2 ||
		aggregate.LastEventID != "newest" ||
		aggregate.WatermarkSequence != 3 {
		t.Fatalf("unexpected account aggregate: %+v", aggregate)
	}
}
