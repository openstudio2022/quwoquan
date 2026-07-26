// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md
package assistant_policy_release_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
)

type memoryStore struct {
	release model.Release
	command string
}

func (store *memoryStore) Stage(
	_ context.Context,
	release model.Release,
	commandID string,
) (model.Release, bool, error) {
	if store.command != "" {
		if store.command != commandID ||
			store.release.CanonicalDigest != release.CanonicalDigest {
			return model.Release{}, false, model.ErrIdempotencyConflict
		}
		return store.release, true, nil
	}
	store.command = commandID
	store.release = release
	return release, false, nil
}

func (store *memoryStore) Get(
	_ context.Context,
	policyID string,
	releaseVersion string,
) (model.Release, bool, error) {
	if store.release.PolicyID == policyID &&
		store.release.ReleaseVersion == releaseVersion {
		return store.release, true, nil
	}
	return model.Release{}, false, nil
}

func TestPolicyReleaseIsImmutableDigestBoundAndIdempotent(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 26, 8, 0, 0, 0, time.UTC)
	input := model.Release{
		PolicyID:          "assistant-default",
		ReleaseVersion:    "2026-07-26.1",
		CanonicalDigest:   "pending",
		DefaultTemplateID: "default",
		Templates: []model.Template{{
			TemplateID:      "default",
			SkillID:         "assistant.general",
			DomainID:        "assistant",
			PromptPolicy:    "answer with grounded citations",
			AllowedTools:    []string{"search", "search"},
			SearchIntensity: "balanced",
		}},
		RoutingRules: []model.RoutingRule{},
		LearningContextPolicy: model.LearningContextPolicy{
			Enabled:                  true,
			AllowedSignals:           []string{"metric_summaries", "feedback_counts", "metric_summaries"},
			AllowedMetricIDs:         []string{"turn_completion"},
			AllowedReasonCodes:       []string{"clear"},
			MinimumFeedbackSamples:   3,
			WindowDays:               30,
			SnapshotTrainingEligible: false,
		},
	}
	digest, err := model.Digest(input)
	if err != nil {
		t.Fatal(err)
	}
	input.CanonicalDigest = digest
	store := &memoryStore{}
	service := application.NewService(store, func() time.Time { return now })

	first, err := service.Stage(context.Background(), "stage-1", input)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.Stage(context.Background(), "stage-1", input)
	if err != nil {
		t.Fatal(err)
	}
	if first.Replayed || !replay.Replayed ||
		first.Release.StagedAt != now ||
		first.Release.AggregateVersion != 1 ||
		len(first.Release.Templates[0].AllowedTools) != 1 ||
		len(first.Release.LearningContextPolicy.AllowedSignals) != 2 {
		t.Fatalf("first=%+v replay=%+v", first, replay)
	}

	changed := input
	changed.ReleaseVersion = "2026-07-26.2"
	changed.CanonicalDigest = digest
	if _, err := service.Stage(context.Background(), "stage-1", changed); !errors.Is(err, model.ErrDigestMismatch) {
		t.Fatalf("changed replay err=%v want digest mismatch", err)
	}
}

func TestPolicyReleaseRejectsUnsafeLearningContext(t *testing.T) {
	t.Parallel()
	_, err := model.Digest(model.Release{
		PolicyID:          "assistant-default",
		ReleaseVersion:    "2026-07-26.1",
		DefaultTemplateID: "default",
		Templates: []model.Template{{
			TemplateID:      "default",
			SkillID:         "assistant.general",
			DomainID:        "assistant",
			PromptPolicy:    "answer safely",
			SearchIntensity: "balanced",
		}},
		LearningContextPolicy: model.LearningContextPolicy{
			Enabled:                true,
			AllowedSignals:         []string{"raw_feedback_text"},
			MinimumFeedbackSamples: 0,
			WindowDays:             365,
		},
	})
	if err == nil {
		t.Fatal("unsafe learning context policy must be rejected")
	}
}
