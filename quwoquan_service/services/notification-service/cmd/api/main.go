package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rterr "quwoquan_service/runtime/errors"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	httpadapter "quwoquan_service/services/notification-service/internal/adapters/http"
	streamadapter "quwoquan_service/services/notification-service/internal/adapters/stream"
	"quwoquan_service/services/notification-service/internal/application"
	integrationclient "quwoquan_service/services/notification-service/internal/infrastructure/integration"
	"quwoquan_service/services/notification-service/internal/infrastructure/persistence"
	realtimeclient "quwoquan_service/services/notification-service/internal/infrastructure/realtime"
	userclient "quwoquan_service/services/notification-service/internal/infrastructure/user"
)

func main() {
	if err := run(); err != nil {
		log.Fatalf("notification-service: %v", err)
	}
}

func run() error {
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
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return fmt.Errorf("device ticket config invalid: %w", err)
	}
	deviceVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		return fmt.Errorf("device ticket verifier invalid: %w", err)
	}

	ctx, cancelRuntime := context.WithCancel(context.Background())
	defer cancelRuntime()
	otelShutdown := rtotel.MustInit(rtotel.Config{
		ServiceName:   "notification-service",
		SamplingRatio: 0.1,
	})
	defer otelShutdown()

	mongoURI, err := requiredEnv("NOTIFICATION_MONGO_URI", "MONGO_URI")
	if err != nil {
		return err
	}
	mongoDatabase, err := requiredEnv("NOTIFICATION_MONGO_DATABASE", "MONGO_DATABASE")
	if err != nil {
		return err
	}
	integrationBaseURL, err := requiredEnv(
		"NOTIFICATION_INTEGRATION_BASE_URL",
		"INTEGRATION_SERVICE_BASE_URL",
	)
	if err != nil {
		return err
	}
	integrationTimeoutMs, err := requiredPositiveIntEnv("NOTIFICATION_INTEGRATION_TIMEOUT_MS")
	if err != nil {
		return err
	}
	userBaseURL, err := requiredEnv(
		"NOTIFICATION_USER_BASE_URL",
		"USER_SERVICE_BASE_URL",
	)
	if err != nil {
		return err
	}
	realtimeBaseURL, err := requiredEnv(
		"NOTIFICATION_REALTIME_BASE_URL",
		"REALTIME_GATEWAY_BASE_URL",
	)
	if err != nil {
		return err
	}
	dependencyTimeoutMs, err := positiveIntEnvOrDefault(
		"NOTIFICATION_INCOMING_CALL_DEPENDENCY_TIMEOUT_MS",
		500,
	)
	if err != nil {
		return err
	}
	claimPerSecond, err := positiveIntEnvOrDefault(
		"NOTIFICATION_CLAIM_PER_SECOND",
		100,
	)
	if err != nil {
		return err
	}
	dispatchPerSecond, err := positiveIntEnvOrDefault(
		"NOTIFICATION_DISPATCH_PER_SECOND",
		100,
	)
	if err != nil {
		return err
	}
	retryPerSecond, err := positiveIntEnvOrDefault(
		"NOTIFICATION_RETRY_PER_SECOND",
		20,
	)
	if err != nil {
		return err
	}

	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("notification-service runtime log exporter init failed: %v", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	kvFilter := robs.NewKVMetadataFilter(nil)
	processLogger, err := robs.NewProcessTraceLogger(
		standardLogWriter,
		errorLogWriter,
		robs.TraceLogLevelInfo,
		kvFilter,
	)
	if err != nil {
		return fmt.Errorf("process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, kvFilter)
	if err != nil {
		return fmt.Errorf("exception logger init failed: %w", err)
	}
	factoryCfg := rthttp.DefaultHTTPClientFactoryConfig()
	factoryCfg.Timeout = time.Duration(integrationTimeoutMs) * time.Millisecond
	factoryCfg.MaxRetries = -1
	factoryCfg.RetryBackoff = -1
	factoryCfg.RetryOnCodes = map[int]struct{}{}
	observedClient := rthttp.NewObservedHTTPClient(
		nil,
		factoryCfg,
		rthttp.HTTPClientMiddlewareConfig{
			Service:           "notification-service",
			Origin:            "cloud",
			Direction:         "outbound",
			SourceID:          "notification-service.integration-delivery",
			Src:               "notification-service",
			ServiceName:       "notification-service",
			ServiceInstanceID: "local",
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	dependencyFactoryCfg := rthttp.DefaultHTTPClientFactoryConfig()
	dependencyFactoryCfg.Timeout =
		time.Duration(dependencyTimeoutMs) * time.Millisecond
	dependencyFactoryCfg.MaxRetries = -1
	dependencyFactoryCfg.RetryBackoff = -1
	dependencyFactoryCfg.RetryOnCodes = map[int]struct{}{}
	userObservedClient := rthttp.NewObservedHTTPClient(
		nil,
		dependencyFactoryCfg,
		rthttp.HTTPClientMiddlewareConfig{
			Service:           "notification-service",
			Origin:            "cloud",
			Direction:         "outbound",
			SourceID:          "notification-service.user-push-destinations",
			Src:               "notification-service",
			ServiceName:       "notification-service",
			ServiceInstanceID: "local",
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	realtimeObservedClient := rthttp.NewObservedHTTPClient(
		nil,
		dependencyFactoryCfg,
		rthttp.HTTPClientMiddlewareConfig{
			Service:           "notification-service",
			Origin:            "cloud",
			Direction:         "outbound",
			SourceID:          "notification-service.realtime-presence",
			Src:               "notification-service",
			ServiceName:       "notification-service",
			ServiceInstanceID: "local",
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	integrationCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"notification-service",
		[]string{"integration.external_interaction.submit"},
	)
	if err != nil {
		return fmt.Errorf("integration service credential init failed: %w", err)
	}
	deliveryAdapter, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     integrationBaseURL,
			Credentials: integrationCredentials,
			Environment: getenvOrDefault("APP_ENV", "alpha"),
			Timeout:     time.Duration(integrationTimeoutMs) * time.Millisecond,
		},
		observedClient,
	)
	if err != nil {
		return fmt.Errorf("integration delivery adapter init failed: %w", err)
	}
	userCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"notification-service",
		[]string{"user.push_destination.read"},
	)
	if err != nil {
		return fmt.Errorf("user service credential init failed: %w", err)
	}
	pushDestinations, err := userclient.NewPushDestinationClient(
		userclient.PushDestinationClientConfig{
			BaseURL:     userBaseURL,
			Credentials: userCredentials,
			Timeout:     time.Duration(dependencyTimeoutMs) * time.Millisecond,
		},
		userObservedClient,
	)
	if err != nil {
		return fmt.Errorf("user push destination client init failed: %w", err)
	}
	realtimeCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"notification-service",
		[]string{"realtime.presence.read"},
	)
	if err != nil {
		return fmt.Errorf("realtime service credential init failed: %w", err)
	}
	presenceReader, err := realtimeclient.NewPresenceClient(
		realtimeclient.PresenceClientConfig{
			BaseURL:     realtimeBaseURL,
			Credentials: realtimeCredentials,
			Timeout:     time.Duration(dependencyTimeoutMs) * time.Millisecond,
		},
		realtimeObservedClient,
	)
	if err != nil {
		return fmt.Errorf("realtime presence client init failed: %w", err)
	}

	mongoClient, err := mongodb.Connect(
		ctx,
		mongodb.ConnectConfig{
			URI:      mongoURI,
			Database: mongoDatabase,
		},
	)
	if err != nil {
		return fmt.Errorf("MongoDB connect failed: %w", err)
	}
	defer func() {
		disconnectCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := mongoClient.Disconnect(disconnectCtx); err != nil {
			log.Printf("notification-service MongoDB disconnect failed: %v", err)
		}
	}()
	store := persistence.NewMongoNotificationDeliveryJobStore(mongoClient.Database(mongoDatabase))
	appMessageStore := persistence.NewMongoAppMessageStore(mongoClient.Database(mongoDatabase))
	accountClosureProjection, err := persistence.NewMongoUserAccountClosedProjection(
		mongoClient.Database(mongoDatabase),
	)
	if err != nil {
		return fmt.Errorf("UserAccountClosed projection init failed: %w", err)
	}
	indexCtx, cancelIndexes := context.WithTimeout(ctx, 30*time.Second)
	indexErr := store.EnsureIndexes(indexCtx)
	if indexErr == nil {
		indexErr = appMessageStore.EnsureIndexes(indexCtx)
	}
	if indexErr == nil {
		indexErr = accountClosureProjection.EnsureIndexes(indexCtx)
	}
	cancelIndexes()
	if indexErr != nil {
		return fmt.Errorf("reliable-task EnsureIndexes failed: %w", indexErr)
	}
	_ = prometheus.Register(reliabletask.NewMetricsCollector(store))
	service, err := application.NewNotificationDeliveryService(
		store,
		deliveryAdapter,
		reliabletask.RateLimitPolicy{
			ClaimPerSecond:    claimPerSecond,
			DispatchPerSecond: dispatchPerSecond,
			RetryPerSecond:    retryPerSecond,
		},
	)
	if err != nil {
		return fmt.Errorf("notification delivery service init failed: %w", err)
	}
	appMessageCommands, err := application.NewAppMessageCommandFacade(
		appMessageStore,
		appMessageStore,
		store,
	)
	if err != nil {
		return fmt.Errorf("app message command facade init failed: %w", err)
	}
	redisAddr, err := requiredEnv("NOTIFICATION_REDIS_ADDR", "REDIS_ADDR")
	if err != nil {
		return fmt.Errorf("interaction notification consumer requires Redis: %w", err)
	}
	redisRouter, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     "standalone",
				Addr:     redisAddr,
				Password: os.Getenv("REDIS_PASSWORD"),
			},
			"realtime": {
				Mode:     "standalone",
				Addr:     redisAddr,
				Password: os.Getenv("REDIS_PASSWORD"),
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		return fmt.Errorf("notification redis init failed: %w", err)
	}
	defer redisRouter.Close()
	interactionFailures := persistence.NewMongoInteractionFailureStore(
		mongoClient.Database(mongoDatabase),
	)
	failureIndexCtx, cancelFailureIndexes := context.WithTimeout(ctx, 30*time.Second)
	failureIndexErr := interactionFailures.EnsureIndexes(failureIndexCtx)
	cancelFailureIndexes()
	if failureIndexErr != nil {
		return fmt.Errorf("interaction failure store EnsureIndexes failed: %w", failureIndexErr)
	}
	interactionConsumer, err := streamadapter.NewInteractionNotificationConsumer(
		redisRouter.Scene("general"),
		appMessageCommands,
		interactionFailures,
		getenvOrDefault("NOTIFICATION_CONSUMER_NAME", "notification-interaction-projector"),
		slog.Default(),
	)
	if err != nil {
		return fmt.Errorf("interaction notification consumer init failed: %w", err)
	}
	go interactionConsumer.Run(ctx, 250*time.Millisecond)
	accountClosureConsumer, err := streamadapter.NewUserAccountClosedConsumer(
		redisRouter.Scene("general"),
		accountClosureProjection,
		accountClosureProjection,
		getenvOrDefault(
			"NOTIFICATION_USER_ACCOUNT_CLOSED_CONSUMER_NAME",
			"notification-user-account-closed-projector",
		),
		slog.Default(),
		streamadapter.DefaultUserAccountClosedConsumerConfig(),
	)
	if err != nil {
		return fmt.Errorf("UserAccountClosed consumer init failed: %w", err)
	}
	accountClosureSetupCtx, cancelAccountClosureSetup := context.WithTimeout(
		ctx,
		10*time.Second,
	)
	accountClosureSetupErr := accountClosureConsumer.EnsureGroup(
		accountClosureSetupCtx,
	)
	cancelAccountClosureSetup()
	if accountClosureSetupErr != nil {
		return fmt.Errorf(
			"UserAccountClosed consumer group setup failed: %w",
			accountClosureSetupErr,
		)
	}
	accountClosureConsumerDone := make(chan struct{})
	go func() {
		defer close(accountClosureConsumerDone)
		accountClosureConsumer.Run(ctx)
	}()
	incomingPublisher, err := realtimeclient.NewIncomingCallPublisher(
		redisRouter.Scene("realtime"),
	)
	if err != nil {
		return fmt.Errorf("incoming call realtime publisher init failed: %w", err)
	}
	incomingCoordinator, err := application.NewIncomingCallDeliveryCoordinator(
		store,
		pushDestinations,
		presenceReader,
		incomingPublisher,
		deliveryAdapter,
		application.WithIncomingCallObserver(
			registerIncomingCallMetrics(),
		),
	)
	if err != nil {
		return fmt.Errorf("incoming call coordinator init failed: %w", err)
	}
	rtcConsumer, err := streamadapter.NewRTCIncomingCallConsumer(
		redisRouter.Scene("realtime"),
		incomingCoordinator,
		getenvOrDefault(
			"NOTIFICATION_RTC_CONSUMER_NAME",
			"notification-incoming-call-worker",
		),
		slog.Default(),
	)
	if err != nil {
		return fmt.Errorf("rtc incoming call consumer init failed: %w", err)
	}
	go rtcConsumer.Run(ctx, 100*time.Millisecond)
	appMessageQueries, err := application.NewAppMessageQueryFacade(
		appMessageStore,
		appMessageStore,
		appMessageStore,
	)
	if err != nil {
		return fmt.Errorf("app message query facade init failed: %w", err)
	}
	deliveryQueries, err := application.NewNotificationDeliveryJobQueryFacade(store, store)
	if err != nil {
		return fmt.Errorf("notification delivery query facade init failed: %w", err)
	}
	deliveryCommands, err := application.NewNotificationDeliveryJobCommandFacade(store)
	if err != nil {
		return fmt.Errorf("notification delivery command facade init failed: %w", err)
	}
	handler, err := httpadapter.NewHandler(httpadapter.HandlerDependencies{
		AppMessageCommands: appMessageCommands,
		AppMessageQueries:  appMessageQueries,
		DeliveryCommands:   deliveryCommands,
		DeliveryQueries:    deliveryQueries,
		IncomingCalls:      incomingCoordinator,
	})
	if err != nil {
		return fmt.Errorf("notification http handler init failed: %w", err)
	}
	workerDone := make(chan struct{})
	go func() {
		defer close(workerDone)
		runWorkerLoop(ctx, service)
	}()
	incomingWorkerDone := make(chan struct{})
	go func() {
		defer close(incomingWorkerDone)
		runIncomingCallWorkerLoop(ctx, incomingCoordinator)
	}()

	rootMux := http.NewServeMux()
	rootMux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	rootMux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		readyCtx, cancel := context.WithTimeout(r.Context(), time.Second)
		defer cancel()
		if err := mongoClient.Ping(readyCtx, nil); err != nil {
			writeNotificationReadinessError(w, r, "mongodb unavailable")
			return
		}
		if err := redisRouter.Scene("realtime").Ping(readyCtx); err != nil {
			writeNotificationReadinessError(w, r, "realtime redis unavailable")
			return
		}
		if err := redisRouter.Scene("general").Ping(readyCtx); err != nil {
			writeNotificationReadinessError(w, r, "general redis unavailable")
			return
		}
		if err := interactionConsumer.Healthy(10 * time.Second); err != nil {
			writeNotificationReadinessError(w, r, "interaction consumer unavailable")
			return
		}
		if err := accountClosureConsumer.Healthy(10 * time.Second); err != nil {
			writeNotificationReadinessError(
				w,
				r,
				"account closure consumer unavailable",
			)
			return
		}
		if err := rtcConsumer.Healthy(10 * time.Second); err != nil {
			writeNotificationReadinessError(w, r, "rtc consumer unavailable")
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ready"}`))
	})
	rootMux.Handle("/metrics", rtmetrics.Handler())
	rootMux.Handle(
		"/",
		rtauth.RequireGeneratedOperationAuthorization(
			operationsecurity.ForDomain("notification"),
		)(handler.Routes()),
	)
	withObservability := rthttp.NewHTTPServerMiddleware(
		rootMux,
		rthttp.HTTPServerMiddlewareConfig{
			Service:           "notification-service",
			Origin:            "cloud",
			Direction:         "inbound",
			SourceID:          "notification-service.http",
			Src:               "gateway",
			ServiceName:       "notification-service",
			ServiceInstanceID: "local",
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	addr := getenvOrDefault("NOTIFICATION_SERVICE_ADDR", ":18087")
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:  accessVerifier,
			DeviceTicketVerifier: deviceVerifier,
		})(withObservability),
		BaseContext:       func(_ net.Listener) context.Context { return ctx },
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("notification-service listening on %s", server.Addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		cancelRuntime()
		waitForWorkerShutdown(workerDone)
		waitForWorkerShutdown(incomingWorkerDone)
		waitForWorkerShutdown(accountClosureConsumerDone)
		return err
	}
	cancelRuntime()
	waitForWorkerShutdown(workerDone)
	waitForWorkerShutdown(incomingWorkerDone)
	waitForWorkerShutdown(accountClosureConsumerDone)
	return nil
}

func writeNotificationReadinessError(
	w http.ResponseWriter,
	r *http.Request,
	debugMessage string,
) {
	rterr.WriteHTTPError(
		w,
		rterr.NewUnavailable(
			rterr.ModuleNotification,
			rterr.DefaultUserMessage,
			debugMessage,
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func runWorkerLoop(ctx context.Context, service *application.NotificationDeliveryService) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			for i := 0; i < 100; i++ {
				processed, err := service.ProcessOne(ctx)
				if err != nil {
					log.Printf("notification delivery worker failed: %v", err)
					break
				}
				if !processed {
					break
				}
			}
		}
	}
}

func runIncomingCallWorkerLoop(
	ctx context.Context,
	coordinator *application.IncomingCallDeliveryCoordinator,
) {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			for i := 0; i < 100; i++ {
				processed, err := coordinator.ProcessDue(ctx)
				if err != nil {
					log.Printf(
						"notification incoming call worker failed: %v",
						err,
					)
					break
				}
				if !processed {
					break
				}
			}
		}
	}
}

func waitForWorkerShutdown(done <-chan struct{}) {
	timer := time.NewTimer(5 * time.Second)
	defer timer.Stop()
	select {
	case <-done:
	case <-timer.C:
		log.Printf("notification-service delivery worker shutdown timed out")
	}
}

type incomingCallMetrics struct {
	transitions *prometheus.CounterVec
	acks        *prometheus.CounterVec
}

func registerIncomingCallMetrics() *incomingCallMetrics {
	metrics := &incomingCallMetrics{
		transitions: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "notification_incoming_call_transitions_total",
				Help: "Incoming call delivery job transitions.",
			},
			[]string{"from_status", "to_status", "outcome"},
		),
		acks: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "notification_incoming_call_presentation_ack_total",
				Help: "Incoming call presentation ACK outcomes.",
			},
			[]string{"raced"},
		),
	}
	_ = prometheus.Register(metrics.transitions)
	_ = prometheus.Register(metrics.acks)
	return metrics
}

func (m *incomingCallMetrics) RecordIncomingCallTransition(
	fromStatus string,
	toStatus string,
	outcome string,
) {
	m.transitions.WithLabelValues(fromStatus, toStatus, outcome).Inc()
}

func (m *incomingCallMetrics) RecordIncomingCallAck(raced bool) {
	m.acks.WithLabelValues(strconv.FormatBool(raced)).Inc()
}

func getenvOrDefault(key string, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func requiredEnv(keys ...string) (string, error) {
	for _, key := range keys {
		if value := strings.TrimSpace(os.Getenv(key)); value != "" {
			if strings.HasPrefix(value, "${") && strings.HasSuffix(value, "}") {
				continue
			}
			return value, nil
		}
	}
	return "", fmt.Errorf("one of %s is required", strings.Join(keys, ", "))
}

func requiredPositiveIntEnv(key string) (int, error) {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return 0, fmt.Errorf("%s is required", key)
	}
	return parsePositiveInt(key, raw)
}

func positiveIntEnvOrDefault(key string, fallback int) (int, error) {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback, nil
	}
	return parsePositiveInt(key, raw)
}

func parsePositiveInt(key string, raw string) (int, error) {
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive integer", key)
	}
	return value, nil
}
