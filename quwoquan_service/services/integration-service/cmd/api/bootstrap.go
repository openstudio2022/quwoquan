// Package bootstrap owns integration-service's private composition for
// servicehost.
package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/reliabletaskmongo"
	rtgov "quwoquan_service/runtime/governance"
	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/runtime/servicekit"
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
)

const serviceName = "integration-service"

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定键集
// 不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix(serviceName), &config{})
}

// NewModule performs fail-fast service-owned assembly. It does not bind a
// listener, start workers, manage signals or decide process exit status.
func NewModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap(serviceName, servicekit.BootstrapSpec[config]{
		OperationDescriptors: operationsecurity.ForDomain("integration"),
		AuthorityScopes:      []string{"user.account.security.read"},
		// 外部 provider 凭据、OTP 明文与推送令牌都会进入 provider 调用的
		// input/output，KV 元数据一律不落盘。
		ObservabilityKVFilter: robs.NewKVMetadataFilter(nil),
		RetiredEnvKeys:        retiredEnvKeys(),
		SnapshotGuard:         snapshotGuard,
		ValidateConfig:        resolveIntegrationConfig,
		// 只装配 general：rec scene 无消费点，声明它会让本进程连一个没有
		// 读写方的 Redis。
		RedisScenes: func(cfg *config) map[string]servicekit.RedisSceneConfig {
			return map[string]servicekit.RedisSceneConfig{"general": cfg.Redis.General}
		},
		Assemble: assembleIntegrationDomain,
	})
}

func assembleIntegrationDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context

	redisProbeCtx, cancelRedisProbe := context.WithTimeout(ctx, 10*time.Second)
	defer cancelRedisProbe()
	if err := asm.RedisRouter.PingAll(redisProbeCtx); err != nil {
		return fmt.Errorf("integration-service Redis unavailable: %w", err)
	}
	messageTransport, err := requireIntegrationMessageTransport(
		ctx,
		cfg.Environment,
		asm.RedisRouter,
		asm.RedisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("integration message transport preflight failed: %w", err)
	}

	locationService, err := assembleLocationService(asm, cfg)
	if err != nil {
		return err
	}

	database := asm.MongoDB
	connectorDefinitionStore := connectordefinitionpersistence.NewMongoStore(database)
	if err := ensureIndexes(ctx, "connector definition", connectorDefinitionStore.EnsureIndexes); err != nil {
		return err
	}
	connectorDefinitionCommands := connectordefinitionapp.NewCommandFacade(
		connectorDefinitionStore,
		nil,
	)
	connectorDefinitionQueries := connectordefinitionapp.NewQueryFacade(connectorDefinitionStore)

	connectorAuthorizationStore := connectorauthorizationpersistence.NewMongoStore(database)
	if err := ensureIndexes(
		ctx, "connector authorization", connectorAuthorizationStore.EnsureIndexes,
	); err != nil {
		return err
	}
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
		database,
		connectorAuthorizationStore,
	)
	if err := ensureIndexes(
		ctx, "connector connection", connectorConnectionStore.EnsureIndexes,
	); err != nil {
		return err
	}
	connectorGrantVerifier := connectorgrantreceipt.NewMongoVerifier(database, nil)
	connectorConnectionCommands := connectorconnectionapp.NewCommandFacade(
		connectorConnectionStore,
		connectorDefinitionStore,
		connectorGrantVerifier,
		nil,
	)

	grantRedis, ok := asm.RedisRouter.LookupScene("general")
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
	grantSession := grantapp.NewCapabilityGrantSessionFacade(
		grantresolver.NewCandidateResolver(
			unavailableGrantSources,
			grantcandidate.NewConnectorReaderSource(
				connectorConnectionStore,
				connectorDefinitionStore,
				nil,
			),
			unavailableGrantSources,
			unavailableGrantSources,
			func() time.Time { return time.Now().UTC() },
		),
		grantSessionStore,
	)
	connectorConnectionQueries := connectorconnectionapp.NewCapabilityQueryFacade(
		connectorConnectionStore,
		grantadapter.NewMiddleware(grantSession),
	)

	connectorInvocationStore := connectorinvocationpersistence.NewMongoStore(database)
	if err := ensureIndexes(
		ctx, "connector invocation", connectorInvocationStore.EnsureIndexes,
	); err != nil {
		return err
	}
	connectorInvocationCommands := connectorinvocationapp.NewCommandFacade(
		connectorInvocationStore,
		grantSession,
		nil,
		nil,
	)
	connectorInvocationQueries := connectorinvocationapp.NewQueryFacade(connectorInvocationStore)
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
	asm.Workers.Add(func(workerCtx context.Context) {
		runConnectorInvocationLoop(workerCtx, connectorInvocationWorker)
	})

	reliableStore := reliabletaskmongo.NewExternalInteraction(database)
	if err := ensureIndexes(ctx, "reliable-task", reliableStore.EnsureIndexes); err != nil {
		return err
	}
	deadLetterRepository := deadletterpersistence.NewMongoRepository(database)
	if err := ensureIndexes(
		ctx, "external interaction dead-letter", deadLetterRepository.EnsureIndexes,
	); err != nil {
		return err
	}
	externalRuntimeStore := deadletteradapter.NewRuntimeStore(
		attemptadapter.NewRuntimeStore(reliableStore),
		deadLetterRepository,
	)
	otpCodeReferenceStore := externalprovider.NewMongoOTPCodeReferenceStore(database)

	attemptClosure, err := attemptpersistence.NewMongoSubjectClosure(database)
	if err != nil {
		return fmt.Errorf("provider attempt account closure init failed: %w", err)
	}
	closureStore, err := interactionpersistence.NewMongoUserAccountClosedProjection(
		database,
		attemptClosure,
	)
	if err != nil {
		return fmt.Errorf("integration account closure projection init failed: %w", err)
	}
	if err := ensureIndexes(
		ctx, "provider attempt account closure", attemptClosure.EnsureIndexes,
	); err != nil {
		return err
	}
	if err := ensureIndexes(
		ctx, "integration account closure", closureStore.EnsureIndexes,
	); err != nil {
		return err
	}
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
	asm.Workers.Add(accountClosureConsumer.Run)
	asm.Health.Register("user_account_closed_consumer", func(context.Context) error {
		return accountClosureConsumer.Healthy(10 * time.Second)
	})

	externalResultRelay, err := resultrelay.New(reliableStore, messageTransport, slog.Default())
	if err != nil {
		return fmt.Errorf("external interaction result relay init failed: %w", err)
	}
	if _, err := externalResultRelay.ProcessOnce(ctx); err != nil {
		return fmt.Errorf("external interaction result relay preflight failed: %w", err)
	}
	asm.Workers.Add(externalResultRelay.Run)
	asm.Health.Register("external_interaction_result_relay", func(hctx context.Context) error {
		return externalResultRelay.Healthy(hctx, 10*time.Second)
	})

	if cfg.Integration.ExternalInteraction.SMS.Enabled {
		if err := ensureIndexes(
			ctx, "otp code reference", otpCodeReferenceStore.EnsureIndexes,
		); err != nil {
			return err
		}
	}
	_ = prometheus.Register(reliabletask.NewMetricsCollector(reliableStore))

	externalService, smsReadinessProvider, err := assembleExternalInteractionService(
		asm,
		cfg,
		externalRuntimeStore,
		otpCodeReferenceStore,
	)
	if err != nil {
		return err
	}

	connectorauthorizationhttp.NewHandler(
		connectorAuthorizationCommands,
		connectorAuthorizationQueries,
	).RegisterRoutes(asm.Mux)
	connectordefinitionhttp.NewHandler(
		connectorDefinitionCommands,
		connectorDefinitionQueries,
	).RegisterRoutes(asm.Mux)
	connectorconnectionhttp.NewHandler(
		connectorConnectionCommands,
		connectorConnectionQueries,
	).RegisterRoutes(asm.Mux)
	connectorinvocationhttp.NewHandler(
		connectorInvocationCommands,
		connectorInvocationQueries,
	).RegisterRoutes(asm.Mux)
	locationhttp.NewHandler(
		locationService,
		cfg.Integration.Location.NearbyDefaultRadiusMeters,
		cfg.Integration.Location.NearbyDefaultLimit,
		cfg.Integration.Location.SearchDefaultLimit,
		cfg.Integration.Location.DefaultLatitude,
		cfg.Integration.Location.DefaultLongitude,
	).RegisterRoutes(asm.Mux)
	externalhttp.NewHandler(
		externalService,
		application.NewSmsOtpDeliveryReadinessQueryFacade(
			smsReadinessProvider,
			externalResultRelay,
		),
	).RegisterRoutes(asm.Mux)
	return nil
}

func assembleExternalInteractionService(
	asm *servicekit.Assembly,
	cfg *config,
	runtimeStore *deadletteradapter.RuntimeStore,
	otpCodeReferences otpseal.ReferenceStore,
) (*application.ExternalInteractionService, *externalprovider.HTTPExternalProvider, error) {
	externalObservedClient, err := newExternalObservedHTTPClient(
		*cfg,
		asm.Observability.IOLogger,
		asm.Observability.ProcessLogger,
		asm.Observability.ExceptionLogger,
	)
	if err != nil {
		return nil, nil, fmt.Errorf("external Provider HTTP client invalid: %w", err)
	}
	var otpCodeSealer *otpseal.Sealer
	if cfg.Integration.ExternalInteraction.SMS.Enabled {
		otpCodeSealer, err = otpseal.LoadFromEnvironment()
		if err != nil {
			return nil, nil, fmt.Errorf("otp code reference sealer invalid: %w", err)
		}
	}
	providers, policies, smsReadinessProvider, err := buildExternalProviders(
		*cfg,
		externalObservedClient,
		asm.Auth.AccessTokenConfig,
		otpCodeSealer,
		otpCodeReferences,
	)
	if err != nil {
		return nil, nil, err
	}
	if len(policies) == 0 {
		return nil, smsReadinessProvider, nil
	}
	service, err := application.NewExternalInteractionService(
		runtimeStore,
		providers,
		policies,
		otpCodeReferences,
	)
	if err != nil {
		return nil, nil, fmt.Errorf("external interaction service init failed: %w", err)
	}
	asm.Workers.Add(func(workerCtx context.Context) {
		runExternalInteractionLoop(workerCtx, service)
	})
	return service, smsReadinessProvider, nil
}

func assembleLocationService(
	asm *servicekit.Assembly,
	cfg *config,
) (*locationapplication.Service, error) {
	bindings, err := resolveLocationBindings(cfg)
	if err != nil {
		return nil, err
	}
	newClient := func(
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
		observedClient := rthttp.NewObservedHTTPClient(
			nil,
			factoryCfg,
			rthttp.HTTPClientMiddlewareConfig{
				Service:           serviceName,
				Origin:            "cloud",
				Direction:         robs.DirectionOutbound,
				SourceID:          sourceID,
				Src:               serviceName,
				ServiceName:       serviceName,
				ServiceInstanceID: asm.Identity.InstanceID,
			},
			asm.Observability.IOLogger,
			asm.Observability.ProcessLogger,
			asm.Observability.ExceptionLogger,
		)
		return rtgov.WrapClientWithCB(
			observedClient,
			rtgov.NewCircuitBreaker(failureThreshold, resetTimeout, slog.Default()),
		)
	}

	var nearbyProvider locationports.NearbyLocationProvider
	if bindings.lookupBlocked {
		nearbyProvider = locationprovider.NewUnavailableLocationProvider(
			bindings.lookupErr.Error(),
		)
	} else {
		provider, err := locationprovider.NewLocationProvider(
			bindings.lookup,
			newClient(bindings.lookup.Timeout, "integration-service.map-provider", 1, 0, 5, 15*time.Second),
		)
		if err != nil {
			return nil, fmt.Errorf("location provider initialization failed: %w", err)
		}
		nearbyProvider = provider
	}

	poiPolicy := cfg.Integration.PublicProvider.POI
	var searchProvider locationports.POISearchProvider
	if bindings.poiUnavailable {
		searchProvider = locationprovider.NewUnavailableLocationProvider(bindings.poiErr.Error())
	} else {
		searchProvider, err = locationprovider.NewPOISearchProvider(
			bindings.poi,
			newClient(
				bindings.poi.Timeout,
				"integration-service.poi-provider",
				poiPolicy.RetryMaxAttempts,
				time.Duration(poiPolicy.RetryBackoffMs)*time.Millisecond,
				poiPolicy.CircuitFailureThreshold,
				time.Duration(poiPolicy.CircuitResetTimeoutMs)*time.Millisecond,
			),
		)
		if err != nil {
			return nil, fmt.Errorf("POI provider initialization failed: %w", err)
		}
	}

	routePolicy := cfg.Integration.PublicProvider.Route
	var routeProvider locationports.RouteReadProvider
	if bindings.routeUnavailable {
		routeProvider = locationprovider.NewUnavailableLocationProvider(bindings.routeErr.Error())
	} else {
		routeProvider, err = locationprovider.NewRouteReadProvider(
			bindings.route,
			newClient(
				bindings.route.Timeout,
				"integration-service.route-provider",
				routePolicy.RetryMaxAttempts,
				time.Duration(routePolicy.RetryBackoffMs)*time.Millisecond,
				routePolicy.CircuitFailureThreshold,
				time.Duration(routePolicy.CircuitResetTimeoutMs)*time.Millisecond,
			),
		)
		if err != nil {
			return nil, fmt.Errorf("route provider initialization failed: %w", err)
		}
	}

	service, err := locationapplication.NewServiceWithProviders(
		nearbyProvider,
		searchProvider,
		routeProvider,
	)
	if err != nil {
		return nil, fmt.Errorf("location application service initialization failed: %w", err)
	}
	return service, nil
}

func ensureIndexes(
	ctx context.Context,
	label string,
	ensure func(context.Context) error,
) error {
	indexCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	if err := ensure(indexCtx); err != nil {
		return fmt.Errorf("%s indexes failed: %w", label, err)
	}
	return nil
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
