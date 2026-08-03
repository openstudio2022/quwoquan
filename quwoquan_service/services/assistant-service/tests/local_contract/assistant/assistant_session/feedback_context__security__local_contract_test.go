// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/feedback-context-injection/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	orchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	ports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
)

type learningProjectionReaderStub struct {
	projection *learningmodel.LearningProjection
	err        error
}

type consentStoreStub struct {
	consents []consentmodel.Consent
	err      error
}

func (store consentStoreStub) ListActiveConsents(
	context.Context,
	string,
) ([]consentmodel.Consent, error) {
	return store.consents, store.err
}

func (reader learningProjectionReaderStub) GetLearningProjection(
	context.Context,
	string,
) (*learningmodel.LearningProjection, error) {
	return reader.projection, reader.err
}

func (reader learningProjectionReaderStub) GetLearningProjectionForPersona(
	context.Context,
	string,
	string,
) (*learningmodel.LearningProjection, error) {
	return reader.projection, reader.err
}

func TestResolveFeedbackContextSnapshotFailsClosedWithoutConsent(t *testing.T) {
	t.Parallel()
	service := orchestration.NewAssistantService(
		consentStoreStub{},
		nil,
		orchestration.WithLearningProjectionReader(learningProjectionReaderStub{
			projection: eligibleLearningProjection(),
		}),
	)
	snapshot := service.ResolveFeedbackContextSnapshot(
		context.Background(),
		"account-1",
		"persona-1",
		enabledLearningContextPolicy(),
		time.Now().UTC(),
	)

	if snapshot.Decision != "consent_missing_or_opted_out" ||
		snapshot.FeedbackSampleCount != 0 ||
		len(snapshot.Metrics) != 0 {
		t.Fatalf("snapshot = %+v, want consent-required without aggregates", snapshot)
	}
}

func TestResolveFeedbackContextSnapshotFiltersPolicyAllowlists(t *testing.T) {
	t.Parallel()
	projection := eligibleLearningProjection()
	service := orchestration.NewAssistantService(
		consentStoreStub{consents: []consentmodel.Consent{{
			ID:            "consent-1",
			AccountID:     "account-1",
			SkillID:       "assistant_learning",
			GrantedScopes: []string{"assistant_learning_context"},
			GrantedAt:     time.Now().UTC(),
		}}},
		nil,
		orchestration.WithLearningProjectionReader(learningProjectionReaderStub{
			projection: projection,
		}),
	)
	snapshot := service.ResolveFeedbackContextSnapshot(
		context.Background(),
		"account-1",
		"persona-1",
		enabledLearningContextPolicy(),
		time.Now().UTC(),
	)

	if snapshot.Decision != "injected" {
		t.Fatalf("decision = %q, want injected", snapshot.Decision)
	}
	if snapshot.ConsentID != "consent-1" || snapshot.ConsentGrantedAt.IsZero() {
		t.Fatalf("consent audit snapshot = %+v", snapshot)
	}
	if len(snapshot.Metrics) != 1 ||
		snapshot.Metrics[0].MetricID != "turn_completion" {
		t.Fatalf("metrics = %+v, want only allowlisted metric", snapshot.Metrics)
	}
	if len(snapshot.Reasons) != 1 || snapshot.Reasons[0].ReasonCode != "clear" {
		t.Fatalf("reasons = %+v, want only allowlisted reason", snapshot.Reasons)
	}
	if snapshot.SnapshotTrainingEligible {
		t.Fatal("feedback context must not become training eligible by default")
	}
}

func TestResolveFeedbackContextSnapshotFailsClosedForUntrustedOrUnavailableProjection(
	t *testing.T,
) {
	t.Parallel()
	ownerMismatch := eligibleLearningProjection()
	ownerMismatch.PersonaID = "persona-other"
	insufficientSamples := eligibleLearningProjection()
	insufficientSamples.DailyBuckets = map[string]learningmodel.LearningProjectionBucket{
		time.Now().UTC().Format("2006-01-02"): {
			FeedbackCount: 0,
		},
	}
	cases := []struct {
		name     string
		consents consentStoreStub
		reader   ports.LearningProjectionReader
		want     string
	}{
		{
			name:     "consent reader unavailable",
			consents: consentStoreStub{err: errors.New("consent store unavailable")},
			reader:   learningProjectionReaderStub{projection: eligibleLearningProjection()},
			want:     "consent_unavailable",
		},
		{
			name:     "projection unavailable",
			consents: learningContextConsentStore(),
			reader: learningProjectionReaderStub{
				err: errors.New("projection store unavailable"),
			},
			want: "projection_unavailable",
		},
		{
			name:     "owner mismatch",
			consents: learningContextConsentStore(),
			reader:   learningProjectionReaderStub{projection: ownerMismatch},
			want:     "owner_mismatch",
		},
		{
			name:     "insufficient samples",
			consents: learningContextConsentStore(),
			reader:   learningProjectionReaderStub{projection: insufficientSamples},
			want:     "insufficient_samples",
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			service := orchestration.NewAssistantService(
				testCase.consents,
				nil,
				orchestration.WithLearningProjectionReader(testCase.reader),
			)
			snapshot := service.ResolveFeedbackContextSnapshot(
				t.Context(),
				"account-1",
				"persona-1",
				enabledLearningContextPolicy(),
				time.Now().UTC(),
			)
			if snapshot.Decision != testCase.want ||
				snapshot.FeedbackSampleCount != 0 ||
				snapshot.PositiveFeedbackCount != 0 ||
				snapshot.NegativeFeedbackCount != 0 ||
				len(snapshot.Metrics) != 0 ||
				len(snapshot.Reasons) != 0 ||
				snapshot.SnapshotTrainingEligible {
				t.Fatalf(
					"snapshot = %+v, want fail-closed decision %q without aggregates",
					snapshot,
					testCase.want,
				)
			}
		})
	}
}

func learningContextConsentStore() consentStoreStub {
	return consentStoreStub{consents: []consentmodel.Consent{{
		ID:            "consent-learning-context",
		AccountID:     "account-1",
		SkillID:       "assistant_learning",
		GrantedScopes: []string{"assistant_learning_context"},
		GrantedAt:     time.Unix(1, 0).UTC(),
	}}}
}

func enabledLearningContextPolicy() assistant.AssistantFrozenLearningContextPolicy {
	return assistant.AssistantFrozenLearningContextPolicy{
		Enabled: true,
		AllowedSignals: []string{
			"feedback_counts",
			"metric_summaries",
			"top_reason_codes",
		},
		AllowedMetricIDs:         []string{"turn_completion"},
		AllowedReasonCodes:       []string{"clear"},
		MinimumFeedbackSamples:   1,
		WindowDays:               30,
		SnapshotTrainingEligible: false,
	}
}

func eligibleLearningProjection() *learningmodel.LearningProjection {
	now := time.Now().UTC()
	return &learningmodel.LearningProjection{
		UserID:            "account-1",
		PersonaID:         "persona-1",
		DefinitionDigest:  learningmodel.LearningProjectionDefinitionDigest,
		WatermarkSequence: 12,
		DailyBuckets: map[string]learningmodel.LearningProjectionBucket{
			now.Format("2006-01-02"): {
				FeedbackCount:         2,
				PositiveFeedbackCount: 1,
				NegativeFeedbackCount: 1,
				MetricSampleCounts: map[string]int64{
					"turn_completion": 2,
					"privacy_comfort": 1,
				},
				MetricScoreSums: map[string]float64{
					"turn_completion": 2,
					"privacy_comfort": 0,
				},
				LatestMetricScores: map[string]float64{
					"turn_completion": 1,
					"privacy_comfort": 0,
				},
				ReasonCodeCounts: map[string]int64{
					"clear":       1,
					"raw_comment": 1,
				},
			},
		},
	}
}
