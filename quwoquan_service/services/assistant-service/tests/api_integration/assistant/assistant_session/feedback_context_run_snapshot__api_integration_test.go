// spec_ref: specs/feature-tree/assistant-run-learning/learning-event-feedback-injection/feedback-context-injection/spec.md#gwt-001
package api_integration

import (
	"context"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	feedbackcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/feedbackcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

const (
	feedbackContextSkillID       = "travel_companion"
	feedbackContextConsentScope  = "assistant.learning.feedback_context.read"
	feedbackContextPackageID     = "assistant.session.skills"
	feedbackContextPackageDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)

type countingFeedbackProjectionReader struct {
	delegate feedbackcontext.ProjectionReader
	reads    int
}

func (reader *countingFeedbackProjectionReader) GetLearningProjectionForPersona(
	ctx context.Context,
	accountID string,
	personaID string,
) (*learningmodel.LearningProjection, error) {
	reader.reads++
	return reader.delegate.GetLearningProjectionForPersona(
		ctx,
		accountID,
		personaID,
	)
}

// frozenFeedbackPackageLoader proves that the feedback resolver reads the
// exact immutable package identity already frozen by AssistantRun. The
// canonical official manifest remains the only source of the consent scope.
type frozenFeedbackPackageLoader struct {
	expected skillpkg.PackageReleaseIdentity
	loads    int
}

func (loader *frozenFeedbackPackageLoader) Load(
	ctx context.Context,
) ([]skillpkg.Manifest, error) {
	loader.loads++
	identity, ok := skillpkg.PackageReleaseFromContext(ctx)
	if !ok || identity != loader.expected {
		return nil, fmt.Errorf(
			"feedback context package identity=%+v found=%t, want %+v",
			identity,
			ok,
			loader.expected,
		)
	}
	return (integrationConsentSkillCatalog{}).Load(ctx)
}

func TestFeedbackContextFreezesCanonicalProjectionAndConsentIntoAssistantRun(
	t *testing.T,
) {
	resetIntegrationState(t)
	ctx := t.Context()
	const (
		accountID = "feedback-context-owner"
		personaID = "feedback-context-owner:persona"
	)
	frozenAt := time.Now().UTC().Truncate(time.Second)

	sourceRun, err := integrationRunCommands.Start(ctx, runruntime.StartCommand{
		UserID:          accountID,
		PersonaID:       personaID,
		SessionID:       "feedback-context-source-session",
		ClientRequestID: "feedback-context-source-run",
		InputText:       "记录 canonical feedback facts",
	})
	if err != nil {
		t.Fatalf("start feedback source run: %v", err)
	}
	learningFacts := learningapplication.NewAssistantLearningFactAppender(
		integrationLearningFactStore,
		runpersistence.NewMongoRunOwnerReader(integrationMongoDB),
		func() time.Time { return frozenAt.Add(-time.Minute) },
	)
	appendFeedbackContextFact(
		t,
		learningFacts,
		sourceRun.RunID,
		accountID,
		personaID,
		"feedback-context-fact-1",
		"useful",
		[]string{"clear", "private_detail"},
		frozenAt.Add(-2*time.Minute),
		true,
	)
	appendFeedbackContextFact(
		t,
		learningFacts,
		sourceRun.RunID,
		accountID,
		personaID,
		"feedback-context-fact-2",
		"irrelevant",
		[]string{"private_detail"},
		frozenAt.Add(-time.Minute),
		false,
	)
	if projected, projectErr := integrationLearningProjector.ProjectAvailable(
		ctx,
		32,
	); projectErr != nil || projected != 2 {
		t.Fatalf("project feedback facts projected=%d err=%v", projected, projectErr)
	}

	consentCommands := consentapplication.NewCommandFacade(
		integrationConsentStore,
		func() time.Time { return frozenAt.Add(-time.Hour) },
	)
	granted, err := consentCommands.Grant(
		ctx,
		"feedback-context-consent-grant",
		accountID,
		feedbackContextSkillID,
		[]string{feedbackContextConsentScope},
	)
	if err != nil || granted.Consent == nil {
		t.Fatalf("grant feedback context consent result=%+v err=%v", granted, err)
	}

	projectionReader := &countingFeedbackProjectionReader{
		delegate: integrationLearningProjector,
	}
	packageLoader := &frozenFeedbackPackageLoader{
		expected: skillpkg.PackageReleaseIdentity{
			PackageID:     feedbackContextPackageID,
			ReleaseDigest: feedbackContextPackageDigest,
		},
	}
	commands := runruntime.NewCommandService(
		integrationRunRepository,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		runruntime.StaticSkillPackageIdentityResolver{
			PackageID:     feedbackContextPackageID,
			ReleaseDigest: feedbackContextPackageDigest,
		},
		runruntime.AllowAllStartAccessPolicy{},
		func() time.Time { return frozenAt },
		nil,
		runruntime.WithPolicyResolver(feedbackContextPolicyResolver()),
		runruntime.WithFeedbackContextResolver(
			feedbackcontext.NewActiveSkillResolver(
				feedbackcontext.NewResolver(
					integrationConsentStore,
					projectionReader,
				),
				packageLoader,
			),
		),
	)
	personalCommand := feedbackContextStartCommand(
		accountID,
		personaID,
		"feedback-context-personal-run",
		"assistant",
	)
	personalRun, err := commands.Start(ctx, personalCommand)
	if err != nil {
		t.Fatalf("start personal feedback-context run: %v", err)
	}
	assertInjectedFeedbackContext(t, personalRun, granted.Consent.ID, 2, 1, 1)
	persistedPersonal, err := integrationRunRepository.Load(ctx, personalRun.RunID)
	if err != nil {
		t.Fatalf("load persisted personal feedback-context run: %v", err)
	}
	assertInjectedFeedbackContext(t, persistedPersonal, granted.Consent.ID, 2, 1, 1)
	if persistedPersonal.SkillPackageID != feedbackContextPackageID ||
		persistedPersonal.SkillPackageReleaseDigest != feedbackContextPackageDigest {
		t.Fatalf(
			"run package identity=%s/%s",
			persistedPersonal.SkillPackageID,
			persistedPersonal.SkillPackageReleaseDigest,
		)
	}
	if projectionReader.reads != 1 || packageLoader.loads != 1 {
		t.Fatalf(
			"initial resolver reads projection=%d package=%d, want 1/1",
			projectionReader.reads,
			packageLoader.loads,
		)
	}

	appendFeedbackContextFact(
		t,
		learningFacts,
		sourceRun.RunID,
		accountID,
		personaID,
		"feedback-context-fact-3",
		"useful",
		[]string{"clear"},
		frozenAt,
		false,
	)
	if projected, projectErr := integrationLearningProjector.ProjectAvailable(
		ctx,
		32,
	); projectErr != nil || projected != 1 {
		t.Fatalf("project changed feedback projected=%d err=%v", projected, projectErr)
	}
	replayedRun, err := commands.Start(ctx, personalCommand)
	if err != nil {
		t.Fatalf("replay personal feedback-context run: %v", err)
	}
	if replayedRun.RunID != personalRun.RunID ||
		replayedRun.FeedbackContextSnapshot.SourceWatermarkSequence !=
			personalRun.FeedbackContextSnapshot.SourceWatermarkSequence ||
		replayedRun.FeedbackContextSnapshot.FeedbackSampleCount != 2 {
		t.Fatalf(
			"idempotent replay changed frozen feedback context: first=%+v replay=%+v",
			personalRun.FeedbackContextSnapshot,
			replayedRun.FeedbackContextSnapshot,
		)
	}
	if projectionReader.reads != 1 || packageLoader.loads != 1 {
		t.Fatalf(
			"idempotent replay reread mutable dependencies: projection=%d package=%d",
			projectionReader.reads,
			packageLoader.loads,
		)
	}
	runCount, err := integrationMongoDB.Collection("assistant_runs").CountDocuments(
		ctx,
		bson.M{
			"userId":          accountID,
			"clientRequestId": personalCommand.ClientRequestID,
		},
	)
	if err != nil || runCount != 1 {
		t.Fatalf("idempotent replay run count=%d err=%v", runCount, err)
	}

	if _, err := consentCommands.Revoke(
		ctx,
		"feedback-context-consent-revoke",
		accountID,
		feedbackContextSkillID,
	); err != nil {
		t.Fatalf("revoke feedback context consent: %v", err)
	}
	revokedRun, err := commands.Start(
		ctx,
		feedbackContextStartCommand(
			accountID,
			personaID,
			"feedback-context-revoked-run",
			"assistant",
		),
	)
	if err != nil {
		t.Fatalf("start run after feedback consent revoke: %v", err)
	}
	assertNoFeedbackContext(t, revokedRun, "consent_missing_or_opted_out")
	persistedRevoked, err := integrationRunRepository.Load(ctx, revokedRun.RunID)
	if err != nil {
		t.Fatalf("load persisted revoked feedback-context run: %v", err)
	}
	assertNoFeedbackContext(t, persistedRevoked, "consent_missing_or_opted_out")
	if projectionReader.reads != 1 || packageLoader.loads != 2 {
		t.Fatalf(
			"revoked resolver reads projection=%d package=%d, want 1/2",
			projectionReader.reads,
			packageLoader.loads,
		)
	}

	if _, err := consentCommands.Grant(
		ctx,
		"feedback-context-consent-regrant",
		accountID,
		feedbackContextSkillID,
		[]string{feedbackContextConsentScope},
	); err != nil {
		t.Fatalf("regrant feedback context consent: %v", err)
	}
	sharedRun, err := commands.Start(
		ctx,
		feedbackContextStartCommand(
			accountID,
			personaID,
			"feedback-context-shared-run",
			"conversation",
		),
	)
	if err != nil {
		t.Fatalf("start shared-surface run: %v", err)
	}
	assertNoFeedbackContext(t, sharedRun, "shared_surface_excluded")
	if projectionReader.reads != 1 || packageLoader.loads != 2 {
		t.Fatalf(
			"shared surface touched private resolver: projection=%d package=%d",
			projectionReader.reads,
			packageLoader.loads,
		)
	}
	loadedShared, err := integrationRunRepository.Load(ctx, sharedRun.RunID)
	if err != nil || loadedShared.FeedbackContextSnapshot.Decision !=
		"shared_surface_excluded" {
		t.Fatalf("persisted shared snapshot=%+v err=%v", loadedShared, err)
	}
}

func feedbackContextPolicyResolver() runruntime.PolicyResolver {
	return runruntime.PolicyResolverFunc(func(
		_ context.Context,
		policyID string,
		_ string,
		_ string,
		_ string,
	) (runruntime.FrozenPolicySelection, error) {
		return runruntime.FrozenPolicySelection{
			PolicyID:        policyID,
			ReleaseDigest:   integrationPolicyReleaseDigest,
			Cohort:          "control",
			RolloutRevision: 1,
			RuleID:          "feedback-context-api-integration",
			Template: runruntime.FrozenPolicyTemplate{
				TemplateID:      "feedback-context-api-integration",
				SkillID:         feedbackContextSkillID,
				DomainID:        "travel",
				PromptPolicy:    "use only allowlisted feedback aggregates",
				SearchIntensity: "medium",
			},
			LearningContextPolicy: runruntime.FrozenLearningContextPolicy{
				Enabled:                  true,
				AllowedSignals:           []string{"feedback_counts", "top_reason_codes"},
				AllowedReasonCodes:       []string{"clear"},
				MinimumFeedbackSamples:   2,
				WindowDays:               30,
				SnapshotTrainingEligible: false,
			},
		}, nil
	})
}

func feedbackContextStartCommand(
	accountID string,
	personaID string,
	clientRequestID string,
	surfaceKind string,
) runruntime.StartCommand {
	return runruntime.StartCommand{
		UserID:            accountID,
		PersonaID:         personaID,
		SessionID:         "feedback-context-target-session",
		ClientRequestID:   clientRequestID,
		IntentKind:        "answer",
		InputText:         "根据已授权的聚合反馈规划行程",
		RequestedSkillID:  feedbackContextSkillID,
		RequestedDomainID: "travel",
		RequestContext: runruntime.RequestContext{
			SurfaceKind: surfaceKind,
			SurfaceID:   "feedback-context-" + surfaceKind,
		},
	}
}

func appendFeedbackContextFact(
	t *testing.T,
	service *learningapplication.AssistantLearningFactAppender,
	runID string,
	accountID string,
	personaID string,
	eventID string,
	feedbackType string,
	reasonCodes []string,
	occurredAt time.Time,
	includeRestrictedText bool,
) {
	t.Helper()
	command := learningmodel.AppendCommand{
		EventID:          eventID,
		FactType:         learningmodel.FactTypeUserFeedback,
		AssistantTurnID:  runID,
		ReferralSource:   "article",
		DomainID:         "assistant",
		FeedbackType:     feedbackType,
		ReasonCodes:      append([]string(nil), reasonCodes...),
		ActionType:       "feedback_submitted",
		TrainingEligible: false,
		OccurredAt:       occurredAt,
	}
	if includeRestrictedText {
		command.QueryText = "private source query"
		command.AnswerText = "private source answer"
		command.FeedbackText = "private source feedback"
		command.CorrectionText = "private source correction"
	}
	trusted := learningmodel.TrustedContext{
		UserID:    accountID,
		PersonaID: personaID,
	}
	if _, err := service.Append(
		t.Context(),
		learningapplication.AppendInput{
			Kind:           learningapplication.AppendKindUserFeedback,
			Command:        command,
			TrustedContext: &trusted,
		},
	); err != nil {
		t.Fatalf("append feedback fact %s: %v", eventID, err)
	}
}

func assertInjectedFeedbackContext(
	t *testing.T,
	run runruntime.Run,
	consentID string,
	wantSamples int64,
	wantPositive int64,
	wantNegative int64,
) {
	t.Helper()
	snapshot := run.FeedbackContextSnapshot
	if snapshot.Decision != "injected" ||
		snapshot.ConsentID != consentID ||
		snapshot.DefinitionDigest != learningmodel.LearningProjectionDefinitionDigest ||
		snapshot.SourceWatermarkSequence <= 0 ||
		snapshot.FeedbackSampleCount != wantSamples ||
		snapshot.PositiveFeedbackCount != wantPositive ||
		snapshot.NegativeFeedbackCount != wantNegative ||
		snapshot.TextFeedbackCount != 0 ||
		len(snapshot.Metrics) != 0 ||
		len(snapshot.Reasons) != 1 ||
		snapshot.Reasons[0].ReasonCode != "clear" ||
		snapshot.Reasons[0].Count != 1 ||
		snapshot.SnapshotTrainingEligible {
		t.Fatalf("injected feedback snapshot=%+v", snapshot)
	}
}

func assertNoFeedbackContext(
	t *testing.T,
	run runruntime.Run,
	wantDecision string,
) {
	t.Helper()
	snapshot := run.FeedbackContextSnapshot
	if snapshot.Decision != wantDecision ||
		snapshot.ConsentID != "" ||
		!snapshot.ConsentGrantedAt.IsZero() ||
		snapshot.DefinitionDigest != "" ||
		snapshot.SourceWatermarkSequence != 0 ||
		snapshot.FeedbackSampleCount != 0 ||
		snapshot.PositiveFeedbackCount != 0 ||
		snapshot.NegativeFeedbackCount != 0 ||
		snapshot.TextFeedbackCount != 0 ||
		len(snapshot.Metrics) != 0 ||
		len(snapshot.Reasons) != 0 ||
		snapshot.SnapshotTrainingEligible {
		t.Fatalf("feedback context must fail closed: %+v", snapshot)
	}
}
