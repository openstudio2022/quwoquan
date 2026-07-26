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
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	httpadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/http"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/providerbinding"
	locationapplication "quwoquan_service/services/integration-service/internal/external_integration/location/application"
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
	locationBinding, locationBindingErr := providerbinding.ResolveLocationLookup(
		cfg.Environment,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	locationCapabilityBlocked := errors.Is(
		locationBindingErr,
		providerbinding.ErrLocationLookupCapabilityBlocked,
	)
	if locationBindingErr != nil && !locationCapabilityBlocked {
		return fmt.Errorf("location provider binding invalid: %w", locationBindingErr)
	}

	ctx, cancelRuntime := context.WithCancel(context.Background())
	defer cancelRuntime()

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
			provider.NewUnavailableLocationProvider(locationBindingErr.Error()),
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
		locationProvider, providerErr := provider.NewLocationProvider(locationBinding, cbClient)
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
	reliableStore := reliabletaskmongo.New(mongoClient.Database(cfg.MongoDB.Database))
	otpCodeReferenceStore := provider.NewMongoOTPCodeReferenceStore(mongoClient.Database(cfg.MongoDB.Database))
	indexCtx, cancelIndexes := context.WithTimeout(ctx, 30*time.Second)
	indexErr := reliableStore.EnsureIndexes(indexCtx)
	cancelIndexes()
	if indexErr != nil {
		return fmt.Errorf("reliable-task EnsureIndexes failed: %w", indexErr)
	}
	if cfg.Integration.ExternalInteraction.SMS.Enabled {
		otpIndexCtx, cancelOTPIndexes := context.WithTimeout(ctx, 30*time.Second)
		otpIndexErr := otpCodeReferenceStore.EnsureIndexes(otpIndexCtx)
		cancelOTPIndexes()
		if otpIndexErr != nil {
			return fmt.Errorf("otp code reference EnsureIndexes failed: %w", otpIndexErr)
		}
	}
	_ = prometheus.Register(reliabletask.NewMetricsCollector(reliableStore))

	externalObservedClient := newExternalObservedHTTPClient(
		cfg,
		ioLogger,
		processLogger,
		exceptionLogger,
	)
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
		callbackSender, err := provider.NewHTTPCallbackSender(
			externalObservedClient,
			cfg.Integration.ExternalInteraction.CallbackSecret,
		)
		if err != nil {
			return fmt.Errorf("external callback sender init failed: %w", err)
		}
		externalService, err = application.NewExternalInteractionService(
			reliableStore,
			externalProviders,
			policies,
			callbackSender,
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
	handler := httpadapter.NewHandler(
		locationService,
		cfg.Integration.Location.NearbyDefaultRadiusMeters,
		cfg.Integration.Location.NearbyDefaultLimit,
		cfg.Integration.Location.SearchDefaultLimit,
		cfg.Integration.Location.DefaultLatitude,
		cfg.Integration.Location.DefaultLongitude,
		externalService,
	).Routes()

	rootMux := http.NewServeMux()
	healthChecker := rthealth.NewChecker()
	healthChecker.Register("account_security_authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
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

	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(withObs)

	server := &http.Server{
		Addr: cfg.Service.HTTP.Addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(rateLimited),
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
		return err
	}
	cancelRuntime()
	waitForWorkerShutdown(externalLoopDone, "external interaction")
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
