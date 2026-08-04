// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md#gwt-001
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
			store.release.ReleaseDigest != release.ReleaseDigest {
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
	releaseDigest string,
) (model.Release, bool, error) {
	if store.release.PolicyID == policyID &&
		store.release.ReleaseDigest == releaseDigest {
		return store.release, true, nil
	}
	return model.Release{}, false, nil
}

func TestPolicyReleaseIsImmutableDigestBoundAndIdempotent(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 26, 8, 0, 0, 0, time.UTC)
	input := model.Release{
		PolicyID:          "assistant-default",
		ReleaseDigest:     "pending",
		DefaultTemplateID: "default",
		Templates: []model.Template{{
			TemplateID:      "default",
			SkillID:         "assistant.general",
			DomainID:        "assistant",
			PromptPolicy:    "answer with grounded citations",
			AllowedTools:    []string{"search", "search"},
			SearchIntensity: "medium",
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
	input.ReleaseDigest = digest
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
	changed.Templates = append([]model.Template(nil), input.Templates...)
	changed.Templates[0].PromptPolicy = "changed policy content"
	if _, err := service.Stage(context.Background(), "stage-1", changed); !errors.Is(err, model.ErrDigestMismatch) {
		t.Fatalf("changed replay err=%v want digest mismatch", err)
	}
}

func TestPolicyReleaseRejectsUnsafeLearningContext(t *testing.T) {
	t.Parallel()
	_, err := model.Digest(model.Release{
		PolicyID:          "assistant-default",
		DefaultTemplateID: "default",
		Templates: []model.Template{{
			TemplateID:      "default",
			SkillID:         "assistant.general",
			DomainID:        "assistant",
			PromptPolicy:    "answer safely",
			SearchIntensity: "medium",
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

func TestPolicyReleaseRejectsRoutingIdentityThatDiffersFromItsTemplate(t *testing.T) {
	t.Parallel()
	base := model.Release{
		PolicyID:          "assistant-default",
		DefaultTemplateID: "travel-companion",
		Templates: []model.Template{{
			TemplateID:      "travel-companion",
			SkillID:         "travel_companion",
			DomainID:        "travel",
			PromptPolicy:    "ground shared travel decisions",
			AllowedTools:    []string{"app_search", "web_search"},
			SearchIntensity: "high",
		}},
		LearningContextPolicy: model.LearningContextPolicy{
			Enabled:                true,
			AllowedSignals:         []string{"feedback_counts"},
			AllowedMetricIDs:       []string{"turn_completion"},
			AllowedReasonCodes:     []string{"clear"},
			MinimumFeedbackSamples: 3,
			WindowDays:             30,
		},
	}
	for _, testCase := range []struct {
		name string
		rule model.RoutingRule
	}{
		{
			name: "retired skill id cannot alias the canonical travel template",
			rule: model.RoutingRule{
				RuleID: "travel-planning", Priority: 10,
				SkillID: "travel_planning", TemplateID: "travel-companion",
			},
		},
		{
			name: "foreign domain cannot alias the canonical travel template",
			rule: model.RoutingRule{
				RuleID: "foreign-domain", Priority: 10,
				DomainID: "life", SkillID: "travel_companion",
				TemplateID: "travel-companion",
			},
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			candidate := base
			candidate.RoutingRules = []model.RoutingRule{testCase.rule}
			if _, err := model.Digest(candidate); !errors.Is(err, model.ErrInvalidArgument) {
				t.Fatalf("routing identity mismatch error=%v want invalid argument", err)
			}
		})
	}
}
