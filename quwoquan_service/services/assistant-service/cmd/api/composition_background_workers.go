package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"log/slog"
	"strings"
	"time"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	learningmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/messaging"
	learningprojection "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/projection"
	policymessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	sessioncompaction "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/compaction"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/scheduling"
	datacontrolapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/application"
	datacontrol "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/infrastructure/control"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	placementapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	placementmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/messaging"
)

const (
	skillSubscriptionCronInterval  = time.Minute
	learningProjectionInterval     = time.Second
	learningOutboxRelayInterval    = time.Second
	assistantConsumerPollInterval  = 500 * time.Millisecond
	assistantWorkerMaxStaleness    = 3 * time.Second
	assistantRunWorkerMaxStaleness = 10 * time.Second
	skillDataControlLeaseTTL       = 30 * time.Second
)

func startAssistantBackgroundWorkers(
	runtime *assistantAPIRuntime,
	infrastructure *assistantInfrastructure,
	assistant *assistantComponents,
) (*assistantBackgroundWorkers, error) {
	deps := infrastructure.dependencies
	if deps.learningProjection == nil {
		return nil, dependencyError(
			"mongodb.rm_assistant_learning_projection",
			"wiring",
			errors.New("assistant learning projection is required"),
		)
	}
	runTerminalRelay := runruntime.NewTerminalRunRelay(
		deps.runRepository,
		[]runruntime.TerminalEventHandler{
			runruntime.TerminalEventHandlerFunc(func(
				ctx context.Context,
				event runruntime.TerminalEvent,
			) error {
				value := 0.0
				if event.Outcome == "completed" {
					value = 1.0
				}
				_, appendErr := assistant.learningFactService.AppendServiceFact(
					ctx,
					learningmodel.AppendCommand{
						EventID:          "turn:" + event.RunID + ":completion",
						FactType:         learningmodel.FactTypeServiceScorecard,
						AssistantTurnID:  event.RunID,
						ReferralSource:   "service",
						DomainID:         event.DomainID,
						MetricID:         "turn_completion",
						MetricValue:      value,
						MetricSource:     "service_auto",
						TrainingEligible: false,
						OccurredAt:       event.OccurredAt,
					},
				)
				return appendErr
			}),
			runruntime.TerminalEventHandlerFunc(func(
				ctx context.Context,
				event runruntime.TerminalEvent,
			) error {
				return compactAssistantSessionFromTerminalEvent(
					ctx,
					event,
					deps.runRepository,
					assistant.sessionCompactor,
					assistant.runHooks,
				)
			}),
		},
		runtime.instanceID+":assistant-run-terminal-learning",
		learningOutboxRelayInterval,
		128,
	)
	subscriptionScheduler, err := scheduling.NewSkillSubscriptionScheduler(
		assistant.service,
		skillSubscriptionCronInterval,
		slog.Default(),
	)
	if err != nil {
		return nil, dependencyError(
			"skill-subscription-scheduler",
			"initialization",
			err,
		)
	}
	learningProjectionScheduler, err := learningprojection.NewScheduler(
		deps.learningProjection,
		learningProjectionInterval,
		256,
		slog.Default(),
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-learning-projection-scheduler",
			"initialization",
			err,
		)
	}
	learningOutboxRelay, err := learningmessaging.NewOutboxRelay(
		deps.learningFactStore,
		infrastructure.messageTransport,
		learningOutboxRelayInterval,
		128,
		slog.Default(),
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-learning-fact-outbox-relay",
			"initialization",
			err,
		)
	}
	policyReleaseOutboxRelay, err := policymessaging.NewOutboxRelay(
		"release",
		deps.policyReleaseStore,
		infrastructure.messageTransport,
		learningOutboxRelayInterval,
		128,
		slog.Default(),
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-policy-release-outbox-relay",
			"initialization",
			err,
		)
	}
	policyRolloutOutboxRelay, err := policymessaging.NewOutboxRelay(
		"rollout",
		deps.policyRolloutStore,
		infrastructure.messageTransport,
		learningOutboxRelayInterval,
		128,
		slog.Default(),
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-policy-rollout-outbox-relay",
			"initialization",
			err,
		)
	}
	consumer := messaging.NewAssistantMentionedConsumerWithTransport(
		infrastructure.messageTransport,
		assistant.service,
		runtime.instanceID,
		slog.Default(),
	)
	placementProjector := placementapplication.NewMembershipProjector(
		deps.placementStore,
		func() time.Time { return time.Now().UTC() },
	)
	placementConsumer := placementmessaging.NewAssistantMembershipConsumer(
		infrastructure.messageTransport,
		placementProjector,
		runtime.instanceID,
		slog.Default(),
	)
	runProfiles, err := runruntime.DefaultReasoningProfileCatalog()
	if err != nil {
		return nil, dependencyError(
			"assistant-run-reasoning-profiles",
			"initialization",
			err,
		)
	}
	runWorker := runruntime.NewConfiguredDurableWorker(
		deps.runRepository,
		deps.runRepository,
		assistant.durableExecutor,
		runtime.instanceID,
		runProfiles,
		assistant.runHooks,
	)
	subscriptionUseCases := subscriptionapplication.NewUseCases(
		deps.subscriptionStore,
		assistant.chatGroundingClient,
		assistant.service,
		time.Now,
	)
	dataControlWorker, err := datacontrolapplication.NewWorker(
		deps.dataControlStore,
		datacontrol.NewExecutor(
			deps.skillActivityStore,
			assistant.consentCommands,
			subscriptionUseCases,
			deps.subscriptionReader,
		),
		runtime.instanceID+":skill-data-control",
		assistantConsumerPollInterval,
		skillDataControlLeaseTTL,
		time.Now,
	)
	if err != nil {
		return nil, dependencyError(
			"skill-data-control-worker",
			"initialization",
			err,
		)
	}

	workerSpecs := []assistantBackgroundWorkerSpec{
		{
			name: "assistant_run_terminal_relay",
			run:  runTerminalRelay.Run,
			health: func(ctx context.Context) error {
				return runTerminalRelay.Healthy(
					ctx,
					3*learningOutboxRelayInterval,
				)
			},
		},
		{
			name: "assistant_skill_subscription_scheduler",
			run:  subscriptionScheduler.Run,
			health: func(ctx context.Context) error {
				return subscriptionScheduler.Healthy(
					ctx,
					3*skillSubscriptionCronInterval,
				)
			},
		},
		{
			name: "assistant_learning_projection_scheduler",
			run:  learningProjectionScheduler.Run,
			health: func(ctx context.Context) error {
				return learningProjectionScheduler.Healthy(
					ctx,
					3*learningProjectionInterval,
				)
			},
		},
		{
			name: "assistant_learning_fact_outbox_relay",
			run:  learningOutboxRelay.Run,
			health: func(ctx context.Context) error {
				return learningOutboxRelay.Healthy(
					ctx,
					3*learningOutboxRelayInterval,
				)
			},
		},
		{
			name: "assistant_policy_release_outbox_relay",
			run:  policyReleaseOutboxRelay.Run,
			health: func(ctx context.Context) error {
				return policyReleaseOutboxRelay.Healthy(
					ctx,
					3*learningOutboxRelayInterval,
				)
			},
		},
		{
			name: "assistant_policy_rollout_outbox_relay",
			run:  policyRolloutOutboxRelay.Run,
			health: func(ctx context.Context) error {
				return policyRolloutOutboxRelay.Healthy(
					ctx,
					3*learningOutboxRelayInterval,
				)
			},
		},
		{
			name: "assistant_mentioned_consumer",
			run: func(ctx context.Context) {
				consumer.Run(ctx, assistantConsumerPollInterval)
			},
			health: func(ctx context.Context) error {
				return consumer.Healthy(ctx, assistantWorkerMaxStaleness)
			},
		},
		{
			name: "assistant_membership_consumer",
			run: func(ctx context.Context) {
				placementConsumer.Run(ctx, assistantConsumerPollInterval)
			},
			health: func(ctx context.Context) error {
				return placementConsumer.Healthy(
					ctx,
					assistantWorkerMaxStaleness,
				)
			},
		},
		{
			name: "assistant_durable_run_worker",
			run:  runWorker.Run,
			health: func(ctx context.Context) error {
				return runWorker.Healthy(ctx, assistantRunWorkerMaxStaleness)
			},
		},
		{
			name: "assistant_skill_data_control_worker",
			run:  dataControlWorker.Run,
			health: func(ctx context.Context) error {
				return dataControlWorker.Healthy(
					ctx,
					assistantWorkerMaxStaleness,
				)
			},
		},
	}
	workers, err := newAssistantBackgroundWorkers(
		workerSpecs,
		assistantShutdownTimeout(),
		slog.Default(),
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-background-worker-supervisor",
			"initialization",
			err,
		)
	}
	committed := false
	defer func() {
		if !committed {
			_ = workers.Close()
		}
	}()

	preflightCtx, cancelPreflight := context.WithTimeout(
		context.Background(),
		dependencyProbeTimeout,
	)
	defer cancelPreflight()
	if err := infrastructure.messageTransport.SetDurableRetention(
		preflightCtx,
		learningmessaging.LearningFactStream,
		learningmessaging.LearningFactStreamRetention,
	); err != nil {
		return nil, dependencyError(
			"assistant-learning-fact-event-stream",
			"retention",
			err,
		)
	}
	if err := consumer.EnsureGroup(preflightCtx); err != nil {
		return nil, dependencyError(
			"assistant-mentioned-consumer",
			"consumer-group",
			err,
		)
	}
	if err := placementConsumer.EnsureGroup(preflightCtx); err != nil {
		return nil, dependencyError(
			"assistant-membership-consumer",
			"consumer-group",
			err,
		)
	}
	for _, worker := range workers.workers {
		worker := worker
		infrastructure.healthChecker.Register(worker.spec.name, worker.Healthy)
	}
	workers.Start()
	committed = true

	log.Printf(
		"assistant-service run terminal relay enabled interval=%s",
		learningOutboxRelayInterval,
	)
	log.Printf(
		"assistant-service skill subscription scheduler enabled interval=%s",
		skillSubscriptionCronInterval,
	)
	log.Printf(
		"assistant-service learning projection scheduler enabled interval=%s",
		learningProjectionInterval,
	)
	log.Printf(
		"assistant-service learning fact outbox relay enabled interval=%s",
		learningOutboxRelayInterval,
	)
	log.Printf(
		"assistant-service policy outbox relays enabled interval=%s",
		learningOutboxRelayInterval,
	)
	log.Printf(
		"assistant-service assistant mentioned consumer enabled stream=%s group=%s",
		messaging.AssistantMentionedStream,
		messaging.AssistantMentionedConsumerGroup,
	)
	log.Printf(
		"assistant-service assistant membership consumer enabled stream=%s group=%s",
		placementmessaging.AssistantMembershipStream,
		placementmessaging.AssistantMembershipConsumerGroup,
	)
	log.Printf(
		"assistant-service durable AssistantRun worker enabled workerId=%s",
		runtime.instanceID,
	)
	log.Printf(
		"assistant-service durable SkillDataControlRequest worker enabled workerId=%s leaseTTL=%s",
		runtime.instanceID,
		skillDataControlLeaseTTL,
	)
	return workers, nil
}

func compactAssistantSessionFromTerminalEvent(
	ctx context.Context,
	event runruntime.TerminalEvent,
	runs runruntime.Repository,
	compactor *sessioncompaction.Service,
	hooks *runruntime.HookRegistry,
) error {
	if event.Outcome != "completed" {
		return nil
	}
	if runs == nil || compactor == nil || hooks == nil {
		return errors.New("assistant session terminal compaction is not configured")
	}
	run, err := runs.Load(ctx, event.RunID)
	if err != nil {
		return err
	}
	if run.RunID != event.RunID || run.SessionID != event.SessionID ||
		run.UserID != event.UserID || run.State != assistantgenerated.AssistantRunStateCompleted {
		return errors.New("assistant terminal event does not match completed Run")
	}
	switch strings.ToLower(strings.TrimSpace(run.RequestContext.SurfaceKind)) {
	case "conversation", "circle":
		return nil
	}
	answerText := ""
	if run.TerminalSnapshot != nil {
		answerText = run.TerminalSnapshot.AnswerText
	}
	source := sessioncompaction.CompletedRunSource{
		CompletionEventID: event.EventID,
		RunID:             run.RunID,
		SessionID:         run.SessionID,
		UserID:            run.UserID,
		CurrentGoal:       run.EffectiveGoal(),
		UserInput:         run.InputText,
		AnswerText:        strings.TrimSpace(answerText),
		PendingItems:      pendingSessionItems(run.TaskGraph),
		ConfirmedSlots:    run.ConfirmedSlotSnapshot(),
		CompletedAt:       event.OccurredAt,
	}
	hookCtx := runruntime.WithExecutionHooks(ctx, hooks, run)
	preCompact, err := runruntime.InvokeExecutionHook(
		hookCtx,
		runruntime.HookPreCompact,
		"task_root",
		"",
		map[string]any{
			"userInput":  source.UserInput,
			"answerText": source.AnswerText,
		},
	)
	if err != nil {
		return err
	}
	if preCompact.Decision != runruntime.HookAllow {
		return fmt.Errorf(
			"pre_compact hook %s: %s",
			preCompact.Decision,
			strings.TrimSpace(preCompact.Reason),
		)
	}
	if value, ok := preCompact.Data["userInput"].(string); ok &&
		strings.TrimSpace(value) != "" {
		source.UserInput = strings.TrimSpace(value)
	}
	if value, ok := preCompact.Data["answerText"].(string); ok &&
		strings.TrimSpace(value) != "" {
		source.AnswerText = strings.TrimSpace(value)
	}
	summary, err := compactor.CompactCompletedRun(ctx, source)
	if err != nil {
		return err
	}
	postCompact, err := runruntime.InvokeExecutionHook(
		hookCtx,
		runruntime.HookPostCompact,
		"task_root",
		"",
		map[string]any{
			"summaryId": summary.SummaryID,
			"turnCount": summary.TurnCount,
			"textRunes": len([]rune(summary.Text)),
		},
	)
	if err != nil {
		return err
	}
	if postCompact.Decision != runruntime.HookAllow {
		return fmt.Errorf(
			"post_compact hook %s: %s",
			postCompact.Decision,
			strings.TrimSpace(postCompact.Reason),
		)
	}
	return nil
}

func pendingSessionItems(graph runruntime.TaskGraph) []string {
	items := make([]string, 0, len(graph.Tasks))
	for _, task := range graph.Tasks {
		switch task.Status {
		case assistantgenerated.AssistantTaskStatusCompleted,
			assistantgenerated.AssistantTaskStatusCancelled:
			continue
		}
		if value := strings.TrimSpace(task.Goal); value != "" {
			items = append(items, value)
		}
	}
	return items
}
