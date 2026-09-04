package local_contract

import (
	"bytes"
	"encoding/json"
	"testing"
	"time"

	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
)

func TestBuildRejectsMixedFactTypePayloads(t *testing.T) {
	t.Parallel()
	base := learningmodel.AppendCommand{
		EventID:          "fact-1",
		FactType:         learningmodel.FactTypeUserFeedback,
		AssistantTurnID:  "turn-1",
		ReferralSource:   "assistant_session",
		DomainID:         "assistant",
		FeedbackType:     "useful",
		TrainingEligible: false,
		OccurredAt:       time.Now().UTC(),
	}
	trusted := learningmodel.TrustedContext{UserID: "account-1", PersonaID: "persona-1"}

	withMetric := base
	withMetric.MetricID = "turn_completion"
	withMetric.MetricValue = 1
	withMetric.MetricSource = "client"
	if _, err := learningmodel.Build(withMetric, trusted, time.Now().UTC()); err == nil {
		t.Fatal("public feedback must not smuggle service scorecard fields")
	}

	interactionWithFeedback := base
	interactionWithFeedback.FactType = learningmodel.FactTypeInteractionOutcome
	interactionWithFeedback.EventType = "action_click"
	if _, err := learningmodel.Build(
		interactionWithFeedback,
		trusted,
		time.Now().UTC(),
	); err == nil {
		t.Fatal("interaction outcome must not include feedback fields")
	}

	scorecardWithText := base
	scorecardWithText.FactType = learningmodel.FactTypeServiceScorecard
	scorecardWithText.FeedbackType = ""
	scorecardWithText.MetricID = "turn_completion"
	scorecardWithText.MetricValue = 1
	scorecardWithText.MetricSource = "service_auto"
	scorecardWithText.QueryText = "raw query"
	if _, err := learningmodel.Build(scorecardWithText, trusted, time.Now().UTC()); err == nil {
		t.Fatal("service scorecard must not include raw text")
	}
}

func TestRedactedPayloadKeepsTrustedContextWithoutRawText(t *testing.T) {
	t.Parallel()
	fact, err := learningmodel.Build(
		learningmodel.AppendCommand{
			EventID:          "fact-context",
			FactType:         learningmodel.FactTypeUserFeedback,
			AssistantTurnID:  "turn-1",
			ReferralSource:   "assistant_session",
			DomainID:         "assistant",
			FeedbackType:     "text",
			QueryText:        "sensitive user query",
			FeedbackText:     "private correction",
			TrainingEligible: false,
			OccurredAt:       time.Now().UTC(),
		},
		learningmodel.TrustedContext{
			UserID:           "account-1",
			PersonaID:        "persona-1",
			TraceID:          "trace-1",
			ClientSessionID:  "client-session-1",
			PageVisitID:      "visit-1",
			PageID:           "assistant",
			SurfaceID:        "assistantFeedback",
			RouteID:          "assistantSession",
			OperationID:      "AppendAssistantLearningFact",
			ExperimentBucket: "policy-a",
		},
		time.Now().UTC(),
	)
	if err != nil {
		t.Fatalf("Build() error = %v", err)
	}
	payload := fact.RedactedPayload()
	if payload.TraceID != "trace-1" ||
		payload.PageVisitID != "visit-1" ||
		payload.ExperimentBucket != "policy-a" ||
		payload.QueryTextDigest == "" {
		t.Fatalf("trusted redacted context = %+v", payload)
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal redacted payload: %v", err)
	}
	for _, raw := range [][]byte{
		[]byte("sensitive user query"),
		[]byte("private correction"),
	} {
		if bytes.Contains(encoded, raw) {
			t.Fatalf("redacted payload leaked raw text: %s", encoded)
		}
	}
}

func TestSortedProjectionReasonCodesUsesCanonicalOrder(t *testing.T) {
	t.Parallel()

	got := learningmodel.SortedProjectionReasonCodes(map[string]int64{
		"quality":    2,
		"completion": 1,
	})
	if len(got) != 2 || got[0] != "completion" || got[1] != "quality" {
		t.Fatalf("sorted projection reason codes = %v", got)
	}
}
