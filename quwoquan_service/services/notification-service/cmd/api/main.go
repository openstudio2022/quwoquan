package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/mongodb"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	"quwoquan_service/runtime/reliabletask"
	httpadapter "quwoquan_service/services/notification-service/internal/adapters/http"
	"quwoquan_service/services/notification-service/internal/application"
	integrationclient "quwoquan_service/services/notification-service/internal/infrastructure/integration"
	"quwoquan_service/services/notification-service/internal/infrastructure/persistence"
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

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	kvFilter := robs.NewKVMetadataFilter(nil)
	processLogger, err := robs.NewProcessTraceLogger(
		os.Stdout,
		os.Stderr,
		robs.TraceLogLevelInfo,
		kvFilter,
	)
	if err != nil {
		return fmt.Errorf("process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, kvFilter)
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
	indexCtx, cancelIndexes := context.WithTimeout(ctx, 30*time.Second)
	indexErr := store.EnsureIndexes(indexCtx)
	if indexErr == nil {
		indexErr = appMessageStore.EnsureIndexes(indexCtx)
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
	})
	if err != nil {
		return fmt.Errorf("notification http handler init failed: %w", err)
	}
	workerDone := make(chan struct{})
	go func() {
		defer close(workerDone)
		runWorkerLoop(ctx, service)
	}()

	rootMux := http.NewServeMux()
	rootMux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
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
		return err
	}
	cancelRuntime()
	waitForWorkerShutdown(workerDone)
	return nil
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

func waitForWorkerShutdown(done <-chan struct{}) {
	timer := time.NewTimer(5 * time.Second)
	defer timer.Stop()
	select {
	case <-done:
	case <-timer.C:
		log.Printf("notification-service delivery worker shutdown timed out")
	}
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
