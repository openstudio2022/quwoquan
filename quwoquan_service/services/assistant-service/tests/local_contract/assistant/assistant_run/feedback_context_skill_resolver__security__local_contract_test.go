// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/feedback-context-injection/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/feedbackcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	runtimecontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
	readerresource "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
)

type feedbackContextRunReader struct {
	run   runruntime.Run
	calls int
}

func (reader *feedbackContextRunReader) Load(
	context.Context,
	string,
) (runruntime.Run, error) {
	reader.calls++
	return reader.run, nil
}

func TestFeedbackContextSkillResolverProjectsOnlyModelSafeFrozenAggregates(
	t *testing.T,
) {
	t.Parallel()
	now := time.Now().UTC().Add(-time.Minute)
	runs := &feedbackContextRunReader{run: feedbackContextRun(now)}
	registry := feedbackContextRuntimeRegistry(t, runs)
	profile := feedbackContextProfile()
	snapshot, err := application.NewAssembler(
		registry,
		application.ConsentReaderFunc(func(
			_ context.Context,
			ownerID string,
			skillID string,
			scopes []string,
		) (bool, error) {
			return ownerID == "account-1" && skillID == "travel_companion" &&
				len(scopes) == 1 && scopes[0] == feedbackConsentScope, nil
		}),
	).Assemble(t.Context(), profile, application.AssembleRequest{
		RunID:              "run-feedback",
		OwnerID:            "account-1",
		SkillID:            "travel_companion",
		Visibility:         application.DeliveryPersonal,
		AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
	})
	if err != nil {
		t.Fatal(err)
	}
	if runs.calls != 1 || len(snapshot.Segments) != 1 || len(snapshot.Missing) != 0 {
		t.Fatalf("feedback context snapshot=%#v runLoads=%d", snapshot, runs.calls)
	}
	segment := snapshot.Segments[0]
	if segment.DescriptorID != "assistant.run_feedback_context" ||
		segment.SourceRef != "run:run-feedback:feedback-context" ||
		segment.Kind != "memory" ||
		segment.Sensitivity != generated.AssistantContextSensitivityPrivate {
		t.Fatalf("feedback segment boundary=%#v", segment)
	}
	encoded, err := json.Marshal(segment.Value)
	if err != nil {
		t.Fatal(err)
	}
	value := string(encoded)
	for _, forbidden := range []string{
		"consent-private-1",
		"definitionDigest",
		"sourceWatermarkSequence",
		"snapshotTrainingEligible",
		"secret_metric",
		"raw_comment",
	} {
		if strings.Contains(value, forbidden) {
			t.Fatalf("model context leaks forbidden feedback evidence %q: %s", forbidden, value)
		}
	}
	for _, expected := range []string{
		`"decision":"injected"`,
		`"feedbackSampleCount":7`,
		`"positiveFeedbackCount":5`,
		`"metricId":"turn_completion"`,
		`"reasonCode":"clear"`,
	} {
		if !strings.Contains(value, expected) {
			t.Fatalf("model context misses %s: %s", expected, value)
		}
	}
}

func TestFeedbackContextSkillResolverIsExcludedBeforeSharedResolution(
	t *testing.T,
) {
	t.Parallel()
	runs := &feedbackContextRunReader{run: feedbackContextRun(time.Now().UTC())}
	registry := feedbackContextRuntimeRegistry(t, runs)
	snapshot, err := application.NewAssembler(
		registry,
		application.ConsentReaderFunc(func(
			context.Context,
			string,
			string,
			[]string,
		) (bool, error) {
			return true, nil
		}),
	).Assemble(t.Context(), feedbackContextProfile(), application.AssembleRequest{
		RunID:              "run-feedback",
		OwnerID:            "account-1",
		SkillID:            "travel_companion",
		Visibility:         application.DeliveryShared,
		AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
	})
	if err != nil {
		t.Fatal(err)
	}
	if runs.calls != 0 || len(snapshot.Segments) != 0 || len(snapshot.Missing) != 0 {
		t.Fatalf(
			"private feedback crossed shared surface: loads=%d snapshot=%#v",
			runs.calls,
			snapshot,
		)
	}
}

func TestFeedbackContextSkillResolverRejectsUnrecognizedDecisionPayload(
	t *testing.T,
) {
	t.Parallel()
	run := feedbackContextRun(time.Now().UTC().Add(-time.Minute))
	run.FeedbackContextSnapshot.Decision = "raw private correction text"
	runs := &feedbackContextRunReader{run: run}
	registry := feedbackContextRuntimeRegistry(t, runs)
	snapshot, err := application.NewAssembler(
		registry,
		application.ConsentReaderFunc(func(
			context.Context,
			string,
			string,
			[]string,
		) (bool, error) {
			return true, nil
		}),
	).Assemble(t.Context(), feedbackContextProfile(), application.AssembleRequest{
		RunID:              "run-feedback",
		OwnerID:            "account-1",
		SkillID:            "travel_companion",
		Visibility:         application.DeliveryPersonal,
		AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
	})
	if err != nil {
		t.Fatal(err)
	}
	if runs.calls != 1 || len(snapshot.Segments) != 0 || len(snapshot.Missing) != 0 {
		t.Fatalf("unrecognized decision was projected: loads=%d snapshot=%#v", runs.calls, snapshot)
	}
}

func feedbackContextRuntimeRegistry(
	t *testing.T,
	runs *feedbackContextRunReader,
) *application.ResolverRegistry {
	t.Helper()
	descriptors, err := runtimecontext.RuntimeDescriptors()
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := readerresource.NewCatalog(descriptors)
	if err != nil {
		t.Fatal(err)
	}
	registry, err := runtimecontext.NewRuntimeRegistry(catalog, runs, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	return registry
}

func feedbackContextProfile() application.Profile {
	profile := application.Profile{
		ProfileID: "context.travel_companion.feedback",
		Requirements: []application.Requirement{{
			SlotID:              "feedback_context",
			AcceptedSourceKinds: []string{"memory"},
			Authority:           generated.AssistantContextAuthorityDomainCanonical,
			Sensitivity:         generated.AssistantContextSensitivityPrivate,
			ConsentScopes:       []string{feedbackConsentScope},
			TokenBudget:         256,
			ResolverRef:         feedbackcontext.ResolverRef,
			FallbackPolicy:      "omit",
		}},
	}
	profile.AssetDigest = canonicalFixtureDigest(profile)
	return profile
}

func feedbackContextRun(now time.Time) runruntime.Run {
	return runruntime.Run{
		RunID:     "run-feedback",
		CreatedAt: now,
		FrozenPolicySelection: runruntime.FrozenPolicySelection{
			LearningContextPolicy: runruntime.FrozenLearningContextPolicy{
				AllowedSignals:     []string{"feedback_counts", "metric_summaries", "top_reason_codes"},
				AllowedMetricIDs:   []string{"turn_completion"},
				AllowedReasonCodes: []string{"clear"},
			},
		},
		FeedbackContextSnapshot: assistantmodel.AssistantFeedbackContextSnapshot{
			Decision:                 "injected",
			ConsentID:                "consent-private-1",
			DefinitionDigest:         "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			SourceWatermarkSequence:  42,
			WindowDays:               30,
			FeedbackSampleCount:      7,
			PositiveFeedbackCount:    5,
			NegativeFeedbackCount:    2,
			TextFeedbackCount:        1,
			SnapshotTrainingEligible: true,
			Metrics: []assistantmodel.AssistantFeedbackMetricSummary{
				{MetricID: "turn_completion", SampleCount: 7, Average: 0.75, Latest: 1},
				{MetricID: "secret_metric", SampleCount: 1, Average: 1, Latest: 1},
			},
			Reasons: []assistantmodel.AssistantFeedbackReasonSummary{
				{ReasonCode: "clear", Count: 5},
				{ReasonCode: "raw_comment", Count: 1},
			},
		},
	}
}
