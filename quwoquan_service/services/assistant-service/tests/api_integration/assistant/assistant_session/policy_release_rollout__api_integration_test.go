// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/spec.md#sit-001
// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md#gwt-001
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	releaseapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	releasemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
	policymessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/messaging"
	releasepersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/persistence"
	rolloutapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	rolloutmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
	rolloutmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/messaging"
	rolloutpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
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

	for _, variant := range []string{"baseline", "candidate"} {
		release := policyReleaseForIntegration(t, variant)
		result, err := releases.Stage(
			ctx,
			"stage-"+release.ReleaseDigest,
			release,
		)
		if err != nil || result.Replayed {
			t.Fatalf("stage %s result=%+v err=%v", variant, result, err)
		}
		replay, err := releases.Stage(ctx, "stage-"+release.ReleaseDigest, release)
		if err != nil || !replay.Replayed {
			t.Fatalf("replay %s result=%+v err=%v", variant, replay, err)
		}
	}
	baselineDigest := policyReleaseForIntegration(t, "baseline").ReleaseDigest
	candidateDigest := policyReleaseForIntegration(t, "candidate").ReleaseDigest

	buckets := []rolloutmodel.BucketDefinition{{
		Cohort:            "all",
		WeightBasisPoints: 10000,
	}}
	first, err := rollouts.Activate(
		ctx,
		"activate-baseline",
		rolloutapplication.ActivateInput{
			PolicyID:          "assistant-default",
			ExpectedRevision:  0,
			BucketDefinitions: buckets,
			Assignments: []rolloutmodel.CohortAssignment{{
				Cohort:        "all",
				ReleaseDigest: baselineDigest,
			}},
			ActivatedBy: "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("activate baseline: %v", err)
	}
	replayedFirst, err := rollouts.Activate(
		ctx,
		"activate-baseline",
		rolloutapplication.ActivateInput{
			PolicyID:          "assistant-default",
			ExpectedRevision:  0,
			BucketDefinitions: buckets,
			Assignments: []rolloutmodel.CohortAssignment{{
				Cohort:        "all",
				ReleaseDigest: baselineDigest,
			}},
			ActivatedBy: "service:policy-publisher",
		},
	)
	if err != nil || !replayedFirst.Replayed ||
		replayedFirst.Rollout.Revision != first.Rollout.Revision {
		t.Fatalf("replay baseline result=%+v err=%v", replayedFirst, err)
	}
	second, err := rollouts.Activate(
		ctx,
		"activate-candidate",
		rolloutapplication.ActivateInput{
			PolicyID:          "assistant-default",
			ExpectedRevision:  first.Rollout.Revision,
			BucketDefinitions: buckets,
			Assignments: []rolloutmodel.CohortAssignment{{
				Cohort:        "all",
				ReleaseDigest: candidateDigest,
			}},
			ActivatedBy: "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("activate candidate: %v", err)
	}
	rollback, err := rollouts.Rollback(
		ctx,
		"rollback-candidate",
		rolloutapplication.RollbackInput{
			PolicyID:         "assistant-default",
			ExpectedRevision: second.Rollout.Revision,
			ActivatedBy:      "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("rollback candidate: %v", err)
	}
	if rollback.Rollout.Revision != 3 ||
		rollback.Rollout.Assignments[0].ReleaseDigest != baselineDigest {
		t.Fatalf("rollback result=%+v", rollback)
	}

	restarted := rolloutpersistence.NewMongoStore(integrationMongoDB)
	persisted, found, err := restarted.Get(ctx, "assistant-default")
	if err != nil || !found ||
		persisted.Revision != rollback.Rollout.Revision ||
		persisted.Assignments[0].ReleaseDigest != baselineDigest {
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
	rolloutRelay, err := rolloutmessaging.NewOutboxRelay(
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
	for _, variant := range []string{"baseline", "candidate"} {
		release := policyReleaseForIntegration(t, variant)
		if _, err := releases.Stage(ctx, "freeze-stage-"+release.ReleaseDigest, release); err != nil {
			t.Fatalf("stage release %s: %v", variant, err)
		}
	}
	baselineDigest := policyReleaseForIntegration(t, "baseline").ReleaseDigest
	candidateDigest := policyReleaseForIntegration(t, "candidate").ReleaseDigest
	rollouts := rolloutapplication.NewService(rolloutStore, releases, nil)
	buckets := []rolloutmodel.BucketDefinition{{
		Cohort:            "all",
		WeightBasisPoints: 10000,
	}}
	firstActivation, err := rollouts.Activate(
		ctx,
		"freeze-activate-baseline",
		rolloutapplication.ActivateInput{
			PolicyID:          "assistant-default",
			ExpectedRevision:  0,
			BucketDefinitions: buckets,
			Assignments: []rolloutmodel.CohortAssignment{{
				Cohort:        "all",
				ReleaseDigest: baselineDigest,
			}},
			ActivatedBy: "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("activate baseline: %v", err)
	}

	service := newIntegrationAssistantService()
	session, err := service.CreateSession(
		ctx,
		"policy-freeze-user",
		assistant.CreateSessionInput{
			Summary:         "policy freeze",
			ClientRequestID: "policy-freeze-session",
		},
	)
	if err != nil {
		t.Fatalf("create session: %v", err)
	}
	commands := runruntime.NewCommandService(
		integrationRunRepository,
		runruntime.SessionResolverFunc(func(
			ctx context.Context,
			userID string,
			sessionID string,
		) (runruntime.SessionContinuity, error) {
			_, authorizeErr := service.GetSession(ctx, userID, sessionID)
			return runruntime.SessionContinuity{}, authorizeErr
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(realRunPolicyResolver(rollouts)),
	)
	firstTurn := createPolicyRun(
		t,
		commands,
		session.SessionID,
		"policy-freeze-user",
		"policy-freeze-persona",
		"policy-freeze-baseline",
	)
	assertSelectedPolicyDigest(t, firstTurn, baselineDigest, firstActivation.Rollout.Revision)

	secondActivation, err := rollouts.Activate(
		ctx,
		"freeze-activate-candidate",
		rolloutapplication.ActivateInput{
			PolicyID:          "assistant-default",
			ExpectedRevision:  firstActivation.Rollout.Revision,
			BucketDefinitions: buckets,
			Assignments: []rolloutmodel.CohortAssignment{{
				Cohort:        "all",
				ReleaseDigest: candidateDigest,
			}},
			ActivatedBy: "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("activate candidate: %v", err)
	}
	secondTurn := createPolicyRun(
		t,
		commands,
		session.SessionID,
		"policy-freeze-user",
		"policy-freeze-persona",
		"policy-freeze-candidate",
	)
	assertSelectedPolicyDigest(t, secondTurn, candidateDigest, secondActivation.Rollout.Revision)

	rollback, err := rollouts.Rollback(
		ctx,
		"freeze-rollback-candidate",
		rolloutapplication.RollbackInput{
			PolicyID:         "assistant-default",
			ExpectedRevision: secondActivation.Rollout.Revision,
			ActivatedBy:      "service:policy-publisher",
		},
	)
	if err != nil {
		t.Fatalf("rollback candidate: %v", err)
	}
	thirdTurn := createPolicyRun(
		t,
		commands,
		session.SessionID,
		"policy-freeze-user",
		"policy-freeze-persona",
		"policy-freeze-after-rollback",
	)
	assertSelectedPolicyDigest(t, thirdTurn, baselineDigest, rollback.Rollout.Revision)

	persistedFirst, err := integrationRunRepository.Load(ctx, firstTurn.RunID)
	if err != nil {
		t.Fatalf("reload frozen first turn: %v", err)
	}
	assertSelectedPolicyDigest(t, persistedFirst, baselineDigest, firstActivation.Rollout.Revision)
}

func realRunPolicyResolver(
	rollouts *rolloutapplication.Service,
) runruntime.PolicyResolver {
	return runruntime.PolicyResolverFunc(func(
		ctx context.Context,
		policyID string,
		personaID string,
		skillID string,
		domainID string,
	) (runruntime.FrozenPolicySelection, error) {
		resolved, err := rollouts.ResolveFrozenSelection(
			ctx,
			policyID,
			personaID,
			skillID,
			domainID,
		)
		if err != nil {
			return runruntime.FrozenPolicySelection{}, err
		}
		return runruntime.FrozenPolicySelection{
			PolicyID:        resolved.PolicyID,
			ReleaseDigest:   resolved.ReleaseDigest,
			Cohort:          resolved.Cohort,
			RolloutRevision: resolved.RolloutRevision,
			RuleID:          resolved.RuleID,
			Template: runruntime.FrozenPolicyTemplate{
				TemplateID:      resolved.Template.TemplateID,
				SkillID:         resolved.Template.SkillID,
				DomainID:        resolved.Template.DomainID,
				PromptPolicy:    resolved.Template.PromptPolicy,
				AllowedTools:    append([]string(nil), resolved.Template.AllowedTools...),
				SearchIntensity: resolved.Template.SearchIntensity,
			},
			LearningContextPolicy: runruntime.FrozenLearningContextPolicy{
				Enabled:                  resolved.LearningContextPolicy.Enabled,
				AllowedSignals:           append([]string(nil), resolved.LearningContextPolicy.AllowedSignals...),
				AllowedMetricIDs:         append([]string(nil), resolved.LearningContextPolicy.AllowedMetricIDs...),
				AllowedReasonCodes:       append([]string(nil), resolved.LearningContextPolicy.AllowedReasonCodes...),
				MinimumFeedbackSamples:   resolved.LearningContextPolicy.MinimumFeedbackSamples,
				WindowDays:               resolved.LearningContextPolicy.WindowDays,
				SnapshotTrainingEligible: resolved.LearningContextPolicy.SnapshotTrainingEligible,
			},
		}, nil
	})
}

func createPolicyRun(
	t *testing.T,
	commands *runruntime.CommandService,
	sessionID string,
	userID string,
	personaID string,
	clientRequestID string,
) runruntime.Run {
	t.Helper()
	run, err := commands.Start(context.Background(), runruntime.StartCommand{
		UserID:            userID,
		PersonaID:         personaID,
		SessionID:         sessionID,
		ClientRequestID:   clientRequestID,
		IntentKind:        "answer",
		InputText:         "policy snapshot",
		RequestedSkillID:  "fallback_general_search",
		RequestedDomainID: "assistant",
	})
	if err != nil {
		t.Fatalf("create policy run: %v", err)
	}
	return run
}

func assertSelectedPolicyDigest(
	t *testing.T,
	run runruntime.Run,
	releaseDigest string,
	revision int,
) {
	t.Helper()
	if run.FrozenPolicySelection.PolicyID != "assistant-default" ||
		run.FrozenPolicySelection.ReleaseDigest != releaseDigest ||
		run.FrozenPolicySelection.RolloutRevision != revision {
		t.Fatalf(
			"run=%+v frozenPolicy=%+v want releaseDigest=%s revision=%d",
			run,
			run.FrozenPolicySelection,
			releaseDigest,
			revision,
		)
	}
}

func policyReleaseForIntegration(t *testing.T, variant string) releasemodel.Release {
	t.Helper()
	release := releasemodel.Release{
		PolicyID:          "assistant-default",
		DefaultTemplateID: "default",
		Templates: []releasemodel.Template{{
			TemplateID:      "default",
			SkillID:         "fallback_general_search",
			DomainID:        "assistant",
			PromptPolicy:    "grounded answer " + variant,
			AllowedTools:    []string{"app_search"},
			SearchIntensity: "medium",
		}},
		LearningContextPolicy: releasemodel.LearningContextPolicy{
			Enabled:                  true,
			AllowedSignals:           []string{"feedback_counts"},
			MinimumFeedbackSamples:   3,
			WindowDays:               30,
			SnapshotTrainingEligible: false,
		},
	}
	digest, err := releasemodel.Digest(release)
	if err != nil {
		t.Fatalf("digest release %s: %v", variant, err)
	}
	release.ReleaseDigest = digest
	return release
}
