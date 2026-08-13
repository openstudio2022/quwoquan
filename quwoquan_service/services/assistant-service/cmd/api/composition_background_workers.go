package bootstrap

import (
	"context"
	"errors"
	"log"
	"log/slog"
	"time"

	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	learningmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/messaging"
	learningprojection "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/projection"
	policymessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/messaging"
	rolloutmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/messaging"
	sessionstream "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/stream"
	sessioncompaction "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/compaction"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/scheduling"
	datacontrolapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/application"
	datacontrolports "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/ports"
	datacontrol "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/infrastructure/control"
	datacontrolmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/infrastructure/messaging"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
	subscriptionmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/infrastructure/messaging"
	placementapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	placementports "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/ports"
	placementmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/messaging"
	settingapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/application"
	settingports "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/ports"
	settingmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/infrastructure/messaging"
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
	runTerminalPublisher, err := runmessaging.NewTerminalEventPublisher(
		infrastructure.messageTransport,
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-run-terminal-event-stream",
			"initialization",
			err,
		)
	}
	runTerminalRelay := runruntime.NewTerminalRunRelay(
		deps.runRepository,
		runTerminalPublisher,
		[]runruntime.TerminalEventHandler{
			runruntime.TerminalEventHandlerFunc(func(
				ctx context.Context,
				event runruntime.TerminalEvent,
			) error {
				_, appendErr := assistant.learningFactService.AppendTerminalRun(
					ctx,
					learningapplication.TerminalRunEvent{
						RunID:      event.RunID,
						DomainID:   event.DomainID,
						Outcome:    event.Outcome,
						OccurredAt: event.OccurredAt,
					},
				)
				return appendErr
			}),
			sessioncompaction.NewAssistantRunTerminalCoordinator(
				deps.runRepository,
				assistant.sessionCompactor,
				assistant.runHooks,
			),
		},
		runtime.instanceID+":assistant-run-terminal-learning",
		learningOutboxRelayInterval,
		128,
	)
	runStopHookRelay := runruntime.NewStopHookRelay(
		deps.runRepository,
		assistant.runHooks,
		runtime.instanceID+":assistant-run-stop-hooks",
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
	policyRolloutOutboxRelay, err := rolloutmessaging.NewOutboxRelay(
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
	sessionOutboxStore, ok := deps.sessionStore.(sessionports.SessionOutboxStore)
	if !ok {
		return nil, dependencyError(
			"mongodb.assistant_session_outbox",
			"wiring",
			errors.New(
				"assistant session store must own the transactional outbox",
			),
		)
	}
	sessionOutboxRelay, err := messaging.NewSessionOutboxRelay(
		sessionOutboxStore,
		infrastructure.messageTransport,
		learningOutboxRelayInterval,
		128,
		slog.Default(),
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-session-outbox-relay",
			"initialization",
			err,
		)
	}
	placementOutbox, ok := deps.placementStore.(placementports.TransactionalOutbox)
	if !ok {
		return nil, dependencyError(
			"postgres.skill_surface_placement_outbox",
			"wiring",
			errors.New("skill surface placement store must own the transactional outbox"),
		)
	}
	placementEventPublisher, err := placementmessaging.NewEventPublisher(
		infrastructure.messageTransport,
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-skill-surface-placement-event-stream",
			"initialization",
			err,
		)
	}
	placementOutboxRelay, err := placementapplication.NewOutboxRelay(
		placementOutbox,
		placementEventPublisher,
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-skill-surface-placement-outbox-relay",
			"initialization",
			err,
		)
	}
	settingOutbox, ok := deps.settingStore.(settingports.TransactionalOutbox)
	if !ok {
		return nil, dependencyError(
			"postgres.skill_user_setting_outbox",
			"wiring",
			errors.New("skill user setting store must own the transactional outbox"),
		)
	}
	settingEventPublisher, err := settingmessaging.NewEventPublisher(
		infrastructure.messageTransport,
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-skill-user-setting-event-stream",
			"initialization",
			err,
		)
	}
	settingOutboxRelay, err := settingapplication.NewOutboxRelay(
		settingOutbox,
		settingEventPublisher,
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-skill-user-setting-outbox-relay",
			"initialization",
			err,
		)
	}
	if deps.dataControlStore == nil {
		return nil, dependencyError(
			"mongodb.skill_data_control_outbox",
			"wiring",
			errors.New("skill data control store must own the transactional outbox"),
		)
	}
	var dataControlOutbox datacontrolports.TransactionalOutbox = deps.dataControlStore
	dataControlEventPublisher, err := datacontrolmessaging.NewEventPublisher(
		infrastructure.messageTransport,
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-skill-data-control-event-stream",
			"initialization",
			err,
		)
	}
	dataControlOutboxRelay, err := datacontrolapplication.NewOutboxRelay(
		dataControlOutbox,
		dataControlEventPublisher,
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-skill-data-control-outbox-relay",
			"initialization",
			err,
		)
	}
	subscriptionOutbox, ok := deps.subscriptionStore.(subscriptionports.TransactionalOutbox)
	if !ok {
		return nil, dependencyError(
			"mongodb.skill_subscription_outbox",
			"wiring",
			errors.New("skill subscription store must own the transactional outbox"),
		)
	}
	subscriptionEventPublisher, err := subscriptionmessaging.NewEventPublisher(
		infrastructure.messageTransport,
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-skill-subscription-event-stream",
			"initialization",
			err,
		)
	}
	subscriptionOutboxRelay, err := subscriptionapplication.NewOutboxRelay(
		subscriptionOutbox,
		subscriptionEventPublisher,
	)
	if err != nil {
		return nil, dependencyError(
			"assistant-skill-subscription-outbox-relay",
			"initialization",
			err,
		)
	}
	consumer := sessionstream.NewAssistantMentionedConsumerWithTransport(
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
			name: "assistant_run_stop_hook_relay",
			run:  runStopHookRelay.Run,
			health: func(ctx context.Context) error {
				return runStopHookRelay.Healthy(
					ctx,
					3*learningOutboxRelayInterval,
				)
			},
		},
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
			name: "assistant_session_outbox_relay",
			run:  sessionOutboxRelay.Run,
			health: func(ctx context.Context) error {
				return sessionOutboxRelay.Healthy(
					ctx,
					3*learningOutboxRelayInterval,
				)
			},
		},
		{
			name: "assistant_skill_surface_placement_outbox_relay",
			run: func(ctx context.Context) {
				placementOutboxRelay.Run(ctx, learningOutboxRelayInterval)
			},
			health: func(ctx context.Context) error {
				return placementOutboxRelay.Healthy(
					ctx,
					3*learningOutboxRelayInterval,
				)
			},
		},
		{
			name: "assistant_skill_user_setting_outbox_relay",
			run: func(ctx context.Context) {
				settingOutboxRelay.Run(ctx, learningOutboxRelayInterval)
			},
			health: func(ctx context.Context) error {
				return settingOutboxRelay.Healthy(
					ctx,
					3*learningOutboxRelayInterval,
				)
			},
		},
		{
			name: "assistant_skill_data_control_outbox_relay",
			run: func(ctx context.Context) {
				dataControlOutboxRelay.Run(ctx, learningOutboxRelayInterval)
			},
			health: func(ctx context.Context) error {
				return dataControlOutboxRelay.Healthy(
					ctx,
					3*learningOutboxRelayInterval,
				)
			},
		},
		{
			name: "assistant_skill_subscription_outbox_relay",
			run: func(ctx context.Context) {
				subscriptionOutboxRelay.Run(ctx, learningOutboxRelayInterval)
			},
			health: func(ctx context.Context) error {
				return subscriptionOutboxRelay.Healthy(
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
	if err := infrastructure.messageTransport.SetDurableRetention(
		preflightCtx,
		runmessaging.AssistantRunEventStream,
		runmessaging.AssistantRunEventRetention,
	); err != nil {
		return nil, dependencyError(
			"assistant-run-event-stream",
			"retention",
			err,
		)
	}
	if err := infrastructure.messageTransport.SetDurableRetention(
		preflightCtx,
		rolloutmessaging.PolicyRolloutAuditStream,
		rolloutmessaging.PolicyRolloutAuditStreamRetention,
	); err != nil {
		return nil, dependencyError(
			"assistant-policy-rollout-event-stream",
			"retention",
			err,
		)
	}
	if err := infrastructure.messageTransport.SetDurableRetention(
		preflightCtx,
		datacontrolmessaging.SkillDataControlEventStream,
		datacontrolmessaging.SkillDataControlEventRetention,
	); err != nil {
		return nil, dependencyError(
			"assistant-skill-data-control-event-stream",
			"retention",
			err,
		)
	}
	if err := infrastructure.messageTransport.SetDurableRetention(
		preflightCtx,
		subscriptionmessaging.SkillSubscriptionEventStream,
		subscriptionmessaging.SkillSubscriptionEventRetention,
	); err != nil {
		return nil, dependencyError(
			"assistant-skill-subscription-event-stream",
			"retention",
			err,
		)
	}
	if err := infrastructure.messageTransport.SetDurableRetention(
		preflightCtx,
		messaging.SessionEventStream,
		messaging.SessionEventStreamRetention,
	); err != nil {
		return nil, dependencyError(
			"assistant-session-event-stream",
			"retention",
			err,
		)
	}
	if err := infrastructure.messageTransport.SetDurableRetention(
		preflightCtx,
		placementmessaging.SkillSurfacePlacementEventStream,
		placementmessaging.SkillSurfacePlacementEventRetention,
	); err != nil {
		return nil, dependencyError(
			"assistant-skill-surface-placement-event-stream",
			"retention",
			err,
		)
	}
	if err := infrastructure.messageTransport.SetDurableRetention(
		preflightCtx,
		settingmessaging.SkillUserSettingEventStream,
		settingmessaging.SkillUserSettingEventRetention,
	); err != nil {
		return nil, dependencyError(
			"assistant-skill-user-setting-event-stream",
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
		"assistant-service run stop hook relay enabled interval=%s",
		learningOutboxRelayInterval,
	)
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
		"assistant-service session outbox relay enabled stream=%s interval=%s",
		messaging.SessionEventStream,
		learningOutboxRelayInterval,
	)
	log.Printf(
		"assistant-service SkillSurfacePlacement outbox relay enabled stream=%s interval=%s",
		placementmessaging.SkillSurfacePlacementEventStream,
		learningOutboxRelayInterval,
	)
	log.Printf(
		"assistant-service SkillUserSetting outbox relay enabled stream=%s interval=%s",
		settingmessaging.SkillUserSettingEventStream,
		learningOutboxRelayInterval,
	)
	log.Printf(
		"assistant-service SkillDataControlRequest outbox relay enabled stream=%s interval=%s",
		datacontrolmessaging.SkillDataControlEventStream,
		learningOutboxRelayInterval,
	)
	log.Printf(
		"assistant-service SkillSubscription outbox relay enabled stream=%s interval=%s",
		subscriptionmessaging.SkillSubscriptionEventStream,
		learningOutboxRelayInterval,
	)
	log.Printf(
		"assistant-service assistant mentioned consumer enabled stream=%s group=%s",
		sessionstream.AssistantMentionedStream,
		sessionstream.AssistantMentionedConsumerGroup,
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
