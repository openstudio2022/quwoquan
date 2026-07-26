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
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	httpadapter "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/chatclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/creationgrounding"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/intersectionclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/notificationclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/scheduling"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/searchclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/userprofile"
	preferencefact "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/application"
)

const (
	dependencyHealthResponseDrainLimitBytes = 4 << 10
	skillSubscriptionCronInterval           = time.Minute
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
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		return fmt.Errorf("config compatibility failed: %w", err)
	}
	if err := validateRuntimeDependenciesConfig(cfg); err != nil {
		return err
	}
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
	log.Printf("assistant-service learning profile storage=mongodb db=%s", cfg.MongoDB.Database)
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
	deliveryPolicyReader, err := application.NewUserDeliveryPolicyClient(
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
	agentLoop, err := buildAgentLoop(
		appEnv,
		canonicalSearch,
		runtimeconfig.EnvRuntimeConfigProvider{},
		newObservedEgressClient,
	)
	if err != nil {
		return dependencyError("assistant-agent-loop", "initialization", err)
	}

	publisher := messaging.NewRedisEventPublisherWithTransport(messageTransport, serviceName, nil)
	if deps.preferenceStore == nil || deps.preferenceReader == nil {
		return dependencyError(
			"mongodb.assistant_preference_facts",
			"wiring",
			errors.New("preference store and reader are required"),
		)
	}
	conversationOwnerReader, ok := deps.conversationRunStore.(preferencefact.ConversationOwnerReader)
	if !ok {
		return dependencyError(
			"mongodb.assistant_conversations",
			"wiring",
			errors.New("conversation owner reader is required"),
		)
	}
	preferenceCommands := preferencefact.NewCommandFacade(
		deps.preferenceStore,
		conversationOwnerReader,
	)
	preferenceQueries := preferencefact.NewQueryFacade(deps.preferenceReader)
	assistantOpts := []application.AssistantServiceOption{
		application.WithLearningProfileStore(deps.profileStore),
		application.WithEventPublisher(publisher),
		application.WithNotificationAppMessageCommandWriter(notificationWriter),
		application.WithSkillSubscriptionStore(deps.subscriptionStore),
		application.WithAssistantDeliveryPolicyReader(deliveryPolicyReader),
		application.WithConversationRunStore(deps.conversationRunStore),
		application.WithPreferenceSnapshotReader(preferenceQueries),
		application.WithCreationSuggestGrounding(creationGroundingClient),
		application.WithXiaoquSearchReader(canonicalSearch),
		application.WithIntersectionInboxReader(intersectionInbox),
		application.WithIntersectionEvidenceReader(intersectionInbox),
		application.WithAgentLoop(agentLoop),
	}
	if userProfileBase := strings.TrimSpace(cfg.UserProfile.BaseURL); userProfileBase != "" {
		interestReader := userprofile.NewClient(searchHTTPClient(cfg.UserProfile.TimeoutMs), userProfileBase)
		assistantOpts = append(assistantOpts, application.WithProactiveInterestReader(interestReader))
		log.Printf("assistant-service proactive interest profile reader enabled base=%s", userProfileBase)
	} else {
		log.Printf("assistant-service proactive interest profile reader disabled (no user_profile.base_url)")
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
		application.WithChatGroundingClient(
			chatGroundingClient,
		),
	)
	healthChecker.Register("chat_service", func(ctx context.Context) error {
		return checkServiceHealth(ctx, chatHTTPClient, chatBase)
	})
	log.Printf("assistant-service chat grounding client enabled base=%s", chatBase)
	service := application.NewAssistantService(
		deps.eventStore,
		deps.consentStore,
		router.Scene("general"),
		assistantOpts...,
	)
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
	consumer := messaging.NewAssistantMentionedConsumerWithTransport(
		messageTransport,
		service,
		instanceID,
		slog.Default(),
	)
	go consumer.Run(serviceCtx, 500*time.Millisecond)
	log.Printf("assistant-service assistant mentioned consumer enabled stream=%s group=%s", messaging.AssistantMentionedStream, messaging.AssistantMentionedConsumerGroup)
	baseHandler := httpadapter.NewHandler(
		service,
		httpadapter.WithPreferenceFacades(
			preferenceCommands,
			preferenceQueries,
		),
	).Routes()
	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", baseHandler)
	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "assistant-service",
		ServiceName:       "assistant-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "assistant-service",
		Src:               "assistant-service",
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())
	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(corsHandler)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(rateLimited),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      assistantHTTPWriteTimeout(),
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("assistant-service listening on %s env=%s (rate_limit=1000/s)", addr, appEnv)
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
