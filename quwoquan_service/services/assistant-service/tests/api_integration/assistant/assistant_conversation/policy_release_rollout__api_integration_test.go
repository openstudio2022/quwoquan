// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/spec.md#sit-001
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md#gwt-001
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	releaseapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	releasemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
	policymessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/messaging"
	releasepersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/persistence"
	rolloutapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	rolloutmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
	rolloutpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/persistence"
)

func TestAssistantPolicyReleaseRolloutPersistsActivationAndRollback(
	t *testing.T,
) {
	resetIntegrationState(t)
	ctx := context.Background()
	releaseStore := releasepersistence.NewMongoStore(integrationMongoDB)
	if err := releaseStore.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure policy release indexes: %v", err)
	}
	rolloutStore := rolloutpersistence.NewMongoStore(integrationMongoDB)
	if err := rolloutStore.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure policy rollout indexes: %v", err)
	}
	releases := releaseapplication.NewService(releaseStore, nil)
	rollouts := rolloutapplication.NewService(rolloutStore, releases, nil)

	for _, version := range []string{"v1", "v2"} {
		release := policyReleaseForIntegration(version)
		digest, err := releasemodel.Digest(release)
		if err != nil {
			t.Fatalf("digest release %s: %v", version, err)
		}
		release.CanonicalDigest = digest
		result, err := releases.Stage(
			ctx,
			"stage-"+version,
			release,
		)
		if err != nil || result.Replayed {
			t.Fatalf("stage %s result=%+v err=%v", version, result, err)
		}
		replay, err := releases.Stage(ctx, "stage-"+version, release)
		if err != nil || !replay.Replayed {
			t.Fatalf("replay %s result=%+v err=%v", version, replay, err)
		}
	}

	buckets := []rolloutmodel.BucketDefinition{{
		Cohort:            "all",
		WeightBasisPoints: 10000,
	}}
	first, err := rollouts.Activate(
		ctx,
		"activate-v1",
		rolloutapplication.ActivateInput{
			PolicyID:          "assistant-default",
			ExpectedRevision:  0,
			BucketDefinitions: buckets,
			Assignments: []rolloutmodel.CohortAssignment{{
				Cohort:         "all",
				ReleaseVersion: "v1",
			}},
			ActivatedBy: "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("activate v1: %v", err)
	}
	replayedFirst, err := rollouts.Activate(
		ctx,
		"activate-v1",
		rolloutapplication.ActivateInput{
			PolicyID:          "assistant-default",
			ExpectedRevision:  0,
			BucketDefinitions: buckets,
			Assignments: []rolloutmodel.CohortAssignment{{
				Cohort:         "all",
				ReleaseVersion: "v1",
			}},
			ActivatedBy: "service:policy-publisher",
		},
	)
	if err != nil || !replayedFirst.Replayed ||
		replayedFirst.Rollout.Revision != first.Rollout.Revision {
		t.Fatalf("replay v1 result=%+v err=%v", replayedFirst, err)
	}
	second, err := rollouts.Activate(
		ctx,
		"activate-v2",
		rolloutapplication.ActivateInput{
			PolicyID:          "assistant-default",
			ExpectedRevision:  first.Rollout.Revision,
			BucketDefinitions: buckets,
			Assignments: []rolloutmodel.CohortAssignment{{
				Cohort:         "all",
				ReleaseVersion: "v2",
			}},
			ActivatedBy: "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("activate v2: %v", err)
	}
	rollback, err := rollouts.Rollback(
		ctx,
		"rollback-v2",
		rolloutapplication.RollbackInput{
			PolicyID:         "assistant-default",
			ExpectedRevision: second.Rollout.Revision,
			ActivatedBy:      "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("rollback v2: %v", err)
	}
	if rollback.Rollout.Revision != 3 ||
		rollback.Rollout.Assignments[0].ReleaseVersion != "v1" {
		t.Fatalf("rollback result=%+v", rollback)
	}

	restarted := rolloutpersistence.NewMongoStore(integrationMongoDB)
	persisted, found, err := restarted.Get(ctx, "assistant-default")
	if err != nil || !found ||
		persisted.Revision != rollback.Rollout.Revision ||
		persisted.Assignments[0].ReleaseVersion != "v1" {
		t.Fatalf("persisted rollout=%+v found=%v err=%v", persisted, found, err)
	}
	releaseOutbox, err := integrationMongoDB.Collection(
		"assistant_policy_release_outbox",
	).CountDocuments(ctx, bson.M{})
	if err != nil || releaseOutbox != 2 {
		t.Fatalf("release outbox count=%d err=%v", releaseOutbox, err)
	}
	rolloutOutbox, err := integrationMongoDB.Collection(
		"assistant_policy_rollout_outbox",
	).CountDocuments(ctx, bson.M{})
	if err != nil || rolloutOutbox != 3 {
		t.Fatalf("rollout outbox count=%d err=%v", rolloutOutbox, err)
	}
	releaseRelay, err := policymessaging.NewOutboxRelay(
		"release",
		releaseStore,
		newIntegrationMessageTransport(),
		time.Second,
		16,
		nil,
	)
	if err != nil {
		t.Fatalf("create release outbox relay: %v", err)
	}
	releasePublished, err := releaseRelay.FlushOnce(ctx)
	if err != nil || releasePublished != 2 {
		t.Fatalf("publish release outbox count=%d err=%v", releasePublished, err)
	}
	rolloutRelay, err := policymessaging.NewOutboxRelay(
		"rollout",
		rolloutStore,
		newIntegrationMessageTransport(),
		time.Second,
		16,
		nil,
	)
	if err != nil {
		t.Fatalf("create rollout outbox relay: %v", err)
	}
	rolloutPublished, err := rolloutRelay.FlushOnce(ctx)
	if err != nil || rolloutPublished != 3 {
		t.Fatalf("publish rollout outbox count=%d err=%v", rolloutPublished, err)
	}
	releasePublishedCount, err := integrationMongoDB.Collection(
		"assistant_policy_release_outbox",
	).CountDocuments(ctx, bson.M{"publishedAt": bson.M{"$exists": true}})
	if err != nil || releasePublishedCount != 2 {
		t.Fatalf("published release outbox count=%d err=%v", releasePublishedCount, err)
	}
	rolloutPublishedCount, err := integrationMongoDB.Collection(
		"assistant_policy_rollout_outbox",
	).CountDocuments(ctx, bson.M{"publishedAt": bson.M{"$exists": true}})
	if err != nil || rolloutPublishedCount != 3 {
		t.Fatalf("published rollout outbox count=%d err=%v", rolloutPublishedCount, err)
	}
}

func TestAssistantRunFreezesRealPolicySelectionAcrossActivationAndRollback(
	t *testing.T,
) {
	resetIntegrationState(t)
	ctx := context.Background()
	releaseStore := releasepersistence.NewMongoStore(integrationMongoDB)
	rolloutStore := rolloutpersistence.NewMongoStore(integrationMongoDB)
	if err := releaseStore.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure policy release indexes: %v", err)
	}
	if err := rolloutStore.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure policy rollout indexes: %v", err)
	}
	releases := releaseapplication.NewService(releaseStore, nil)
	for _, version := range []string{"v1", "v2"} {
		release := policyReleaseForIntegration(version)
		digest, err := releasemodel.Digest(release)
		if err != nil {
			t.Fatalf("digest release %s: %v", version, err)
		}
		release.CanonicalDigest = digest
		if _, err := releases.Stage(ctx, "freeze-stage-"+version, release); err != nil {
			t.Fatalf("stage release %s: %v", version, err)
		}
	}
	rollouts := rolloutapplication.NewService(rolloutStore, releases, nil)
	buckets := []rolloutmodel.BucketDefinition{{
		Cohort:            "all",
		WeightBasisPoints: 10000,
	}}
	firstActivation, err := rollouts.Activate(
		ctx,
		"freeze-activate-v1",
		rolloutapplication.ActivateInput{
			PolicyID:          "assistant-default",
			ExpectedRevision:  0,
			BucketDefinitions: buckets,
			Assignments: []rolloutmodel.CohortAssignment{{
				Cohort:         "all",
				ReleaseVersion: "v1",
			}},
			ActivatedBy: "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("activate v1: %v", err)
	}

	service := newIntegrationAssistantService(
		realFrozenPolicyResolver(rollouts),
	)
	conversation, err := service.CreateConversation(
		ctx,
		"policy-freeze-user",
		assistant.CreateConversationInput{
			Summary:         "policy freeze",
			ClientRequestID: "policy-freeze-conversation",
		},
	)
	if err != nil {
		t.Fatalf("create conversation: %v", err)
	}
	firstTurn := createAndExecutePolicyTurn(
		t,
		service,
		conversation.ConversationID,
		"policy-freeze-user",
		"policy-freeze-persona",
		"policy-freeze-v1",
	)
	assertSelectedPolicyVersion(t, firstTurn, "v1", firstActivation.Rollout.Revision)

	secondActivation, err := rollouts.Activate(
		ctx,
		"freeze-activate-v2",
		rolloutapplication.ActivateInput{
			PolicyID:          "assistant-default",
			ExpectedRevision:  firstActivation.Rollout.Revision,
			BucketDefinitions: buckets,
			Assignments: []rolloutmodel.CohortAssignment{{
				Cohort:         "all",
				ReleaseVersion: "v2",
			}},
			ActivatedBy: "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("activate v2: %v", err)
	}
	secondTurn := createAndExecutePolicyTurn(
		t,
		service,
		conversation.ConversationID,
		"policy-freeze-user",
		"policy-freeze-persona",
		"policy-freeze-v2",
	)
	assertSelectedPolicyVersion(t, secondTurn, "v2", secondActivation.Rollout.Revision)

	rollback, err := rollouts.Rollback(
		ctx,
		"freeze-rollback-v2",
		rolloutapplication.RollbackInput{
			PolicyID:         "assistant-default",
			ExpectedRevision: secondActivation.Rollout.Revision,
			ActivatedBy:      "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("rollback v2: %v", err)
	}
	thirdTurn := createAndExecutePolicyTurn(
		t,
		service,
		conversation.ConversationID,
		"policy-freeze-user",
		"policy-freeze-persona",
		"policy-freeze-after-rollback",
	)
	assertSelectedPolicyVersion(t, thirdTurn, "v1", rollback.Rollout.Revision)

	persistedFirst, err := service.GetTurn(ctx, "policy-freeze-user", firstTurn.TurnID)
	if err != nil {
		t.Fatalf("reload frozen first turn: %v", err)
	}
	assertSelectedPolicyVersion(t, persistedFirst, "v1", firstActivation.Rollout.Revision)
}

func realFrozenPolicyResolver(
	rollouts *rolloutapplication.Service,
) application.AssistantServiceOption {
	return application.WithFrozenPolicyResolver(
		application.FrozenPolicyResolverFunc(func(
			ctx context.Context,
			policyID string,
			personaID string,
			skillID string,
			domainID string,
		) (assistant.AssistantFrozenPolicySelection, error) {
			resolved, err := rollouts.ResolveFrozenSelection(
				ctx,
				policyID,
				personaID,
				skillID,
				domainID,
			)
			if err != nil {
				return assistant.AssistantFrozenPolicySelection{}, err
			}
			return assistant.AssistantFrozenPolicySelection{
				PolicyID:        resolved.PolicyID,
				ReleaseVersion:  resolved.ReleaseVersion,
				Cohort:          resolved.Cohort,
				RolloutRevision: resolved.RolloutRevision,
				RuleID:          resolved.RuleID,
				Template: assistant.AssistantFrozenPolicyTemplate{
					TemplateID:      resolved.Template.TemplateID,
					SkillID:         resolved.Template.SkillID,
					DomainID:        resolved.Template.DomainID,
					PromptPolicy:    resolved.Template.PromptPolicy,
					AllowedTools:    append([]string(nil), resolved.Template.AllowedTools...),
					SearchIntensity: resolved.Template.SearchIntensity,
				},
				LearningContextPolicy: assistant.AssistantFrozenLearningContextPolicy{
					Enabled:                  resolved.LearningContextPolicy.Enabled,
					AllowedSignals:           append([]string(nil), resolved.LearningContextPolicy.AllowedSignals...),
					AllowedMetricIDs:         append([]string(nil), resolved.LearningContextPolicy.AllowedMetricIDs...),
					AllowedReasonCodes:       append([]string(nil), resolved.LearningContextPolicy.AllowedReasonCodes...),
					MinimumFeedbackSamples:   resolved.LearningContextPolicy.MinimumFeedbackSamples,
					WindowDays:               resolved.LearningContextPolicy.WindowDays,
					SnapshotTrainingEligible: resolved.LearningContextPolicy.SnapshotTrainingEligible,
				},
			}, nil
		}),
	)
}

func createAndExecutePolicyTurn(
	t *testing.T,
	service *application.AssistantService,
	conversationID string,
	userID string,
	personaID string,
	clientRequestID string,
) assistant.AssistantTurn {
	t.Helper()
	turn, err := service.CreateTurn(
		context.Background(),
		userID,
		conversationID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: "policy snapshot"},
			ClientRequestID: clientRequestID,
			RequestContext: assistant.AssistantRunRequestContext{
				PersonaID: personaID,
			},
		},
	)
	if err != nil {
		t.Fatalf("create policy turn: %v", err)
	}
	if _, err := service.ExecuteTurn(context.Background(), userID, turn.TurnID); err != nil {
		t.Fatalf("execute policy turn: %v", err)
	}
	persisted, err := service.GetTurn(context.Background(), userID, turn.TurnID)
	if err != nil {
		t.Fatalf("reload policy turn: %v", err)
	}
	return persisted
}

func assertSelectedPolicyVersion(
	t *testing.T,
	turn assistant.AssistantTurn,
	version string,
	revision int,
) {
	t.Helper()
	if turn.TerminalSnapshot == nil ||
		turn.TerminalSnapshot.SelectedPolicyRef == nil ||
		turn.TerminalSnapshot.SelectedPolicyRef.PolicyID != "assistant-default" ||
		turn.TerminalSnapshot.SelectedPolicyRef.Version != version ||
		turn.FrozenPolicySelection.RolloutRevision != revision {
		t.Fatalf(
			"turn=%+v selectedPolicy=%+v want version=%s revision=%d",
			turn,
			turn.TerminalSnapshot,
			version,
			revision,
		)
	}
}

func policyReleaseForIntegration(version string) releasemodel.Release {
	return releasemodel.Release{
		PolicyID:          "assistant-default",
		ReleaseVersion:    version,
		DefaultTemplateID: "default",
		Templates: []releasemodel.Template{{
			TemplateID:      "default",
			SkillID:         "fallback_general_search",
			DomainID:        "assistant",
			PromptPolicy:    "grounded answer " + version,
			AllowedTools:    []string{"app_search"},
			SearchIntensity: "balanced",
		}},
		LearningContextPolicy: releasemodel.LearningContextPolicy{
			Enabled:                  true,
			AllowedSignals:           []string{"feedback_counts"},
			MinimumFeedbackSamples:   3,
			WindowDays:               30,
			SnapshotTrainingEligible: false,
		},
	}
}
