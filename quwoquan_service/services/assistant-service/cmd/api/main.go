package main

import (
	"context"
	"errors"
	"fmt"
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
	httpadapter "quwoquan_service/services/assistant-service/internal/adapters/http"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/infrastructure/chatclient"
	"quwoquan_service/services/assistant-service/internal/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/infrastructure/notificationclient"
	"quwoquan_service/services/assistant-service/internal/infrastructure/userprofile"
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
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return fmt.Errorf("access token config invalid: %w", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return fmt.Errorf("access token verifier invalid: %w", err)
	}
	addr := getenvOrDefault("ASSISTANT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18087"
	}
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())
	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, robs.TraceLogLevelInfo, nil)
	if err != nil {
		return fmt.Errorf("process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
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
	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "assistant-service", SamplingRatio: 0.1})
	defer otelShutdown()

	healthChecker := rthealth.NewChecker()
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

	publisher := messaging.NewRedisEventPublisher(router.Scene("general"), serviceName, nil)
	assistantOpts := []application.AssistantServiceOption{
		application.WithLearningProfileStore(deps.profileStore),
		application.WithEventPublisher(publisher),
		application.WithNotificationAppMessageCommandWriter(notificationWriter),
		application.WithSkillSubscriptionStore(deps.subscriptionStore),
		application.WithAgentLoop(buildAgentLoop(cfg, appEnv)),
	}
	chatGroundingEnabled := false
	if userProfileBase := strings.TrimSpace(cfg.UserProfile.BaseURL); userProfileBase != "" {
		interestReader := userprofile.NewClient(searchHTTPClient(cfg.UserProfile.TimeoutMs), userProfileBase)
		assistantOpts = append(assistantOpts, application.WithProactiveInterestReader(interestReader))
		log.Printf("assistant-service proactive interest profile reader enabled base=%s", userProfileBase)
	} else {
		log.Printf("assistant-service proactive interest profile reader disabled (no user_profile.base_url)")
	}
	if chatBase := strings.TrimSpace(cfg.ChatService.BaseURL); chatBase != "" {
		assistantOpts = append(assistantOpts, application.WithChatGroundingClient(chatclient.NewClient(searchHTTPClient(cfg.ChatService.TimeoutMs), chatBase)))
		chatGroundingEnabled = true
		log.Printf("assistant-service chat grounding client enabled base=%s", chatBase)
	} else {
		log.Printf("assistant-service chat grounding client disabled (no chat_service.base_url)")
	}
	service := application.NewAssistantService(
		deps.eventStore,
		deps.consentStore,
		router.Scene("general"),
		assistantOpts...,
	)
	serviceCtx, serviceCancel := context.WithCancel(context.Background())
	defer serviceCancel()
	if chatGroundingEnabled {
		consumer := messaging.NewAssistantMentionedConsumer(
			router.Scene("general"),
			service,
			instanceID,
			slog.Default(),
		)
		go consumer.Run(serviceCtx, 500*time.Millisecond)
		log.Printf("assistant-service assistant mentioned consumer enabled stream=%s group=%s", messaging.AssistantMentionedStream, messaging.AssistantMentionedConsumerGroup)
	}
	baseHandler := httpadapter.NewHandler(service).Routes()
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
			AccessTokenVerifier: accessVerifier,
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
