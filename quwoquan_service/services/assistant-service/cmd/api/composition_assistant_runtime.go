package main

import (
	"context"
	"errors"
	"strings"
	"time"

	generatedsecurity "quwoquan_service/generated/operationsecurity"
	runtimeconfig "quwoquan_service/runtime/config"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	policyreleaseapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	policyrolloutapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	preferenceapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/application"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/feedbackcontext"
	runorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/toolaccess"
	runports "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	skillcontextinfra "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
	sessioncompaction "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/compaction"
	sessionorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/chatclient"
	descriptorhttp "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/adapters/inbound/http"
	descriptorapplication "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/application"
	descriptorresource "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
	pageapplication "quwoquan_service/services/assistant-service/internal/assistant/page_context/application"
	pagepersistence "quwoquan_service/services/assistant-service/internal/assistant/page_context/infrastructure/persistence"
	skillcatalogactive "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/activerelease"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	skillpackageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	skillpackagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	skillpackageartifact "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/artifact"
	placementapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	settingapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/application"
)

type assistantComponents struct {
	service              *sessionorchestration.AssistantService
	durableExecutor      *runruntime.ManagedRunExecutor
	runCommands          *runruntime.CommandService
	runContextResolver   *runapplication.ContextResolver
	pageContextFacade    *pageapplication.Facade
	chatGroundingClient  *chatclient.Client
	preferenceCommands   *preferenceapplication.CommandFacade
	preferenceQueries    *preferenceapplication.QueryFacade
	consentCommands      *consentapplication.CommandFacade
	consentQueries       *consentapplication.QueryFacade
	settingCommands      *settingapplication.CommandFacade
	settingQueries       *settingapplication.QueryFacade
	placementCommands    *placementapplication.CommandFacade
	placementQueries     *placementapplication.QueryFacade
	policyReleaseService *policyreleaseapplication.Service
	policyRolloutService *policyrolloutapplication.Service
	skillPackageService  *skillpackageapplication.Service
	activeSkillCatalog   *skillcatalogactive.CatalogSource
	learningFactService  *learningapplication.Service
	learningOpsQueries   *learningapplication.OpsQueryService
	domainReaderHandler  *descriptorhttp.Handler
	runHooks             *runruntime.HookRegistry
	sessionCompactor     *sessioncompaction.Service
}

func wireAssistantRuntime(
	runtime *assistantAPIRuntime,
	infrastructure *assistantInfrastructure,
) (*assistantComponents, error) {
	deps := infrastructure.dependencies
	trustedSkillPackageKeys, err := skillpackageapplication.DecodeTrustedPublicKeys(
		runtime.config.SkillPackage.TrustedPublicKeysJSON,
	)
	if err != nil {
		return nil, dependencyError("assistant-skill-package", "trusted-keys", err)
	}
	skillPackageAssets, err := skillpackageartifact.NewResourceReader(
		runtime.config.SkillPackage.AssetRoot,
	)
	if err != nil {
		return nil, dependencyError("assistant-skill-package", "asset-reader", err)
	}
	skillPackageService := skillpackageapplication.NewService(
		deps.skillPackageStore,
		deps.skillPackageStore,
		skillPackageAssets,
		skillpackageapplication.NewEd25519Verifier(trustedSkillPackageKeys),
		skillpackageapplication.RuntimeIdentity{
			APIVersion: skillpackagemodel.RuntimeAPIVersion,
			Version:    skillpackagemodel.RuntimeVersion,
		},
		time.Now,
	)
	activeSkillCatalog := skillcatalogactive.NewCatalogSource(
		skillPackageService,
		skillcatalogactive.OfficialPackageID,
		runorchestration.ValidateAssistantDomainSkillCatalog,
	)
	activeSkillPrompts := skillcatalogactive.NewPromptResolver(
		skillPackageService,
		skillcatalogactive.OfficialPackageID,
	)
	runtimeDescriptors, err := skillcontextinfra.RuntimeDescriptors()
	if err != nil {
		return nil, dependencyError(
			"assistant-domain-reader",
			"descriptor-source",
			err,
		)
	}
	descriptorCatalog, err := descriptorresource.NewCatalog(runtimeDescriptors)
	if err != nil {
		return nil, dependencyError(
			"assistant-domain-reader",
			"catalog",
			err,
		)
	}
	descriptorRoutes, err := descriptorhttp.NewRouteDescriptors(
		generatedsecurity.ForDomain("assistant"),
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-domain-reader",
			"generated-routes",
			err,
		)
	}
	domainReaderHandler, err := descriptorhttp.NewHandler(
		descriptorapplication.NewQueryService(descriptorCatalog),
		descriptorRoutes,
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-domain-reader",
			"http-handler",
			err,
		)
	}
	settingQueries := settingapplication.NewQueryFacade(deps.settingStore)
	infrastructure.healthChecker.Register("assistant_skill_package", func(ctx context.Context) error {
		_, resolveErr := activeSkillCatalog.ResolveSnapshot(ctx)
		return resolveErr
	})

	externalClients, err := buildAssistantExternalClients(runtime, infrastructure)
	if err != nil {
		return nil, err
	}
	agentLoop, err := buildAgentLoop(
		runtime.appEnv,
		externalClients.canonicalSearch,
		runtime.config.Model,
		runtimeconfig.EnvRuntimeConfigProvider{},
		externalClients.egressClient,
		deps.publicWebEvidence,
		deps.publicWebBudget,
		deps.runRepository,
		deps.subscriptionStore,
		externalClients.interestReader,
		deps.consentStore,
		externalClients.travelContextReader,
		externalClients.canonicalDomainReaders,
		descriptorCatalog,
		activeSkillCatalog,
		activeSkillPrompts,
	)
	if err != nil {
		return nil, dependencyError("assistant-agent-loop", "initialization", err)
	}
	runHooks, err := buildProductionRunHooks(agentLoop)
	if err != nil {
		return nil, dependencyError("assistant-run-hooks", "initialization", err)
	}
	infrastructure.healthChecker.Register("assistant_skill_package_policies", func(ctx context.Context) error {
		snapshot, resolveErr := activeSkillCatalog.ResolveSnapshot(ctx)
		if resolveErr != nil {
			return resolveErr
		}
		for _, manifest := range snapshot.Manifests {
			if validateErr := runHooks.ValidatePolicyRefs(
				manifest.Orchestration.HookPolicyRefs,
			); validateErr != nil {
				return errors.New("active Skill " + manifest.SkillID + " Hook policy: " + validateErr.Error())
			}
			if validateErr := runHooks.ValidateVerifierRefs(
				manifest.Orchestration.DefinitionOfDone,
				manifest.Orchestration.VerifierRefs,
			); validateErr != nil {
				return errors.New("active Skill " + manifest.SkillID + " verifier policy: " + validateErr.Error())
			}
		}
		return nil
	})
	sessionCompactor := sessioncompaction.NewService(
		deps.sessionStore,
		sessioncompaction.NarrativeGeneratorFunc(func(
			ctx context.Context,
			input sessioncompaction.NarrativeInput,
		) (string, error) {
			response, completeErr := agentLoop.React.Model.Complete(
				ctx,
				runorchestration.ModelRequest{
					Stage:            string(runports.ModelStageCompaction),
					ProblemClass:     string(assistantgenerated.ProblemClassGeneral),
					SearchIntensity:  string(assistantgenerated.SearchIntensityMedium),
					ReasoningProfile: assistantgenerated.AssistantReasoningProfileBalanced,
					Prompt:           "把上一版摘要与本轮公开对话压缩为新的连续叙事。",
					Observation: map[string]any{
						"previousSummary": input.PreviousSummary,
						"currentGoal":     input.CurrentGoal,
						"userInput":       input.UserInput,
						"answerText":      input.AnswerText,
						"confirmedFacts":  input.ConfirmedFacts,
						"pendingItems":    input.PendingItems,
						"confirmedSlots":  input.ConfirmedSlots,
					},
				},
			)
			if completeErr != nil {
				return "", completeErr
			}
			return strings.TrimSpace(response.Text), nil
		}),
	)
	placement, err := wireAssistantSurfacePlacement(
		runtime,
		infrastructure,
		activeSkillCatalog,
		externalClients.egressClient,
	)
	if err != nil {
		return nil, err
	}
	if deps.preferenceStore == nil || deps.preferenceReader == nil {
		return nil, dependencyError(
			"mongodb.assistant_preferences",
			"wiring",
			errors.New("preference store and reader are required"),
		)
	}
	sessionOwnerReader, ok := deps.sessionStore.(preferenceapplication.SessionOwnerReader)
	if !ok {
		return nil, dependencyError(
			"mongodb.assistant_sessions",
			"wiring",
			errors.New("session owner reader is required"),
		)
	}
	preferenceCommands := preferenceapplication.NewCommandFacade(
		deps.preferenceStore,
		sessionOwnerReader,
	)
	preferenceQueries := preferenceapplication.NewQueryFacade(deps.preferenceReader)
	policyReleaseService := policyreleaseapplication.NewService(
		deps.policyReleaseStore,
		nil,
	)
	policyRolloutService := policyrolloutapplication.NewService(
		deps.policyRolloutStore,
		policyReleaseService,
		nil,
	)
	frozenPolicyResolver := runruntime.PolicyResolverFunc(
		func(
			ctx context.Context,
			policyID string,
			personaID string,
			skillID string,
			domainID string,
		) (runruntime.FrozenPolicySelection, error) {
			resolved, resolveErr := policyRolloutService.ResolveFrozenSelection(
				ctx,
				policyID,
				personaID,
				skillID,
				domainID,
			)
			if resolveErr != nil {
				return runruntime.FrozenPolicySelection{}, resolveErr
			}
			return projectRunFrozenPolicySelection(resolved), nil
		},
	)
	durableExecutor := runruntime.NewManagedRunExecutor(
		runorchestration.NewDurableRunExecutor(agentLoop),
	)
	runCancellation := runruntime.NewCancellationCoordinator(
		durableExecutor,
		10*time.Second,
	)
	consentQueries := consentapplication.NewQueryFacade(deps.consentStore)
	authorizeSkillAccess := newSkillAccessAuthorizer(
		settingQueries,
		consentQueries,
		placement.queries,
		activeSkillCatalog,
	)
	configureAgentSkillAccess(
		agentLoop,
		settingQueries,
		placement.queries,
		activeSkillCatalog,
		authorizeSkillAccess,
	)
	configureAgentToolAccess(
		agentLoop,
		toolaccess.NewPolicy(
			deps.settingStore,
			deps.consentStore,
			externalClients.connectorGrantGateway,
		),
	)
	runCommands := runruntime.NewCommandService(
		deps.runRepository,
		runruntime.SessionResolverFunc(func(
			ctx context.Context,
			userID string,
			sessionID string,
		) (runruntime.SessionContinuity, error) {
			session, found, readErr := deps.sessionStore.GetSession(ctx, sessionID)
			if readErr != nil {
				return runruntime.SessionContinuity{}, readErr
			}
			if !found || session.UserID != strings.TrimSpace(userID) ||
				strings.TrimSpace(session.State) != "active" {
				return runruntime.SessionContinuity{}, runruntime.ErrRunNotFound
			}
			if session.ContextSummary == nil {
				return runruntime.SessionContinuity{}, nil
			}
			return runruntime.SessionContinuity{
				SummaryID:      session.ContextSummary.SummaryID,
				Text:           session.ContextSummary.Text,
				FromTurnID:     session.ContextSummary.FromTurnID,
				ToTurnID:       session.ContextSummary.ToTurnID,
				TurnCount:      session.ContextSummary.TurnCount,
				CurrentGoal:    session.ContextSummary.CurrentGoal,
				ConfirmedFacts: append([]string(nil), session.ContextSummary.ConfirmedFacts...),
				PendingItems:   append([]string(nil), session.ContextSummary.PendingItems...),
				ConfirmedSlots: cloneSessionSummarySlots(
					session.ContextSummary.ConfirmedSlots,
				),
			}, nil
		}),
		activeSkillCatalog,
		runruntime.StartAccessPolicyFunc(func(
			ctx context.Context,
			request runruntime.StartAccessRequest,
		) error {
			return authorizeSkillAccess(
				ctx,
				request.AccountID,
				request.SkillID,
				request.SurfaceKind,
				request.SurfaceID,
			)
		}),
		time.Now,
		runCancellation,
		runruntime.WithPolicyResolver(frozenPolicyResolver),
		runruntime.WithFeedbackContextResolver(
			feedbackcontext.NewActiveSkillResolver(
				feedbackcontext.NewResolver(
					deps.consentStore,
					deps.learningProjection,
				),
				activeSkillCatalog,
			),
		),
	)
	pageContextFacade := pageapplication.NewFacade(
		pagepersistence.NewRedisStore(infrastructure.router.Scene("general")),
		func() time.Time { return time.Now().UTC() },
	)
	runContextResolver := newAssistantRunContextResolver(
		pageContextFacade,
		externalClients.intersectionEvidence,
	)
	assistantOpts := []sessionorchestration.AssistantServiceOption{
		sessionorchestration.WithNotificationAppMessageCommandWriter(externalClients.notificationWriter),
		sessionorchestration.WithSkillSubscriptionStore(deps.subscriptionStore),
		sessionorchestration.WithAssistantDeliveryPolicyReader(externalClients.deliveryPolicyReader),
		sessionorchestration.WithSessionStore(deps.sessionStore),
		sessionorchestration.WithRunCommandService(runCommands),
		sessionorchestration.WithSkillCatalog(activeSkillCatalog),
	}
	chatGroundingClient, err := buildAssistantChatGroundingClient(
		runtime,
		infrastructure,
		externalClients.egressClient,
	)
	if err != nil {
		return nil, err
	}
	assistantOpts = append(
		assistantOpts,
		sessionorchestration.WithChatGroundingClient(chatGroundingClient),
	)
	learningFactService := learningapplication.NewService(
		deps.learningFactStore,
		deps.learningRunOwners,
		nil,
	)
	learningOpsQueries := learningapplication.NewOpsQueryService(
		deps.learningProjection,
	)
	service := sessionorchestration.NewAssistantService(
		deps.consentStore,
		infrastructure.router.Scene("general"),
		assistantOpts...,
	)
	consentCommands := consentapplication.NewCommandFacade(
		deps.consentStore,
		func() time.Time { return time.Now().UTC() },
	)
	settingCommands := settingapplication.NewCommandFacade(
		deps.settingStore,
		activeSkillCatalog,
		func() time.Time { return time.Now().UTC() },
	)
	return &assistantComponents{
		service:              service,
		durableExecutor:      durableExecutor,
		runCommands:          runCommands,
		runContextResolver:   runContextResolver,
		pageContextFacade:    pageContextFacade,
		chatGroundingClient:  chatGroundingClient,
		preferenceCommands:   preferenceCommands,
		preferenceQueries:    preferenceQueries,
		consentCommands:      consentCommands,
		consentQueries:       consentQueries,
		settingCommands:      settingCommands,
		settingQueries:       settingQueries,
		placementCommands:    placement.commands,
		placementQueries:     placement.queries,
		policyReleaseService: policyReleaseService,
		policyRolloutService: policyRolloutService,
		skillPackageService:  skillPackageService,
		activeSkillCatalog:   activeSkillCatalog,
		learningFactService:  learningFactService,
		learningOpsQueries:   learningOpsQueries,
		domainReaderHandler:  domainReaderHandler,
		runHooks:             runHooks,
		sessionCompactor:     sessionCompactor,
	}, nil
}

func cloneSessionSummarySlots(value map[string]string) map[string]string {
	if value == nil {
		return nil
	}
	cloned := make(map[string]string, len(value))
	for key, item := range value {
		cloned[key] = item
	}
	return cloned
}

func projectRunFrozenPolicySelection(
	selection policyrolloutapplication.FrozenSelection,
) runruntime.FrozenPolicySelection {
	return runruntime.FrozenPolicySelection{
		PolicyID:        selection.PolicyID,
		ReleaseDigest:   selection.ReleaseDigest,
		Cohort:          selection.Cohort,
		RolloutRevision: selection.RolloutRevision,
		RuleID:          selection.RuleID,
		Template: runruntime.FrozenPolicyTemplate{
			TemplateID:      selection.Template.TemplateID,
			SkillID:         selection.Template.SkillID,
			DomainID:        selection.Template.DomainID,
			PromptPolicy:    selection.Template.PromptPolicy,
			AllowedTools:    append([]string(nil), selection.Template.AllowedTools...),
			SearchIntensity: selection.Template.SearchIntensity,
		},
		LearningContextPolicy: runruntime.FrozenLearningContextPolicy{
			Enabled:                  selection.LearningContextPolicy.Enabled,
			AllowedSignals:           append([]string(nil), selection.LearningContextPolicy.AllowedSignals...),
			AllowedMetricIDs:         append([]string(nil), selection.LearningContextPolicy.AllowedMetricIDs...),
			AllowedReasonCodes:       append([]string(nil), selection.LearningContextPolicy.AllowedReasonCodes...),
			MinimumFeedbackSamples:   selection.LearningContextPolicy.MinimumFeedbackSamples,
			WindowDays:               selection.LearningContextPolicy.WindowDays,
			SnapshotTrainingEligible: selection.LearningContextPolicy.SnapshotTrainingEligible,
		},
	}
}
