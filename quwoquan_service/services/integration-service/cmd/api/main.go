package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/mongodb"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	connectorauthorizationhttp "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/adapters/inbound/http"
	connectorauthorizationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/application"
	connectorgrantreceipt "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/grantreceipt"
	connectorauthorizationpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/persistence"
	connectorauthorizationproof "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/proof"
	connectorauthorizationreference "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/reference"
	connectorconnectionhttp "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/adapters/inbound/http"
	connectorconnectionapp "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/application"
	connectorconnectionpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/infrastructure/persistence"
	connectordefinitionhttp "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/adapters/inbound/http"
	connectordefinitionapp "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/application"
	connectordefinitionpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/infrastructure/persistence"
	connectorinvocationhttp "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/adapters/inbound/http"
	connectorinvocationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/application"
	connectorinvocationpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/infrastructure/persistence"
	externalhttp "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/http"
	streamadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/stream"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	interactionpersistence "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/persistence"
	externalprovider "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/resultrelay"
	attemptadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/adapters/inbound/runtime"
	attemptpersistence "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/infrastructure/persistence"
	deadletteradapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/adapters/inbound/runtime"
	deadletterpersistence "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/infrastructure/persistence"
	locationhttp "quwoquan_service/services/integration-service/internal/external_integration/location/adapters/inbound/http"
	locationapplication "quwoquan_service/services/integration-service/internal/external_integration/location/application"
	locationprovider "quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/provider"
	locationproviderbinding "quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/providerbinding"
)

func main() {
	if err := run(); err != nil {
		log.Fatalf("integration-service: %v", err)
	}
}

func run() error {
	cfg, err := loadRuntimeConfig()
	if err != nil {
		return fmt.Errorf("config load failed: %w", err)
	}
	if err := applyEnvOverrides(&cfg); err != nil {
		return fmt.Errorf("config env override failed: %w", err)
	}
	normalizeDefaults(&cfg)
	if err := validateRuntimeConfig(cfg); err != nil {
		return fmt.Errorf("config validation failed: %w", err)
	}
	controlplane.StartReleaseConfigAttestation(
		"integration-service",
		strings.TrimSpace(cfg.Environment),
		strings.TrimSpace(os.Getenv("CONFIG_ROOT")),
		strings.TrimSpace(os.Getenv("CONFIG_VERSION")),
		strings.TrimSpace(os.Getenv("IMAGE_VERSION")),
	)
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
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"integration-service",
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
	locationBinding, locationBindingErr := locationproviderbinding.ResolveLocationLookup(
		cfg.Environment,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	locationCapabilityBlocked := errors.Is(
		locationBindingErr,
		locationproviderbinding.ErrLocationLookupCapabilityBlocked,
	)
	if locationBindingErr != nil && !locationCapabilityBlocked {
		return fmt.Errorf("location provider binding invalid: %w", locationBindingErr)
	}

	ctx, cancelRuntime := context.WithCancel(context.Background())
	defer cancelRuntime()

	redisRouter, redisSceneModes, err := buildIntegrationRedisRouter(cfg)
	if err != nil {
		return fmt.Errorf("integration message transport config invalid: %w", err)
	}
	defer func() {
		if err := redisRouter.Close(); err != nil {
			log.Printf("integration-service Redis close failed: %v", err)
		}
	}()
	redisProbeCtx, cancelRedisProbe := context.WithTimeout(ctx, 10*time.Second)
	if err := redisRouter.PingAll(redisProbeCtx); err != nil {
		cancelRedisProbe()
		return fmt.Errorf("integration-service Redis unavailable: %w", err)
	}
	cancelRedisProbe()
	messageTransport, err := requireIntegrationMessageTransport(
		ctx,
		cfg.Environment,
		redisRouter,
		redisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("integration message transport preflight failed: %w", err)
	}

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "integration-service", SamplingRatio: 0.1})
	defer otelShutdown()

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
	kvFilter := robs.NewKVMetadataFilter(nil)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, robs.TraceLogLevelInfo, kvFilter)
	if err != nil {
		return fmt.Errorf("process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, kvFilter)
	if err != nil {
		return fmt.Errorf("exception logger init failed: %w", err)
	}

	var locationService *locationapplication.Service
	locationAdapter := "blocked"
	locationTimeout := int64(0)
	if locationCapabilityBlocked {
		locationService, err = locationapplication.NewService(
			locationprovider.NewUnavailableLocationProvider(locationBindingErr.Error()),
		)
	} else {
		factoryCfg := rthttp.DefaultHTTPClientFactoryConfig()
		factoryCfg.Timeout = locationBinding.Timeout
		factoryCfg.MaxRetries = 0
		factoryCfg.RetryBackoff = 0
		factoryCfg.RetryOnCodes = map[int]struct{}{}
		logCfg := rthttp.HTTPClientMiddlewareConfig{
			Service:           "integration-service",
			Origin:            "cloud",
			Direction:         "outbound",
			SourceID:          "integration-service.map-provider",
			Src:               "integration-service",
			ServiceName:       "integration-service",
			ServiceInstanceID: "local",
		}
		mapObservedClient := rthttp.NewObservedHTTPClient(
			nil,
			factoryCfg,
			logCfg,
			ioLogger,
			processLogger,
			exceptionLogger,
		)
		mapCB := rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default())
		cbClient := rtgov.WrapClientWithCB(mapObservedClient, mapCB)
		locationProvider, providerErr := locationprovider.NewLocationProvider(locationBinding, cbClient)
		if providerErr != nil {
			return fmt.Errorf("location provider initialization failed: %w", providerErr)
		}
		locationService, err = locationapplication.NewService(locationProvider)
		locationAdapter = locationBinding.AdapterID
		locationTimeout = locationBinding.Timeout.Milliseconds()
	}
	if err != nil {
		return fmt.Errorf("location application service initialization failed: %w", err)
	}

	mongoClient, err := mongodb.Connect(
		ctx,
		mongodb.ConnectConfig{
			URI:      cfg.MongoDB.URI,
			Database: cfg.MongoDB.Database,
		},
	)
	if err != nil {
		return fmt.Errorf("MongoDB connect failed: %w", err)
	}
	defer func() {
		disconnectCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := mongoClient.Disconnect(disconnectCtx); err != nil {
			log.Printf("integration-service MongoDB disconnect failed: %v", err)
		}
	}()
	connectorDefinitionStore := connectordefinitionpersistence.NewMongoStore(
		mongoClient.Database(cfg.MongoDB.Database),
	)
	connectorDefinitionIndexCtx, cancelConnectorDefinitionIndexes := context.WithTimeout(ctx, 30*time.Second)
	if err := connectorDefinitionStore.EnsureIndexes(connectorDefinitionIndexCtx); err != nil {
		cancelConnectorDefinitionIndexes()
		return fmt.Errorf("connector definition indexes failed: %w", err)
	}
	cancelConnectorDefinitionIndexes()
	connectorDefinitionCommands := connectordefinitionapp.NewCommandFacade(
		connectorDefinitionStore,
		nil,
	)
	connectorDefinitionQueries := connectordefinitionapp.NewQueryFacade(
		connectorDefinitionStore,
	)
	connectorAuthorizationStore := connectorauthorizationpersistence.NewMongoStore(
		mongoClient.Database(cfg.MongoDB.Database),
	)
	connectorAuthorizationIndexCtx, cancelConnectorAuthorizationIndexes := context.WithTimeout(ctx, 30*time.Second)
	if err := connectorAuthorizationStore.EnsureIndexes(connectorAuthorizationIndexCtx); err != nil {
		cancelConnectorAuthorizationIndexes()
		return fmt.Errorf("connector authorization indexes failed: %w", err)
	}
	cancelConnectorAuthorizationIndexes()
	connectorAuthorizationCommands := connectorauthorizationapp.NewCommandFacade(
		connectorAuthorizationStore,
		connectorDefinitionStore,
		connectorauthorizationreference.NewIssuer(nil),
		connectorauthorizationproof.NewUnavailableVerifier(),
		nil,
		nil,
	)
	connectorAuthorizationQueries := connectorauthorizationapp.NewQueryFacade(
		connectorAuthorizationStore,
	)
	connectorConnectionStore := connectorconnectionpersistence.NewMongoStore(
		mongoClient.Database(cfg.MongoDB.Database),
		connectorAuthorizationStore,
	)
	connectorGrantVerifier := connectorgrantreceipt.NewMongoVerifier(
		mongoClient.Database(cfg.MongoDB.Database),
		nil,
	)
	connectorConnectionIndexCtx, cancelConnectorConnectionIndexes := context.WithTimeout(ctx, 30*time.Second)
	if err := connectorConnectionStore.EnsureIndexes(connectorConnectionIndexCtx); err != nil {
		cancelConnectorConnectionIndexes()
		return fmt.Errorf("connector connection indexes failed: %w", err)
	}
	cancelConnectorConnectionIndexes()
	connectorConnectionCommands := connectorconnectionapp.NewCommandFacade(
		connectorConnectionStore,
		connectorDefinitionStore,
		connectorGrantVerifier,
		nil,
	)
	connectorConnectionQueries := connectorconnectionapp.NewCapabilityQueryFacade(
		connectorConnectionStore,
		connectorDefinitionStore,
		nil,
	)
	connectorInvocationStore := connectorinvocationpersistence.NewMongoStore(
		mongoClient.Database(cfg.MongoDB.Database),
	)
	connectorInvocationIndexCtx, cancelConnectorInvocationIndexes := context.WithTimeout(ctx, 30*time.Second)
	if err := connectorInvocationStore.EnsureIndexes(connectorInvocationIndexCtx); err != nil {
		cancelConnectorInvocationIndexes()
		return fmt.Errorf("connector invocation indexes failed: %w", err)
	}
	cancelConnectorInvocationIndexes()
	connectorInvocationCommands := connectorinvocationapp.NewCommandFacade(
		connectorInvocationStore,
		connectorConnectionStore,
		connectorDefinitionStore,
		nil,
		nil,
	)
	connectorInvocationQueries := connectorinvocationapp.NewQueryFacade(
		connectorInvocationStore,
	)
	reliableStore := reliabletaskmongo.NewExternalInteraction(mongoClient.Database(cfg.MongoDB.Database))
	attemptRuntimeStore := attemptadapter.NewRuntimeStore(reliableStore)
	deadLetterRepository := deadletterpersistence.NewMongoRepository(
		mongoClient.Database(cfg.MongoDB.Database),
	)
	externalRuntimeStore := deadletteradapter.NewRuntimeStore(
		attemptRuntimeStore,
		deadLetterRepository,
	)
	otpCodeReferenceStore := externalprovider.NewMongoOTPCodeReferenceStore(mongoClient.Database(cfg.MongoDB.Database))
	indexCtx, cancelIndexes := context.WithTimeout(ctx, 30*time.Second)
	indexErr := reliableStore.EnsureIndexes(indexCtx)
	cancelIndexes()
	if indexErr != nil {
		return fmt.Errorf("reliable-task EnsureIndexes failed: %w", indexErr)
	}
	deadLetterIndexCtx, cancelDeadLetterIndexes := context.WithTimeout(ctx, 30*time.Second)
	indexErr = deadLetterRepository.EnsureIndexes(deadLetterIndexCtx)
	cancelDeadLetterIndexes()
	if indexErr != nil {
		return fmt.Errorf("external interaction dead-letter indexes failed: %w", indexErr)
	}
	attemptClosure, err := attemptpersistence.NewMongoSubjectClosure(
		mongoClient.Database(cfg.MongoDB.Database),
	)
	if err != nil {
		return fmt.Errorf("provider attempt account closure init failed: %w", err)
	}
	closureProjection, err := interactionpersistence.NewMongoUserAccountClosedProjection(
		mongoClient.Database(cfg.MongoDB.Database),
		attemptClosure,
	)
	if err != nil {
		return fmt.Errorf("integration account closure projection init failed: %w", err)
	}
	closureIndexCtx, cancelClosureIndexes := context.WithTimeout(ctx, 30*time.Second)
	if err := attemptClosure.EnsureIndexes(closureIndexCtx); err != nil {
		cancelClosureIndexes()
		return fmt.Errorf("provider attempt account closure indexes failed: %w", err)
	}
	if err := closureProjection.EnsureIndexes(closureIndexCtx); err != nil {
		cancelClosureIndexes()
		return fmt.Errorf("integration account closure indexes failed: %w", err)
	}
	cancelClosureIndexes()
	accountClosureConsumer, err := streamadapter.NewUserAccountClosedConsumer(
		messageTransport,
		closureProjection,
		closureProjection,
		fmt.Sprintf("integration-service-%d", os.Getpid()),
		slog.Default(),
		streamadapter.DefaultUserAccountClosedConsumerConfig(),
	)
	if err != nil {
		return fmt.Errorf("integration account closure consumer init failed: %w", err)
	}
	if _, err := accountClosureConsumer.ProcessOnce(ctx); err != nil {
		return fmt.Errorf("integration account closure consumer preflight failed: %w", err)
	}
	accountClosureDone := make(chan struct{})
	go func() {
		defer close(accountClosureDone)
		accountClosureConsumer.Run(ctx)
	}()
	externalResultRelay, err := resultrelay.New(
		reliableStore,
		messageTransport,
		slog.Default(),
	)
	if err != nil {
		return fmt.Errorf("external interaction result relay init failed: %w", err)
	}
	if _, err := externalResultRelay.ProcessOnce(ctx); err != nil {
		return fmt.Errorf("external interaction result relay preflight failed: %w", err)
	}
	resultRelayDone := make(chan struct{})
	go func() {
		defer close(resultRelayDone)
		externalResultRelay.Run(ctx)
	}()
	if cfg.Integration.ExternalInteraction.SMS.Enabled {
		otpIndexCtx, cancelOTPIndexes := context.WithTimeout(ctx, 30*time.Second)
		otpIndexErr := otpCodeReferenceStore.EnsureIndexes(otpIndexCtx)
		cancelOTPIndexes()
		if otpIndexErr != nil {
			return fmt.Errorf("otp code reference EnsureIndexes failed: %w", otpIndexErr)
		}
	}
	_ = prometheus.Register(reliabletask.NewMetricsCollector(reliableStore))

	externalObservedClient, err := newExternalObservedHTTPClient(
		cfg,
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	if err != nil {
		return fmt.Errorf("external Provider HTTP client invalid: %w", err)
	}
	var otpCodeSealer *otpseal.Sealer
	if cfg.Integration.ExternalInteraction.SMS.Enabled {
		otpCodeSealer, err = otpseal.LoadFromEnvironment()
		if err != nil {
			return fmt.Errorf("otp code reference sealer invalid: %w", err)
		}
	}
	externalProviders, policies, err := buildExternalProviders(
		cfg,
		externalObservedClient,
		accessTokenConfig,
		otpCodeSealer,
		otpCodeReferenceStore,
	)
	if err != nil {
		return err
	}
	var externalService *application.ExternalInteractionService
	externalLoopDone := make(chan struct{})
	if len(policies) > 0 {
		externalService, err = application.NewExternalInteractionService(
			externalRuntimeStore,
			externalProviders,
			policies,
			otpCodeReferenceStore,
		)
		if err != nil {
			return fmt.Errorf("external interaction service init failed: %w", err)
		}
		go func() {
			defer close(externalLoopDone)
			runExternalInteractionLoop(ctx, externalService)
		}()
	} else {
		close(externalLoopDone)
	}
	operationMux := http.NewServeMux()
	connectorauthorizationhttp.NewHandler(
		connectorAuthorizationCommands,
		connectorAuthorizationQueries,
	).RegisterRoutes(operationMux)
	connectordefinitionhttp.NewHandler(
		connectorDefinitionCommands,
		connectorDefinitionQueries,
	).RegisterRoutes(operationMux)
	connectorconnectionhttp.NewHandler(
		connectorConnectionCommands,
		connectorConnectionQueries,
	).RegisterRoutes(operationMux)
	connectorinvocationhttp.NewHandler(
		connectorInvocationCommands,
		connectorInvocationQueries,
	).RegisterRoutes(operationMux)
	locationhttp.NewHandler(
		locationService,
		cfg.Integration.Location.NearbyDefaultRadiusMeters,
		cfg.Integration.Location.NearbyDefaultLimit,
		cfg.Integration.Location.SearchDefaultLimit,
		cfg.Integration.Location.DefaultLatitude,
		cfg.Integration.Location.DefaultLongitude,
	).RegisterRoutes(operationMux)
	externalhttp.NewHandler(externalService).RegisterRoutes(operationMux)
	handler := http.Handler(operationMux)

	providerSubstitute, err := startNonprodProviderSubstitute(cfg.Environment)
	if err != nil {
		return fmt.Errorf("nonprod provider substitute init failed: %w", err)
	}
	if providerSubstitute != nil {
		defer func() {
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			if err := providerSubstitute.close(shutdownCtx); err != nil {
				log.Printf("nonprod provider substitute shutdown failed: %v", err)
			}
		}()
	}

	rootMux := http.NewServeMux()
	healthChecker := rthealth.NewChecker()
	healthChecker.Register("account_security_authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	healthChecker.Register("redis", func(hctx context.Context) error {
		return redisRouter.PingAll(hctx)
	})
	healthChecker.Register(
		"user_account_closed_consumer",
		func(context.Context) error {
			return accountClosureConsumer.Healthy(10 * time.Second)
		},
	)
	if providerSubstitute != nil {
		healthChecker.Register(
			"nonprod_provider_substitute",
			providerSubstitute.health,
		)
	}
	healthChecker.Register(
		"external_interaction_result_relay",
		func(hctx context.Context) error {
			return externalResultRelay.Healthy(hctx, 10*time.Second)
		},
	)
	rootMux.HandleFunc("/healthz", healthChecker.Handler())
	rootMux.Handle("/metrics", rtmetrics.Handler())
	rootMux.Handle(
		"/",
		rtauth.EnforceGeneratedOperationAuthorization(
			operationsecurity.ForDomain("integration"),
		)(handler),
	)

	serverCfg := rthttp.HTTPServerMiddlewareConfig{
		Service:           "integration-service",
		Origin:            "cloud",
		Direction:         "inbound",
		SourceID:          "integration-service.http",
		Src:               "gateway",
		ServiceName:       "integration-service",
		ServiceInstanceID: "local",
	}
	withObs := rthttp.NewHTTPServerMiddleware(rootMux, serverCfg, ioLogger, processLogger, exceptionLogger)

	server := &http.Server{
		Addr: cfg.Service.HTTP.Addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(withObs),
		BaseContext:       func(_ net.Listener) context.Context { return ctx },
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf(
		"integration-service listening on %s location_adapter=%s timeout_ms=%d",
		cfg.Service.HTTP.Addr,
		locationAdapter,
		locationTimeout,
	)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		cancelRuntime()
		waitForWorkerShutdown(externalLoopDone, "external interaction")
		waitForWorkerShutdown(resultRelayDone, "external interaction result relay")
		waitForWorkerShutdown(accountClosureDone, "account closure consumer")
		return err
	}
	cancelRuntime()
	waitForWorkerShutdown(externalLoopDone, "external interaction")
	waitForWorkerShutdown(resultRelayDone, "external interaction result relay")
	waitForWorkerShutdown(accountClosureDone, "account closure consumer")
	return nil
}

func runExternalInteractionLoop(ctx context.Context, service *application.ExternalInteractionService) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := service.DispatchDue(ctx, 20); err != nil {
				log.Printf("external interaction dispatch failed: %v", err)
				continue
			}
			for i := 0; i < 20; i++ {
				processed, err := service.ProcessOne(ctx)
				if err != nil {
					log.Printf("external interaction worker failed: %v", err)
					break
				}
				if !processed {
					break
				}
			}
		}
	}
}

func waitForWorkerShutdown(done <-chan struct{}, name string) {
	timer := time.NewTimer(5 * time.Second)
	defer timer.Stop()
	select {
	case <-done:
	case <-timer.C:
		log.Printf("integration-service %s worker shutdown timed out", name)
	}
}
