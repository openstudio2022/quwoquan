// Package bootstrap owns integration-service's private composition for
// servicehost.
package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log"
	"log/slog"
	"net"
	"net/http"
	"os"
	rterr "quwoquan_service/runtime/errors"
	"strings"
	"sync"
	"sync/atomic"
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
	"quwoquan_service/runtime/servicehost"
	grantadapter "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/adapters/inbound/runtime"
	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantcandidate "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/candidate"
	grantpersistence "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/persistence"
	grantresolver "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/resolver"
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
	connectorinvocationauthority "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/infrastructure/authority"
	connectorinvocationexecutor "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/infrastructure/executor"
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
	locationports "quwoquan_service/services/integration-service/internal/external_integration/location/domain/ports"
	locationprovider "quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/provider"
	locationproviderbinding "quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/providerbinding"
)

const serviceName = "integration-service"

// Module keeps integration-service's public HTTP contract, workers and private
// resources together while servicehost owns process lifecycle coordination.
type Module struct {
	configDigest string
	server       *http.Server
	readiness    *rthealth.Checker
	listener     net.Listener
	admission    atomic.Bool
	serveError   chan error

	workerCancel context.CancelFunc
	workerGroup  sync.WaitGroup
	workerStarts []func(context.Context)
	cleanup      func()
	runContext   context.Context

	locationAdapter string
	locationTimeout int64
}

var _ servicehost.Module = (*Module)(nil)

// NewModule performs fail-fast service-owned assembly. It does not bind a
// listener, start workers, manage signals or decide process exit status.
func NewModule() (*Module, error) {
	module := &Module{cleanup: func() {}}
	if err := module.build(); err != nil {
		module.cleanup()
		return nil, err
	}
	return module, nil
}

func (module *Module) build() error {
	cfg, err := loadRuntimeConfig()
	if err != nil {
		return fmt.Errorf("config load failed: %w", err)
	}
	if err := applyEnvOverrides(&cfg); err != nil {
		return fmt.Errorf("config env override failed: %w", err)
	}
	normalizeDefaults(&cfg)
	cfg, err = materializeReleaseExternalInteractionBindings(
		cfg,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return fmt.Errorf("external provider binding invalid: %w", err)
	}
	if err := validateRuntimeConfig(cfg); err != nil {
		return fmt.Errorf("config validation failed: %w", err)
	}
	controlplane.StartReleaseConfigAttestation(
		"integration-service",
		strings.TrimSpace(cfg.Environment),
		strings.TrimSpace(os.Getenv("CONFIG_ROOT")),
		strings.TrimSpace(
			servicehost.ModuleEnvironmentValue(
				"integration-service",
				"CONFIG_VERSION",
			),
		),
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
	runtimeConfigProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	locationBinding, locationBindingErr := locationproviderbinding.ResolveLocationLookup(
		cfg.Environment,
		runtimeConfigProvider,
	)
	locationCapabilityBlocked := errors.Is(
		locationBindingErr,
		locationproviderbinding.ErrLocationLookupCapabilityBlocked,
	)
	if locationBindingErr != nil && !locationCapabilityBlocked {
		return fmt.Errorf("location provider binding invalid: %w", locationBindingErr)
	}
	poiPolicy := cfg.Integration.PublicProvider.POI
	poiBinding, poiBindingErr :=
		locationproviderbinding.ResolvePublicLocationCapability(
			cfg.Environment,
			locationproviderbinding.LocationPOISearchCapabilityID,
			runtimeConfigProvider,
			locationproviderbinding.PublicProviderRuntimePolicy{
				ConfigRef:          "config:integration.public_provider.poi",
				RatePolicyRef:      "config:integration.public_provider.poi",
				ProbePassed:        poiPolicy.ProbePassed,
				RateLimitPerSecond: poiPolicy.RateLimitPerSecond,
			},
		)
	poiCapabilityUnavailable := errors.Is(
		poiBindingErr,
		locationproviderbinding.ErrPublicLocationCapabilityBlocked,
	) || errors.Is(
		poiBindingErr,
		locationproviderbinding.ErrPublicLocationProbeNotPassed,
	)
	if poiBindingErr != nil && !poiCapabilityUnavailable {
		return fmt.Errorf("POI provider binding invalid: %w", poiBindingErr)
	}
	routePolicy := cfg.Integration.PublicProvider.Route
	routeBinding, routeBindingErr :=
		locationproviderbinding.ResolvePublicLocationCapability(
			cfg.Environment,
			locationproviderbinding.LocationRouteReadCapabilityID,
			runtimeConfigProvider,
			locationproviderbinding.PublicProviderRuntimePolicy{
				ConfigRef:          "config:integration.public_provider.route",
				RatePolicyRef:      "config:integration.public_provider.route",
				ProbePassed:        routePolicy.ProbePassed,
				RateLimitPerSecond: routePolicy.RateLimitPerSecond,
			},
		)
	routeCapabilityUnavailable := errors.Is(
		routeBindingErr,
		locationproviderbinding.ErrPublicLocationCapabilityBlocked,
	) || errors.Is(
		routeBindingErr,
		locationproviderbinding.ErrPublicLocationProbeNotPassed,
	)
	if routeBindingErr != nil && !routeCapabilityUnavailable {
		return fmt.Errorf("route provider binding invalid: %w", routeBindingErr)
	}

	ctx := context.Background()

	redisRouter, redisSceneModes, err := buildIntegrationRedisRouter(cfg)
	if err != nil {
		return fmt.Errorf("integration message transport config invalid: %w", err)
	}
	module.addCleanup(func() {
		if err := redisRouter.Close(); err != nil {
			log.Printf("integration-service Redis close failed: %v", err)
		}
	})
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

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: serviceName, SamplingRatio: 0.1})
	module.addCleanup(otelShutdown)

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
	module.addCleanup(runtimeLogExporter.Close)
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	module.addCleanup(func() {
		errorLogWriter.Close()
		standardLogWriter.Close()
	})
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

	newLocationHTTPClient := func(
		timeout time.Duration,
		sourceID string,
		maxAttempts int,
		retryBackoff time.Duration,
		failureThreshold int,
		resetTimeout time.Duration,
	) *http.Client {
		factoryCfg := rthttp.DefaultHTTPClientFactoryConfig()
		factoryCfg.Timeout = timeout
		if maxAttempts > 1 {
			factoryCfg.MaxRetries = maxAttempts - 1
		}
		factoryCfg.RetryBackoff = retryBackoff
		factoryCfg.RetryOnCodes = map[int]struct{}{
			http.StatusTooManyRequests:    {},
			http.StatusBadGateway:         {},
			http.StatusServiceUnavailable: {},
			http.StatusGatewayTimeout:     {},
		}
		logCfg := rthttp.HTTPClientMiddlewareConfig{
			Service:           "integration-service",
			Origin:            "cloud",
			Direction:         "outbound",
			SourceID:          sourceID,
			Src:               "integration-service",
			ServiceName:       "integration-service",
			ServiceInstanceID: "local",
		}
		observedClient := rthttp.NewObservedHTTPClient(
			nil,
			factoryCfg,
			logCfg,
			ioLogger,
			processLogger,
			exceptionLogger,
		)
		cb := rtgov.NewCircuitBreaker(
			failureThreshold,
			resetTimeout,
			slog.Default(),
		)
		return rtgov.WrapClientWithCB(observedClient, cb)
	}

	var nearbyProvider locationports.NearbyLocationProvider
	locationAdapter := "blocked"
	locationTimeout := int64(0)
	if locationCapabilityBlocked {
		nearbyProvider = locationprovider.NewUnavailableLocationProvider(
			locationBindingErr.Error(),
		)
	} else {
		nearbyClient := newLocationHTTPClient(
			locationBinding.Timeout,
			"integration-service.map-provider",
			1,
			0,
			5,
			15*time.Second,
		)
		locationProvider, providerErr := locationprovider.NewLocationProvider(
			locationBinding,
			nearbyClient,
		)
		if providerErr != nil {
			return fmt.Errorf("location provider initialization failed: %w", providerErr)
		}
		nearbyProvider = locationProvider
		locationAdapter = locationBinding.AdapterID
		locationTimeout = locationBinding.Timeout.Milliseconds()
	}
	var searchProvider locationports.POISearchProvider
	if poiCapabilityUnavailable {
		searchProvider = locationprovider.NewUnavailableLocationProvider(
			poiBindingErr.Error(),
		)
	} else {
		poiClient := newLocationHTTPClient(
			poiBinding.Timeout,
			"integration-service.poi-provider",
			poiPolicy.RetryMaxAttempts,
			time.Duration(poiPolicy.RetryBackoffMs)*time.Millisecond,
			poiPolicy.CircuitFailureThreshold,
			time.Duration(poiPolicy.CircuitResetTimeoutMs)*time.Millisecond,
		)
		searchProvider, err = locationprovider.NewPOISearchProvider(
			poiBinding,
			poiClient,
		)
		if err != nil {
			return fmt.Errorf("POI provider initialization failed: %w", err)
		}
	}
	var routeProvider locationports.RouteReadProvider
	if routeCapabilityUnavailable {
		routeProvider = locationprovider.NewUnavailableLocationProvider(
			routeBindingErr.Error(),
		)
	} else {
		routeClient := newLocationHTTPClient(
			routeBinding.Timeout,
			"integration-service.route-provider",
			routePolicy.RetryMaxAttempts,
			time.Duration(routePolicy.RetryBackoffMs)*time.Millisecond,
			routePolicy.CircuitFailureThreshold,
			time.Duration(routePolicy.CircuitResetTimeoutMs)*time.Millisecond,
		)
		routeProvider, err = locationprovider.NewRouteReadProvider(
			routeBinding,
			routeClient,
		)
		if err != nil {
			return fmt.Errorf("route provider initialization failed: %w", err)
		}
	}
	locationService, err := locationapplication.NewServiceWithProviders(
		nearbyProvider,
		searchProvider,
		routeProvider,
	)
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
	module.addCleanup(func() {
		disconnectCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := mongoClient.Disconnect(disconnectCtx); err != nil {
			log.Printf("integration-service MongoDB disconnect failed: %v", err)
		}
	})
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
	grantRedis, ok := redisRouter.LookupScene("general")
	if !ok {
		return errors.New("capability grant session requires Redis scene general")
	}
	grantSessionStore, err := grantpersistence.NewRedisSessionStore(grantRedis)
	if err != nil {
		return fmt.Errorf("capability grant session store init failed: %w", err)
	}
	unavailableGrantSources := grantcandidate.NewUnavailableSources(
		"public provider, device, and domain-operation owners are not bound to this HTTP process",
	)
	grantCandidateResolver := grantresolver.NewCandidateResolver(
		unavailableGrantSources,
		grantcandidate.NewConnectorReaderSource(
			connectorConnectionStore,
			connectorDefinitionStore,
			nil,
		),
		unavailableGrantSources,
		unavailableGrantSources,
		func() time.Time { return time.Now().UTC() },
	)
	grantSession := grantapp.NewCapabilityGrantSessionFacade(
		grantCandidateResolver,
		grantSessionStore,
	)
	connectorConnectionQueries := connectorconnectionapp.NewCapabilityQueryFacade(
		connectorConnectionStore,
		grantadapter.NewMiddleware(grantSession),
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
		grantSession,
		nil,
		nil,
	)
	connectorInvocationQueries := connectorinvocationapp.NewQueryFacade(
		connectorInvocationStore,
	)
	connectorInvocationWorker := connectorinvocationapp.NewInvocationWorker(
		connectorInvocationStore,
		grantSession,
		connectorConnectionStore,
		connectorDefinitionStore,
		connectorinvocationauthority.UnavailableExecutionAuthority{},
		connectorinvocationexecutor.UnavailableCapabilityExecutor{},
		"integration-service-connector-invocation",
		30*time.Second,
		nil,
	)
	module.workerStarts = append(
		module.workerStarts,
		func(workerCtx context.Context) {
			runConnectorInvocationLoop(workerCtx, connectorInvocationWorker)
		},
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
	closureStore, err := interactionpersistence.NewMongoUserAccountClosedProjection(
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
	if err := closureStore.EnsureIndexes(closureIndexCtx); err != nil {
		cancelClosureIndexes()
		return fmt.Errorf("integration account closure indexes failed: %w", err)
	}
	cancelClosureIndexes()
	closureProjection, err := application.NewUserAccountClosedProjection(closureStore)
	if err != nil {
		return fmt.Errorf("integration account closure application facet init failed: %w", err)
	}
	accountClosureConsumer, err := streamadapter.NewUserAccountClosedConsumer(
		messageTransport,
		closureProjection,
		closureStore,
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
	module.workerStarts = append(module.workerStarts, accountClosureConsumer.Run)
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
	module.workerStarts = append(module.workerStarts, externalResultRelay.Run)
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
		module.workerStarts = append(
			module.workerStarts,
			func(workerCtx context.Context) {
				runExternalInteractionLoop(workerCtx, externalService)
			},
		)
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
	healthChecker.Register(
		"external_interaction_result_relay",
		func(hctx context.Context) error {
			return externalResultRelay.Healthy(hctx, 10*time.Second)
		},
	)
	rootMux.HandleFunc("/healthz", healthChecker.Handler())
	rootMux.HandleFunc("/readyz", healthChecker.Handler())
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

	timeouts := rtauth.ContractHTTPServerTimeouts(
		operationsecurity.ForDomain("integration"),
	)
	server := &http.Server{
		Addr: cfg.Service.HTTP.Addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(withObs),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	module.configDigest = strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("integration-service", "CONFIG_VERSION"),
	)
	if module.configDigest == "" {
		module.configDigest = fmt.Sprintf("%s:%s", cfg.Environment, cfg.Service.Name)
	}
	module.server = server
	module.readiness = healthChecker
	module.serveError = make(chan error, 1)
	module.locationAdapter = locationAdapter
	module.locationTimeout = locationTimeout
	server.Handler = module.admissionHandler(server.Handler)
	server.BaseContext = func(net.Listener) context.Context {
		if module.runContext != nil {
			return module.runContext
		}
		return context.Background()
	}
	return nil
}

func (module *Module) Name() string { return serviceName }

func (module *Module) ConfigDigest() string {
	if module == nil {
		return ""
	}
	return module.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.server == nil || module.readiness == nil || module.cleanup == nil {
		return errors.New("integration-service module is incomplete")
	}
	return nil
}

func (module *Module) PrepareMigration(context.Context) error {
	return nil
}

func (module *Module) Bind(context.Context) error {
	if module == nil || module.server == nil {
		return errors.New("integration-service HTTP server is unavailable")
	}
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("integration-service listener bind: %w", err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(ctx context.Context) error {
	if module == nil || module.listener == nil {
		return errors.New("integration-service listener is not bound")
	}
	module.runContext, module.workerCancel = context.WithCancel(ctx)
	for _, start := range module.workerStarts {
		module.workerGroup.Add(1)
		module.startWorker(start)
	}
	module.workerGroup.Add(1)
	go func() {
		defer module.workerGroup.Done()
		log.Printf(
			"integration-service listening on %s location_adapter=%s timeout_ms=%d",
			module.server.Addr,
			module.locationAdapter,
			module.locationTimeout,
		)
		if err := module.server.Serve(module.listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			select {
			case module.serveError <- err:
			case <-module.runContext.Done():
			}
		}
	}()
	return nil
}

func (module *Module) Ready(ctx context.Context) error {
	if result := module.readiness.Check(ctx); result.Status != "ok" {
		return fmt.Errorf("integration-service readiness failed: %v", result.FailedChecks)
	}
	select {
	case err := <-module.serveError:
		return fmt.Errorf("integration-service listener failed: %w", err)
	default:
		return nil
	}
}

func (module *Module) OpenAdmission(context.Context) error {
	module.admission.Store(true)
	return nil
}

func (module *Module) Shutdown(ctx context.Context) error {
	module.admission.Store(false)
	var result error
	if module.server != nil {
		if err := module.server.Shutdown(ctx); err != nil {
			result = errors.Join(result, err)
			result = errors.Join(result, module.server.Close())
		}
	}
	if module.workerCancel != nil {
		module.workerCancel()
		module.workerGroup.Wait()
		module.workerCancel = nil
	}
	if module.cleanup != nil {
		module.cleanup()
		module.cleanup = nil
	}
	return result
}

func (module *Module) startWorker(start func(context.Context)) {
	go func() {
		defer module.workerGroup.Done()
		start(module.runContext)
	}()
}

func (module *Module) admissionHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/healthz", "/readyz", "/metrics":
			next.ServeHTTP(writer, request)
			return
		}
		if !module.admission.Load() {
			rterr.WriteHTTPError(
				writer,
				rterr.NewAppError(
					rterr.NewCode(rterr.ModuleGateway, rterr.KindMiddleware, "upstream_unavailable"),
					"服务暂不可用，请稍后重试",
					"service admission is not ready",
				).WithMetadata("upstream_unavailable", http.StatusServiceUnavailable).
					WithRecoveryDirective("retry", "snackbar", 1),
				rterr.HTTPWriteOptionsFromRequest(request),
			)
			return
		}
		next.ServeHTTP(writer, request)
	})
}

func (module *Module) addCleanup(cleanup func()) {
	previousCleanup := module.cleanup
	module.cleanup = func() {
		cleanup()
		previousCleanup()
	}
}

func runConnectorInvocationLoop(
	ctx context.Context,
	worker *connectorinvocationapp.InvocationWorker,
) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			processed, err := worker.RunOnce(ctx)
			if err != nil {
				log.Printf("connector invocation worker failed: %v", err)
				continue
			}
			if !processed {
				continue
			}
		}
	}
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
