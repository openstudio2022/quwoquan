// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/feedback-context-injection/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"errors"
	"testing"
	"time"

	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/feedbackcontext"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

const feedbackConsentScope = "assistant.learning.feedback_context.read"

type feedbackProjectionReaderStub struct {
	projection *learningmodel.LearningProjection
	err        error
}

func (reader feedbackProjectionReaderStub) GetLearningProjectionForPersona(
	context.Context,
	string,
	string,
) (*learningmodel.LearningProjection, error) {
	return reader.projection, reader.err
}

type feedbackConsentReaderStub struct {
	consents []consentmodel.Consent
	err      error
}

type frozenFeedbackManifestLoader struct {
	identity skillpkg.PackageReleaseIdentity
}

func (loader *frozenFeedbackManifestLoader) Load(
	ctx context.Context,
) ([]skillpkg.Manifest, error) {
	identity, ok := skillpkg.PackageReleaseFromContext(ctx)
	if !ok {
		return nil, errors.New("feedback manifest load is not release-frozen")
	}
	loader.identity = identity
	return []skillpkg.Manifest{{
		SkillID: "travel_companion",
		ContextProfile: skillpkg.ContextProfile{Requirements: []skillpkg.ContextRequirement{{
			SlotID:        "feedback_context",
			ResolverRef:   feedbackcontext.ResolverRef,
			ConsentScopes: []string{feedbackConsentScope},
		}}},
	}}, nil
}

func (reader feedbackConsentReaderStub) ListActiveConsents(
	context.Context,
	string,
) ([]consentmodel.Consent, error) {
	return reader.consents, reader.err
}

func TestFeedbackContextResolverUsesCurrentSkillConsentAndPolicyAllowlists(
	t *testing.T,
) {
	t.Parallel()
	frozenAt := time.Date(2026, time.August, 4, 8, 0, 0, 0, time.UTC)
	projection := eligibleFeedbackProjection(frozenAt)
	resolver := feedbackcontext.NewResolver(
		feedbackConsentReaderStub{consents: []consentmodel.Consent{{
			ID:            "consent-travel",
			AccountID:     "account-1",
			SkillID:       "travel_companion",
			GrantedScopes: []string{feedbackConsentScope},
			GrantedAt:     frozenAt.Add(-time.Hour),
		}}},
		feedbackProjectionReaderStub{projection: projection},
	)

	snapshot := resolver.Resolve(t.Context(), feedbackcontext.Request{
		AccountID:    "account-1",
		PersonaID:    "persona-1",
		SkillID:      "travel_companion",
		ConsentScope: feedbackConsentScope,
		Policy:       enabledFeedbackPolicy(),
		FrozenAt:     frozenAt,
	})

	if snapshot.Decision != "injected" || snapshot.ConsentID != "consent-travel" {
		t.Fatalf("snapshot = %+v, want current Skill consent", snapshot)
	}
	if snapshot.FeedbackSampleCount != 2 || snapshot.PositiveFeedbackCount != 1 ||
		len(snapshot.Metrics) != 1 || snapshot.Metrics[0].MetricID != "turn_completion" ||
		len(snapshot.Reasons) != 1 || snapshot.Reasons[0].ReasonCode != "clear" {
		t.Fatalf("snapshot = %+v, want allowlisted aggregates only", snapshot)
	}
	if snapshot.SnapshotTrainingEligible {
		t.Fatal("feedback context must not become training eligible")
	}
}

func TestFeedbackContextResolverUsesTheSameFrozenSkillPackageAsRun(t *testing.T) {
	t.Parallel()
	frozenAt := time.Date(2026, time.August, 4, 9, 0, 0, 0, time.UTC)
	loader := &frozenFeedbackManifestLoader{}
	resolver := feedbackcontext.NewActiveSkillResolver(
		feedbackcontext.NewResolver(
			feedbackConsentReaderStub{consents: feedbackConsent(frozenAt)},
			feedbackProjectionReaderStub{projection: eligibleFeedbackProjection(frozenAt)},
		),
		loader,
	)
	const releaseDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	snapshot := resolver.ResolveFeedbackContext(
		t.Context(),
		"account-1",
		"persona-1",
		"travel_companion",
		"personal",
		"assistant.session.skills",
		releaseDigest,
		enabledFeedbackPolicy(),
		frozenAt,
	)
	if snapshot.Decision != "injected" ||
		loader.identity.PackageID != "assistant.session.skills" ||
		loader.identity.ReleaseDigest != releaseDigest {
		t.Fatalf(
			"feedback scope did not use frozen package identity: snapshot=%+v identity=%+v",
			snapshot,
			loader.identity,
		)
	}
}

func TestFeedbackContextResolverFailsClosedWithoutExactSkillScope(t *testing.T) {
	t.Parallel()
	frozenAt := time.Date(2026, time.August, 4, 8, 0, 0, 0, time.UTC)
	resolver := feedbackcontext.NewResolver(
		feedbackConsentReaderStub{consents: []consentmodel.Consent{{
			ID:            "consent-other-skill",
			AccountID:     "account-1",
			SkillID:       "weather",
			GrantedScopes: []string{feedbackConsentScope},
			GrantedAt:     frozenAt.Add(-time.Hour),
		}}},
		feedbackProjectionReaderStub{projection: eligibleFeedbackProjection(frozenAt)},
	)

	snapshot := resolver.Resolve(t.Context(), feedbackcontext.Request{
		AccountID:    "account-1",
		PersonaID:    "persona-1",
		SkillID:      "travel_companion",
		ConsentScope: feedbackConsentScope,
		Policy:       enabledFeedbackPolicy(),
		FrozenAt:     frozenAt,
	})
	assertNoFeedbackAggregates(t, snapshot, "consent_missing_or_opted_out")
}

func TestFeedbackContextResolverRejectsUntrustedOrUnavailableSources(t *testing.T) {
	t.Parallel()
	frozenAt := time.Date(2026, time.August, 4, 8, 0, 0, 0, time.UTC)
	ownerMismatch := eligibleFeedbackProjection(frozenAt)
	ownerMismatch.PersonaID = "persona-other"
	untrusted := eligibleFeedbackProjection(frozenAt)
	untrusted.DefinitionDigest = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
	insufficient := eligibleFeedbackProjection(frozenAt)
	insufficient.DailyBuckets = map[string]learningmodel.LearningProjectionBucket{}
	cases := []struct {
		name       string
		consentErr error
		projection *learningmodel.LearningProjection
		projectErr error
		want       string
	}{
		{name: "consent unavailable", consentErr: errors.New("down"), projection: eligibleFeedbackProjection(frozenAt), want: "consent_unavailable"},
		{name: "projection unavailable", projectErr: errors.New("down"), want: "projection_unavailable"},
		{name: "owner mismatch", projection: ownerMismatch, want: "owner_mismatch"},
		{name: "definition mismatch", projection: untrusted, want: "projection_untrusted"},
		{name: "insufficient samples", projection: insufficient, want: "insufficient_samples"},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			resolver := feedbackcontext.NewResolver(
				feedbackConsentReaderStub{
					consents: feedbackConsent(frozenAt),
					err:      testCase.consentErr,
				},
				feedbackProjectionReaderStub{
					projection: testCase.projection,
					err:        testCase.projectErr,
				},
			)
			snapshot := resolver.Resolve(t.Context(), feedbackcontext.Request{
				AccountID:    "account-1",
				PersonaID:    "persona-1",
				SkillID:      "travel_companion",
				ConsentScope: feedbackConsentScope,
				Policy:       enabledFeedbackPolicy(),
				FrozenAt:     frozenAt,
			})
			assertNoFeedbackAggregates(t, snapshot, testCase.want)
		})
	}
}

func assertNoFeedbackAggregates(
	t *testing.T,
	snapshot assistantmodel.AssistantFeedbackContextSnapshot,
	want string,
) {
	t.Helper()
	if snapshot.Decision != want || snapshot.FeedbackSampleCount != 0 ||
		snapshot.PositiveFeedbackCount != 0 || snapshot.NegativeFeedbackCount != 0 ||
		len(snapshot.Metrics) != 0 || len(snapshot.Reasons) != 0 ||
		snapshot.SnapshotTrainingEligible {
		t.Fatalf("snapshot = %+v, want fail-closed %q", snapshot, want)
	}
}

func feedbackConsent(frozenAt time.Time) []consentmodel.Consent {
	return []consentmodel.Consent{{
		ID:            "consent-travel",
		AccountID:     "account-1",
		SkillID:       "travel_companion",
		GrantedScopes: []string{feedbackConsentScope},
		GrantedAt:     frozenAt.Add(-time.Hour),
	}}
}

func enabledFeedbackPolicy() assistantmodel.AssistantFrozenLearningContextPolicy {
	return assistantmodel.AssistantFrozenLearningContextPolicy{
		Enabled:                  true,
		AllowedSignals:           []string{"feedback_counts", "metric_summaries", "top_reason_codes"},
		AllowedMetricIDs:         []string{"turn_completion"},
		AllowedReasonCodes:       []string{"clear"},
		MinimumFeedbackSamples:   1,
		WindowDays:               30,
		SnapshotTrainingEligible: false,
	}
}

func eligibleFeedbackProjection(frozenAt time.Time) *learningmodel.LearningProjection {
	return &learningmodel.LearningProjection{
		UserID:            "account-1",
		PersonaID:         "persona-1",
		DefinitionDigest:  learningmodel.LearningProjectionDefinitionDigest,
		WatermarkSequence: 12,
		DailyBuckets: map[string]learningmodel.LearningProjectionBucket{
			frozenAt.Format("2006-01-02"): {
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
			frozenAt.Add(24 * time.Hour).Format("2006-01-02"): {
				FeedbackCount: 100,
			},
		},
	}
}
