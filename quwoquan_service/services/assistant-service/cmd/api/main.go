package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	learninghttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/adapters/inbound/http"
	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	learningmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/messaging"
	learningprojection "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/projection"
	policyreleasehttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/adapters/inbound/http"
	policyreleaseapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	policymessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/messaging"
	policyrollouthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/adapters/inbound/http"
	policyrolloutapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	preferencefact "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	httpadapter "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	assistantdomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/chatclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/creationgrounding"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/intersectionclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/notificationclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/scheduling"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/searchclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/userprofile"
	turnviewhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/adapters/inbound/http"
	turnviewapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/application"
	skillcataloghttp "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/adapters/inbound/http"
	skillcatalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	skillcatalogports "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/ports"
	skillcatalogresource "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	consenthttp "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/adapters/inbound/http"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
)

const (
	dependencyHealthResponseDrainLimitBytes = 4 << 10
	skillSubscriptionCronInterval           = time.Minute
	learningProjectionInterval              = time.Second
	learningOutboxRelayInterval             = time.Second
)

func main() {
	if err := run(); err != nil {
		logStartupFailure(err)
		os.Exit(1)
	}
}

func run() error {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		return fmt.Errorf("runtime identity invalid: %w", err)
	}
	runtimeConfigProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		return fmt.Errorf("config load failed: %w", err)
	}
	if err := applyEnvOverrides(&cfg); err != nil {
		return fmt.Errorf("environment override invalid: %w", err)
	}
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion); err != nil {
		return fmt.Errorf("config identity failed: %w", err)
	}
	if err := validateRuntimeDependenciesConfig(cfg); err != nil {
		return err
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeConfigProvider,
	)
	if err != nil {
		return fmt.Errorf("access token config invalid: %w", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return fmt.Errorf("access token verifier invalid: %w", err)
	}
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return fmt.Errorf("account security authority credential init failed: %w", err)
	}
	accountSecurityAuthorityTimeout := time.Duration(
		cfg.AccountSecurityAuthority.TimeoutMs,
	) * time.Millisecond
	accountSecurityAuthority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     cfg.AccountSecurityAuthority.BaseURL,
			HTTPClient:  &http.Client{Timeout: accountSecurityAuthorityTimeout},
			Credentials: accountSecurityAuthorityCredentials,
			Timeout:     accountSecurityAuthorityTimeout,
		},
	)
	if err != nil {
		return fmt.Errorf("account security authority config invalid: %w", err)
	}
	addr := getenvOrDefault("ASSISTANT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18087"
	}
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())
	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		return fmt.Errorf("runtime log exporter init failed: %w", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, robs.TraceLogLevelInfo, nil)
	if err != nil {
		return fmt.Errorf("process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		return fmt.Errorf("exception logger init failed: %w", err)
	}
	ctx := context.Background()
	router, err := buildRedisRouter(cfg)
	if err != nil {
		return err
	}
	defer func() {
		if err := router.Close(); err != nil {
			log.Printf("WARN: assistant-service redis close: %v", err)
		}
	}()
	redisProbeCtx, redisProbeCancel := context.WithTimeout(ctx, dependencyProbeTimeout)
	if err := router.PingAll(redisProbeCtx); err != nil {
		redisProbeCancel()
		return dependencyError("redis", "connectivity", err)
	}
	redisProbeCancel()
	messageTransport, err := requireAssistantAPIMessageTransport(
		ctx,
		appEnv,
		router,
		map[string]string{
			"general": cfg.Redis.General.Mode,
		},
	)
	if err != nil {
		return dependencyError("runtime.message.transport", "preflight", err)
	}
	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "assistant-service", SamplingRatio: 0.1})
	defer otelShutdown()

	healthChecker := rthealth.NewChecker()
	healthChecker.Register("account_security_authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	healthChecker.Register("redis", func(ctx context.Context) error {
		return router.PingAll(ctx)
	})

	deps, err := openPersistentDependencies(ctx, cfg)
	if err != nil {
		return err
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), dependencyProbeTimeout)
		defer cancel()
		if err := deps.Close(closeCtx); err != nil {
			log.Printf("WARN: assistant-service persistent dependency close: %v", err)
		}
	}()
	healthChecker.Register("mongodb", func(ctx context.Context) error {
		return deps.mongoClient.Ping(ctx, nil)
	})
	healthChecker.Register("postgres", func(ctx context.Context) error {
		return deps.postgresPool.Ping(ctx)
	})
	log.Printf("assistant-service events storage=mongodb db=%s", cfg.MongoDB.Database)
	log.Printf("assistant-service learning projection storage=mongodb db=%s", cfg.MongoDB.Database)
	log.Printf("assistant-service skill subscription storage=mongodb db=%s", cfg.MongoDB.Database)
	log.Printf("assistant-service consent storage=postgres")

	notificationCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{"notification.app_message.create"},
	)
	if err != nil {
		return dependencyError("notification-service", "credentials", err)
	}
	notificationHTTPConfig := rthttp.DefaultHTTPClientFactoryConfig()
	notificationHTTPConfig.Timeout = providerTimeout(cfg.NotificationService.TimeoutMs)
	notificationHTTPConfig.MaxRetries = 0
	notificationHTTPConfig.RetryBackoff = 0
	notificationHTTPConfig.RetryOnCodes = map[int]struct{}{}
	notificationObservedClient := rthttp.NewObservedHTTPClient(
		nil,
		notificationHTTPConfig,
		rthttp.HTTPClientMiddlewareConfig{
			Service:           "assistant-service",
			Origin:            "cloud",
			Direction:         "outbound",
			SourceID:          "assistant-service.notification-command",
			Src:               "assistant-service",
			ServiceName:       "assistant-service",
			ServiceInstanceID: instanceID,
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	notificationWriter, err := notificationclient.NewClient(
		rtgov.WrapClientWithCB(
			notificationObservedClient,
			rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default()),
		),
		cfg.NotificationService.BaseURL,
		notificationCredentials,
	)
	if err != nil {
		return dependencyError("notification-service", "initialization", err)
	}
	healthChecker.Register("notification_service", func(ctx context.Context) error {
		return checkServiceHealth(
			ctx,
			notificationObservedClient,
			cfg.NotificationService.BaseURL,
		)
	})

	newObservedEgressClient := func(sourceID string, timeoutMs int) *http.Client {
		httpConfig := rthttp.DefaultHTTPClientFactoryConfig()
		httpConfig.Timeout = providerTimeout(timeoutMs)
		observed := rthttp.NewObservedHTTPClient(
			nil,
			httpConfig,
			rthttp.HTTPClientMiddlewareConfig{
				Service:           "assistant-service",
				Origin:            "cloud",
				Direction:         "outbound",
				SourceID:          sourceID,
				Src:               "assistant-service",
				ServiceName:       "assistant-service",
				ServiceInstanceID: instanceID,
			},
			ioLogger,
			processLogger,
			exceptionLogger,
		)
		return rtgov.WrapClientWithCB(
			observed,
			rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default()),
		)
	}
	deliveryPolicyAuthorization, err :=
		rtauth.NewHS256ServiceAuthorizationProvider(
			accessTokenConfig,
			"assistant-service",
			[]string{"user.assistant_delivery_policy.read"},
		)
	if err != nil {
		return dependencyError("user-service", "credentials", err)
	}
	deliveryPolicyHTTPClient := newObservedEgressClient(
		"assistant-service.user-delivery-policy",
		cfg.UserService.TimeoutMs,
	)
	deliveryPolicyReader, err := orchestration.NewUserDeliveryPolicyClient(
		cfg.UserService.BaseURL,
		deliveryPolicyAuthorization,
		deliveryPolicyHTTPClient,
	)
	if err != nil {
		return dependencyError("user-service", "delivery-policy-reader", err)
	}
	healthChecker.Register("user_service", func(ctx context.Context) error {
		return checkServiceHealth(
			ctx,
			deliveryPolicyHTTPClient,
			cfg.UserService.BaseURL,
		)
	})
	canonicalSearch, err := searchclient.New(
		cfg.SearchService.BaseURL,
		newObservedEgressClient(
			"assistant-service.search-query",
			cfg.SearchService.TimeoutMs,
		),
	)
	if err != nil {
		return dependencyError("search-service", "initialization", err)
	}
	creationGroundingClient, err := creationgrounding.New(
		canonicalSearch,
		cfg.EntityService.BaseURL,
		newObservedEgressClient(
			"assistant-service.entity-homepage-query",
			cfg.EntityService.TimeoutMs,
		),
	)
	if err != nil {
		return dependencyError("creation-grounding", "initialization", err)
	}
	intersectionAuthorization, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{"content.my_intersections.read"},
	)
	if err != nil {
		return dependencyError("content-service", "credentials", err)
	}
	intersectionInbox, err := intersectionclient.New(intersectionclient.Config{
		BaseURL: cfg.ContentService.BaseURL,
		HTTPClient: newObservedEgressClient(
			"assistant-service.content-intersections",
			cfg.ContentService.TimeoutMs,
		),
		Authorization: intersectionAuthorization,
	})
	if err != nil {
		return dependencyError("content-service", "intersection-reader", err)
	}
	var interestReader sessionports.ProactiveInterestReader
	if userProfileBase := strings.TrimSpace(cfg.UserProfile.BaseURL); userProfileBase != "" {
		interestReader = userprofile.NewClient(
			searchHTTPClient(cfg.UserProfile.TimeoutMs),
			userProfileBase,
		)
		log.Printf("assistant-service context interest resolver enabled base=%s", userProfileBase)
	} else {
		log.Printf("assistant-service context interest resolver disabled (no user_profile.base_url)")
	}
	agentLoop, err := buildAgentLoop(
		appEnv,
		canonicalSearch,
		cfg.Model,
		runtimeconfig.EnvRuntimeConfigProvider{},
		newObservedEgressClient,
		deps.publicWebEvidence,
		deps.publicWebBudget,
		deps.sessionRunStore,
		deps.subscriptionStore,
		interestReader,
		deps.consentStore,
	)
	if err != nil {
		return dependencyError("assistant-agent-loop", "initialization", err)
	}

	if deps.preferenceStore == nil || deps.preferenceReader == nil {
		return dependencyError(
			"mongodb.assistant_preferences",
			"wiring",
			errors.New("preference store and reader are required"),
		)
	}
	sessionOwnerReader, ok := deps.sessionRunStore.(preferencefact.SessionOwnerReader)
	if !ok {
		return dependencyError(
			"mongodb.assistant_sessions",
			"wiring",
			errors.New("session owner reader is required"),
		)
	}
	preferenceCommands := preferencefact.NewCommandFacade(
		deps.preferenceStore,
		sessionOwnerReader,
	)
	preferenceQueries := preferencefact.NewQueryFacade(deps.preferenceReader)
	policyReleaseService := policyreleaseapplication.NewService(
		deps.policyReleaseStore,
		nil,
	)
	policyRolloutService := policyrolloutapplication.NewService(
		deps.policyRolloutStore,
		policyReleaseService,
		nil,
	)
	frozenPolicyResolver := sessionports.FrozenPolicyResolverFunc(
		func(
			ctx context.Context,
			policyID string,
			personaID string,
			skillID string,
			domainID string,
		) (assistantdomain.AssistantFrozenPolicySelection, error) {
			resolved, resolveErr := policyRolloutService.ResolveFrozenSelection(
				ctx,
				policyID,
				personaID,
				skillID,
				domainID,
			)
			if resolveErr != nil {
				return assistantdomain.AssistantFrozenPolicySelection{}, resolveErr
			}
			return projectFrozenPolicySelection(resolved), nil
		},
	)
	durableExecutor := runruntime.NewManagedRunExecutor(
		orchestration.NewDurableRunExecutorWithPolicyResolver(
			agentLoop,
			func(
				ctx context.Context,
				request runruntime.ExecutionRequest,
			) (assistantdomain.AssistantFrozenPolicySelection, error) {
				return frozenPolicyResolver.ResolveFrozenPolicy(
					ctx,
					"assistant-default",
					request.UserID,
					request.RequestedSkillID,
					request.RequestedDomainID,
				)
			},
		),
	)
	runCancellation := runruntime.NewCancellationCoordinator(
		durableExecutor,
		10*time.Second,
	)
	runCommands := runruntime.NewCommandService(
		deps.runRepository,
		runruntime.SessionAuthorizerFunc(func(
			ctx context.Context,
			userID string,
			sessionID string,
		) error {
			session, found, readErr := deps.sessionRunStore.GetSession(
				ctx,
				sessionID,
			)
			if readErr != nil {
				return readErr
			}
			if !found || session.UserID != strings.TrimSpace(userID) {
				return runruntime.ErrRunNotFound
			}
			return nil
		}),
		time.Now,
		runCancellation,
	)
	assistantOpts := []orchestration.AssistantServiceOption{
		orchestration.WithLearningProjectionReader(deps.learningProjection),
		orchestration.WithNotificationAppMessageCommandWriter(notificationWriter),
		orchestration.WithSkillSubscriptionStore(deps.subscriptionStore),
		orchestration.WithAssistantDeliveryPolicyReader(deliveryPolicyReader),
		orchestration.WithSessionRunStore(deps.sessionRunStore),
		orchestration.WithPreferenceSnapshotReader(preferenceQueries),
		orchestration.WithCreationSuggestGrounding(creationGroundingClient),
		orchestration.WithXiaoquSearchReader(canonicalSearch),
		orchestration.WithIntersectionInboxReader(intersectionInbox),
		orchestration.WithIntersectionEvidenceReader(intersectionInbox),
		orchestration.WithAgentLoop(agentLoop),
		orchestration.WithRunCommandService(runCommands),
	}
	chatBase := strings.TrimSpace(cfg.ChatService.BaseURL)
	if chatBase == "" {
		return dependencyError(
			"chat-service",
			"configuration",
			errors.New("chat_service.base_url is required"),
		)
	}
	chatHTTPClient := newObservedEgressClient(
		"assistant-service.chat-grounding",
		cfg.ChatService.TimeoutMs,
	)
	chatAuthorization, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{
			"chat.assistant_delivery_membership.read",
			"chat.assistant_grounding.read",
			"chat.assistant_delivery_message.send",
		},
	)
	if err != nil {
		return dependencyError("chat-service", "credentials", err)
	}
	chatGroundingClient, err := chatclient.NewClient(
		chatHTTPClient,
		chatBase,
		chatAuthorization,
	)
	if err != nil {
		return dependencyError("chat-service", "initialization", err)
	}
	assistantOpts = append(
		assistantOpts,
		orchestration.WithChatGroundingClient(
			chatGroundingClient,
		),
	)
	healthChecker.Register("chat_service", func(ctx context.Context) error {
		return checkServiceHealth(ctx, chatHTTPClient, chatBase)
	})
	log.Printf("assistant-service chat grounding client enabled base=%s", chatBase)
	learningFactService := learningapplication.NewService(
		deps.learningFactStore,
		deps.learningRunOwners,
		nil,
	)
	learningOpsQueries := learningapplication.NewOpsQueryService(
		deps.learningProjection,
	)
	assistantOpts = append(
		assistantOpts,
		orchestration.WithLearningFactWriter(
			sessionports.LearningFactWriterFunc(func(
				ctx context.Context,
				command sessionports.ServiceScorecardFactCommand,
			) error {
				_, appendErr := learningFactService.AppendServiceFact(
					ctx,
					learningmodel.AppendCommand{
						EventID:          command.EventID,
						FactType:         learningmodel.FactTypeServiceScorecard,
						AssistantTurnID:  command.AssistantTurnID,
						ReferralSource:   "service",
						DomainID:         command.DomainID,
						MetricID:         command.MetricID,
						MetricValue:      command.MetricValue,
						MetricSource:     command.MetricSource,
						TrainingEligible: false,
						OccurredAt:       command.OccurredAt,
					},
				)
				return appendErr
			}),
		),
	)
	assistantOpts = append(
		assistantOpts,
		orchestration.WithPolicySkillCandidateResolver(
			sessionports.PolicySkillCandidateResolverFunc(
				func(
					ctx context.Context,
					policyID string,
					personaID string,
				) ([]string, error) {
					return policyRolloutService.ResolveSkillCandidates(ctx, policyID, personaID)
				},
			),
		),
		orchestration.WithFrozenPolicyResolver(frozenPolicyResolver),
	)
	service := orchestration.NewAssistantService(
		deps.consentStore,
		router.Scene("general"),
		assistantOpts...,
	)
	consentCommands := consentapplication.NewCommandFacade(
		deps.consentStore,
		func() time.Time { return time.Now().UTC() },
	)
	consentQueries := consentapplication.NewQueryFacade(deps.consentStore)
	serviceCtx, serviceCancel := context.WithCancel(context.Background())
	defer serviceCancel()
	subscriptionScheduler, err := scheduling.NewSkillSubscriptionScheduler(
		service,
		skillSubscriptionCronInterval,
		slog.Default(),
	)
	if err != nil {
		return dependencyError(
			"skill-subscription-scheduler",
			"initialization",
			err,
		)
	}
	go subscriptionScheduler.Run(serviceCtx)
	log.Printf(
		"assistant-service skill subscription scheduler enabled interval=%s",
		skillSubscriptionCronInterval,
	)
	if deps.learningProjection == nil {
		return dependencyError(
			"mongodb.rm_assistant_learning_projection",
			"wiring",
			errors.New("assistant learning projection is required"),
		)
	}
	learningProjectionScheduler, err := learningprojection.NewScheduler(
		deps.learningProjection,
		learningProjectionInterval,
		256,
		slog.Default(),
	)
	if err != nil {
		return dependencyError(
			"assistant-learning-projection-scheduler",
			"initialization",
			err,
		)
	}
	if err := messageTransport.SetDurableRetention(
		serviceCtx,
		learningmessaging.LearningFactStream,
		learningmessaging.LearningFactStreamRetention,
	); err != nil {
		return dependencyError(
			"assistant-learning-fact-event-stream",
			"retention",
			err,
		)
	}
	healthChecker.Register(
		"assistant_learning_projection_scheduler",
		func(ctx context.Context) error {
			return learningProjectionScheduler.Healthy(
				ctx,
				3*learningProjectionInterval,
			)
		},
	)
	go learningProjectionScheduler.Run(serviceCtx)
	log.Printf(
		"assistant-service learning projection scheduler enabled interval=%s",
		learningProjectionInterval,
	)
	learningOutboxRelay, err := learningmessaging.NewOutboxRelay(
		deps.learningFactStore,
		messageTransport,
		learningOutboxRelayInterval,
		128,
		slog.Default(),
	)
	if err != nil {
		return dependencyError(
			"assistant-learning-fact-outbox-relay",
			"initialization",
			err,
		)
	}
	healthChecker.Register(
		"assistant_learning_fact_outbox_relay",
		func(ctx context.Context) error {
			return learningOutboxRelay.Healthy(
				ctx,
				3*learningOutboxRelayInterval,
			)
		},
	)
	go learningOutboxRelay.Run(serviceCtx)
	log.Printf(
		"assistant-service learning fact outbox relay enabled interval=%s",
		learningOutboxRelayInterval,
	)
	policyReleaseOutboxRelay, err := policymessaging.NewOutboxRelay(
		"release",
		deps.policyReleaseStore,
		messageTransport,
		learningOutboxRelayInterval,
		128,
		slog.Default(),
	)
	if err != nil {
		return dependencyError(
			"assistant-policy-release-outbox-relay",
			"initialization",
			err,
		)
	}
	policyRolloutOutboxRelay, err := policymessaging.NewOutboxRelay(
		"rollout",
		deps.policyRolloutStore,
		messageTransport,
		learningOutboxRelayInterval,
		128,
		slog.Default(),
	)
	if err != nil {
		return dependencyError(
			"assistant-policy-rollout-outbox-relay",
			"initialization",
			err,
		)
	}
	healthChecker.Register(
		"assistant_policy_release_outbox_relay",
		func(ctx context.Context) error {
			return policyReleaseOutboxRelay.Healthy(
				ctx,
				3*learningOutboxRelayInterval,
			)
		},
	)
	healthChecker.Register(
		"assistant_policy_rollout_outbox_relay",
		func(ctx context.Context) error {
			return policyRolloutOutboxRelay.Healthy(
				ctx,
				3*learningOutboxRelayInterval,
			)
		},
	)
	go policyReleaseOutboxRelay.Run(serviceCtx)
	go policyRolloutOutboxRelay.Run(serviceCtx)
	log.Printf(
		"assistant-service policy outbox relays enabled interval=%s",
		learningOutboxRelayInterval,
	)
	consumer := messaging.NewAssistantMentionedConsumerWithTransport(
		messageTransport,
		service,
		instanceID,
		slog.Default(),
	)
	go consumer.Run(serviceCtx, 500*time.Millisecond)
	log.Printf("assistant-service assistant mentioned consumer enabled stream=%s group=%s", messaging.AssistantMentionedStream, messaging.AssistantMentionedConsumerGroup)
	runWorker := runruntime.NewDurableWorker(
		deps.runRepository,
		deps.runRepository,
		durableExecutor,
		instanceID,
	)
	go runWorker.Run(serviceCtx)
	log.Printf(
		"assistant-service durable AssistantRun worker enabled workerId=%s",
		instanceID,
	)
	baseHandler := httpadapter.NewHandler(
		service,
		httpadapter.WithPreferenceFacades(
			preferenceCommands,
			preferenceQueries,
		),
		httpadapter.WithRunCommandService(runCommands),
	).Routes()
	skillCatalogQueries := skillcatalogapplication.NewQueryService(
		skillcatalogresource.NewCatalogSource(),
		skillcatalogports.ConsentReaderFunc(func(
			ctx context.Context,
			accountID string,
		) (map[string]string, error) {
			if deps.consentStore == nil {
				return nil, errors.New("skill consent store is not configured")
			}
			consents, err := deps.consentStore.ListActiveConsents(ctx, accountID)
			if err != nil {
				return nil, err
			}
			scopes := make(map[string]string, len(consents))
			for _, consent := range consents {
				scopes[consent.SkillID] = consent.GrantedScope
			}
			return scopes, nil
		}),
	)
	serviceMux := http.NewServeMux()
	consenthttp.NewHandler(consentCommands, consentQueries).RegisterRoutes(serviceMux)
	policyreleasehttp.NewHandler(policyReleaseService).RegisterRoutes(serviceMux)
	policyrollouthttp.NewHandler(policyRolloutService).RegisterRoutes(serviceMux)
	turnviewhttp.NewHandler(
		turnviewapplication.NewQueryFacade(deps.turnViewReader),
	).RegisterRoutes(serviceMux)
	learninghttp.NewHandler(
		learningFactService,
		learningOpsQueries,
	).RegisterRoutes(serviceMux)
	skillcataloghttp.NewHandler(skillCatalogQueries).RegisterRoutes(serviceMux)
	serviceMux.Handle("/", baseHandler)
	baseHandler = serviceMux
	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", httpadapter.GeneratedPrivilegedOperationHandler(baseHandler))
	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "assistant-service",
		ServiceName:       "assistant-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "assistant-service",
		Src:               "assistant-service",
		EndpointResolver:  httpadapter.GeneratedOperationPathTemplateResolver(),
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(corsHandler),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      assistantHTTPWriteTimeout(),
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("assistant-service listening on %s env=%s", addr, appEnv)
	if err := rthttp.ListenAndServeGraceful(server, assistantShutdownTimeout()); err != nil {
		return fmt.Errorf("listen failed: %w", err)
	}
	return nil
}

func checkServiceHealth(
	ctx context.Context,
	client *http.Client,
	baseURL string,
) error {
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		strings.TrimRight(strings.TrimSpace(baseURL), "/")+"/healthz",
		nil,
	)
	if err != nil {
		return err
	}
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if _, err := io.Copy(
		io.Discard,
		io.LimitReader(response.Body, dependencyHealthResponseDrainLimitBytes),
	); err != nil {
		return fmt.Errorf("read dependency health response: %w", err)
	}
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf(
			"dependency health status=%d",
			response.StatusCode,
		)
	}
	return nil
}

func logStartupFailure(err error) {
	logger := slog.New(slog.NewJSONHandler(os.Stderr, nil))
	attributes := []any{
		"service", "assistant-service",
		"error", err.Error(),
	}
	var dependencyFailure *startupDependencyError
	if errors.As(err, &dependencyFailure) {
		attributes = append(
			attributes,
			"dependency", dependencyFailure.Dependency,
			"stage", dependencyFailure.Stage,
		)
	}
	logger.Error("assistant-service startup failed", attributes...)
}

func projectFrozenPolicySelection(
	resolved policyrolloutapplication.FrozenSelection,
) assistantdomain.AssistantFrozenPolicySelection {
	return assistantdomain.AssistantFrozenPolicySelection{
		PolicyID:        resolved.PolicyID,
		ReleaseDigest:   resolved.ReleaseDigest,
		Cohort:          resolved.Cohort,
		RolloutRevision: resolved.RolloutRevision,
		RuleID:          resolved.RuleID,
		Template: assistantdomain.AssistantFrozenPolicyTemplate{
			TemplateID:   resolved.Template.TemplateID,
			SkillID:      resolved.Template.SkillID,
			DomainID:     resolved.Template.DomainID,
			PromptPolicy: resolved.Template.PromptPolicy,
			AllowedTools: append(
				[]string(nil),
				resolved.Template.AllowedTools...,
			),
			SearchIntensity: resolved.Template.SearchIntensity,
		},
		LearningContextPolicy: assistantdomain.AssistantFrozenLearningContextPolicy{
			Enabled: resolved.LearningContextPolicy.Enabled,
			AllowedSignals: append(
				[]string(nil),
				resolved.LearningContextPolicy.AllowedSignals...,
			),
			AllowedMetricIDs: append(
				[]string(nil),
				resolved.LearningContextPolicy.AllowedMetricIDs...,
			),
			AllowedReasonCodes: append(
				[]string(nil),
				resolved.LearningContextPolicy.AllowedReasonCodes...,
			),
			MinimumFeedbackSamples: resolved.LearningContextPolicy.MinimumFeedbackSamples,
			WindowDays:             resolved.LearningContextPolicy.WindowDays,
			SnapshotTrainingEligible: resolved.LearningContextPolicy.
				SnapshotTrainingEligible,
		},
	}
}
