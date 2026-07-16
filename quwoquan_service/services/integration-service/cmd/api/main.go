package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net"
	"net/http"
	"os"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/mongodb"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rtgov "quwoquan_service/runtime/governance"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	httpadapter "quwoquan_service/services/integration-service/internal/adapters/http"
	"quwoquan_service/services/integration-service/internal/application"
	"quwoquan_service/services/integration-service/internal/domain/location/model"
	"quwoquan_service/services/integration-service/internal/infrastructure/provider"
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

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "integration-service", SamplingRatio: 0.1})
	defer otelShutdown()

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	kvFilter := robs.NewKVMetadataFilter(nil)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, robs.TraceLogLevelInfo, kvFilter)
	if err != nil {
		return fmt.Errorf("process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, kvFilter)
	if err != nil {
		return fmt.Errorf("exception logger init failed: %w", err)
	}

	factoryCfg := rthttp.DefaultHTTPClientFactoryConfig()
	factoryCfg.Timeout = time.Duration(cfg.Integration.Location.TimeoutMs) * time.Millisecond
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
	clients := map[model.Provider]model.ProviderClient{
		model.ProviderBaidu: provider.NewBaiduClient(cfg.Integration.Location.BaiduBaseURL, cfg.Integration.Location.BaiduAK, cbClient),
		model.ProviderAMap:  provider.NewAMapClient(cfg.Integration.Location.AMapBaseURL, cfg.Integration.Location.AMapKey, cbClient),
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
	catalogClient := provider.NewMongoCatalogClient(
		mongoClient.Database(cfg.MongoDB.Database),
	)
	catalogIndexCtx, cancelCatalogIndexes := context.WithTimeout(ctx, 30*time.Second)
	catalogIndexErr := catalogClient.EnsureIndexes(catalogIndexCtx)
	cancelCatalogIndexes()
	if catalogIndexErr != nil {
		return fmt.Errorf("location catalog EnsureIndexes failed: %w", catalogIndexErr)
	}
	clients[model.ProviderCatalog] = catalogClient
	locationService := application.NewService(
		cfg.Integration.Location.PrimaryProvider,
		cfg.Integration.Location.BackupProvider,
		clients,
		log.Default(),
	)

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
	rootMux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
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
			AccessTokenVerifier:  accessVerifier,
			DeviceTicketVerifier: deviceVerifier,
		})(rateLimited),
		BaseContext:       func(_ net.Listener) context.Context { return ctx },
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf(
		"integration-service listening on %s primary=%s backup=%s timeout_ms=%d",
		cfg.Service.HTTP.Addr,
		cfg.Integration.Location.PrimaryProvider,
		cfg.Integration.Location.BackupProvider,
		cfg.Integration.Location.TimeoutMs,
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

func newExternalObservedHTTPClient(
	cfg config,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) *http.Client {
	timeout := 2 * time.Second
	for _, providerCfg := range []externalProviderConfig{
		cfg.Integration.ExternalInteraction.SMS,
		cfg.Integration.ExternalInteraction.Push,
	} {
		if providerCfg.Enabled && time.Duration(providerCfg.TimeoutMs)*time.Millisecond > timeout {
			timeout = time.Duration(providerCfg.TimeoutMs) * time.Millisecond
		}
	}
	factoryCfg := rthttp.DefaultHTTPClientFactoryConfig()
	factoryCfg.Timeout = timeout
	factoryCfg.MaxRetries = -1
	factoryCfg.RetryBackoff = -1
	factoryCfg.RetryOnCodes = map[int]struct{}{}
	logCfg := rthttp.HTTPClientMiddlewareConfig{
		Service:           "integration-service",
		Origin:            "cloud",
		Direction:         "outbound",
		SourceID:          "integration-service.external-provider",
		Src:               "integration-service",
		ServiceName:       "integration-service",
		ServiceInstanceID: "local",
	}
	return rthttp.NewObservedHTTPClient(
		nil,
		factoryCfg,
		logCfg,
		ioLogger,
		processLogger,
		exceptionLogger,
	)
}

func buildExternalProviders(
	cfg config,
	client *http.Client,
	otpCodeSealer *otpseal.Sealer,
	otpCodeReferences otpseal.ReferenceStore,
) (
	map[string]reliabletask.ExternalProvider,
	map[string]reliabletask.ProviderPolicy,
	error,
) {
	providers := map[string]reliabletask.ExternalProvider{}
	policies := map[string]reliabletask.ProviderPolicy{}
	for _, item := range []struct {
		operation string
		config    externalProviderConfig
	}{
		{
			operation: reliabletask.ExternalInteractionOperationSmsOTP,
			config:    cfg.Integration.ExternalInteraction.SMS,
		},
		{
			operation: reliabletask.ExternalInteractionOperationPush,
			config:    cfg.Integration.ExternalInteraction.Push,
		},
	} {
		if !item.config.Enabled {
			continue
		}
		timeout := time.Duration(item.config.TimeoutMs) * time.Millisecond
		externalProvider, err := provider.NewHTTPExternalProvider(
			provider.HTTPExternalProviderConfig{
				Name:              item.config.Provider,
				Operation:         item.operation,
				Endpoint:          item.config.Endpoint,
				BearerToken:       item.config.Token,
				Timeout:           timeout,
				OTPCodeSealer:     otpCodeSealer,
				OTPCodeReferences: otpCodeReferences,
			},
			client,
		)
		if err != nil {
			return nil, nil, fmt.Errorf(
				"external provider init failed for %s: %w",
				item.operation,
				err,
			)
		}
		providers[item.config.Provider] = externalProvider
		policies[item.operation] = reliabletask.ProviderPolicy{
			Providers:   []string{item.config.Provider},
			Timeout:     timeout,
			RetryPolicy: reliabletask.DefaultRetryPolicy(),
		}
	}
	return providers, policies, nil
}
