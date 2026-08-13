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
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/runtime/servicehost"
	httpadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/http"
	streamadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	accountsecurity "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/accountsecurity"
	integrationclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/integration"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/persistence"
	realtimeclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/realtime"
	userclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/user"
	deliveryhttp "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/adapters/inbound/http"
	deliverystream "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/adapters/inbound/stream"
	deliveryapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	deliverymessaging "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/infrastructure/messaging"
	deliverypersistence "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/infrastructure/persistence"
)

// Module is notification-service's service-owned servicehost adapter.
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
}

var _ servicehost.Module = (*Module)(nil)

// NewModule assembles notification-service's private dependencies and public
// HTTP contract. The process host owns listener admission and runtime lifetime.
func NewModule() (*Module, error) {
	module := &Module{cleanup: func() {}}
	if err := module.build(); err != nil {
		module.cleanup()
		return nil, err
	}
	return module, nil
}

func (module *Module) build() error {
	serviceName := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("notification-service", "SERVICE_NAME"),
	)
	if serviceName == "" {
		serviceName = "notification-service"
	}
	appEnv := getenvOrDefault("APP_ENV", "alpha")
	runtimeConfig, err := loadNotificationRuntimeConfig(
		serviceName,
		appEnv,
		strings.TrimSpace(os.Getenv("CONFIG_ROOT")),
	)
	if err != nil {
		return fmt.Errorf("runtime config invalid: %w", err)
	}
	if err := applyNotificationRuntimeConfig(runtimeConfig); err != nil {
		return fmt.Errorf("runtime config environment adapter failed: %w", err)
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName,
		appEnv,
		strings.TrimSpace(os.Getenv("CONFIG_ROOT")),
		strings.TrimSpace(
			servicehost.ModuleEnvironmentValue(
				"notification-service",
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
	accountSecurityAuthority, err := accountsecurity.NewAuthority(
		accessTokenConfig,
		accountsecurity.Config{
			BaseURL:   runtimeConfig.AccountSecurityAuthority.BaseURL,
			TimeoutMS: runtimeConfig.AccountSecurityAuthority.TimeoutMS,
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

	ctx, cancelRuntime := context.WithCancel(context.Background())
	defer cancelRuntime()
	otelShutdown := rtotel.MustInit(rtotel.Config{
		ServiceName:   "notification-service",
		SamplingRatio: 0.1,
	})
	module.addCleanup(otelShutdown)

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
		return fmt.Errorf("notification-service runtime log exporter init failed: %w", err)
	}
	module.addCleanup(runtimeLogExporter.Close)
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	module.addCleanup(standardLogWriter.Close)
	module.addCleanup(errorLogWriter.Close)
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
	deliveryAdapter, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     integrationBaseURL,
			Credentials: integrationCredentials,
			Environment: getenvOrDefault("APP_ENV", "alpha"),
			Timeout:     time.Duration(integrationTimeoutMs) * time.Millisecond,
		},
		observedClient,
		pushDestinations,
	)
	if err != nil {
		return fmt.Errorf("integration delivery adapter init failed: %w", err)
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
	module.addCleanup(func() {
		disconnectCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := mongoClient.Disconnect(disconnectCtx); err != nil {
			log.Printf("notification-service MongoDB disconnect failed: %v", err)
		}
	})
	notificationDB := mongoClient.Database(mongoDatabase)
	deliveryLifecycle := deliverypersistence.NewMongoAccountLifecycle(notificationDB)
	accountRestrictionStore, err :=
		persistence.NewMongoUserAccountRestrictionProjection(
			notificationDB,
			deliveryLifecycle,
		)
	if err != nil {
		return fmt.Errorf("account restriction projection init failed: %w", err)
	}
	store := deliverypersistence.NewMongoNotificationDeliveryJobStore(
		notificationDB,
		accountRestrictionStore,
	)
	appMessageStore := persistence.NewMongoAppMessageStore(notificationDB)
	accountClosureStore, err := persistence.NewMongoUserAccountClosedProjection(
		notificationDB,
		deliveryLifecycle,
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
		indexErr = deliveryLifecycle.EnsureIndexes(indexCtx)
	}
	if indexErr == nil {
		indexErr = accountClosureStore.EnsureIndexes(indexCtx)
	}
	if indexErr == nil {
		indexErr = accountRestrictionStore.EnsureIndexes(indexCtx)
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
	accountClosureProjection, err := application.NewUserAccountClosedProjection(
		accountClosureStore,
	)
	if err != nil {
		return fmt.Errorf("UserAccountClosed application facet init failed: %w", err)
	}
	accountRestrictionProjection, err := application.NewUserAccountRestrictionProjection(
		accountRestrictionStore,
	)
	if err != nil {
		return fmt.Errorf("account restriction application facet init failed: %w", err)
	}
	redisAddr, err := requiredEnv("NOTIFICATION_REDIS_ADDR", "REDIS_ADDR")
	if err != nil {
		return fmt.Errorf("interaction notification consumer requires Redis: %w", err)
	}
	generalRedisDB, err := requiredNonNegativeIntEnv(
		"NOTIFICATION_REDIS_GENERAL_DB",
	)
	if err != nil {
		return err
	}
	realtimeRedisDB, err := requiredNonNegativeIntEnv(
		"NOTIFICATION_REDIS_REALTIME_DB",
	)
	if err != nil {
		return err
	}
	redisRouter, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     "standalone",
				Addr:     redisAddr,
				Password: os.Getenv("REDIS_PASSWORD"),
				DB:       generalRedisDB,
			},
			"realtime": {
				Mode:     "standalone",
				Addr:     redisAddr,
				Password: os.Getenv("REDIS_PASSWORD"),
				DB:       realtimeRedisDB,
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		return fmt.Errorf("notification redis init failed: %w", err)
	}
	module.addCleanup(func() {
		if err := redisRouter.Close(); err != nil {
			log.Printf("notification-service Redis close failed: %v", err)
		}
	})
	messageTransport, err := requireNotificationAPIMessageTransport(
		ctx,
		getenvOrDefault("APP_ENV", "alpha"),
		redisRouter,
		map[string]string{
			"general":  "standalone",
			"realtime": "standalone",
		},
	)
	if err != nil {
		return fmt.Errorf("notification message transport construction failed: %w", err)
	}
	if err := messageTransport.SetDurableRetention(
		ctx,
		deliverymessaging.NotificationDeliveryJobEventStream,
		deliverymessaging.NotificationDeliveryJobEventStreamRetention,
	); err != nil {
		return fmt.Errorf("NotificationDeliveryJob event stream retention setup failed: %w", err)
	}
	deliveryEventPublisher, err := deliverymessaging.NewEventPublisher(messageTransport)
	if err != nil {
		return fmt.Errorf("NotificationDeliveryJob event publisher init failed: %w", err)
	}
	deliveryOutboxRelay, err := deliveryapplication.NewOutboxRelay(
		store,
		deliveryEventPublisher,
		fmt.Sprintf(
			"notification-delivery-job-relay-%s-%d",
			moduleInstanceID("notification-service", "local"),
			os.Getpid(),
		),
	)
	if err != nil {
		return fmt.Errorf("NotificationDeliveryJob outbox relay init failed: %w", err)
	}
	interactionFailures := persistence.NewMongoInteractionFailureStore(
		mongoClient.Database(mongoDatabase),
	)
	failureIndexCtx, cancelFailureIndexes := context.WithTimeout(ctx, 30*time.Second)
	failureIndexErr := interactionFailures.EnsureIndexes(failureIndexCtx)
	cancelFailureIndexes()
	if failureIndexErr != nil {
		return fmt.Errorf("interaction failure store EnsureIndexes failed: %w", failureIndexErr)
	}
	gatheringInvitations, err := application.NewGatheringInvitationProjection(
		appMessageStore,
	)
	if err != nil {
		return fmt.Errorf("Gathering invitation projection init failed: %w", err)
	}
	interactionConsumer, err := streamadapter.NewInteractionNotificationConsumer(
		messageTransport,
		appMessageCommands,
		interactionFailures,
		getenvOrDefault("NOTIFICATION_CONSUMER_NAME", "notification-interaction-projector"),
		slog.Default(),
		gatheringInvitations,
	)
	if err != nil {
		return fmt.Errorf("interaction notification consumer init failed: %w", err)
	}
	// chat 离线推送投影：presence 在线抑制 + push 投递作业（不落 inbox）。
	// kill-switch：关闭后降级为「仅在线接收」（message-reliability design §6）。
	if getenvOrDefault("NOTIFICATION_CHAT_OFFLINE_PUSH_ENABLED", "true") == "true" {
		chatOfflinePush, chatPushErr := application.NewChatOfflinePushProjectionHandler(
			presenceReader,
			store,
		)
		if chatPushErr != nil {
			return fmt.Errorf("chat offline push projection init failed: %w", chatPushErr)
		}
		interactionConsumer = interactionConsumer.WithChatOfflinePush(chatOfflinePush)
	}
	externalResultRecorder, err := deliveryapplication.NewExternalInteractionResultRecorder(
		store,
	)
	if err != nil {
		return fmt.Errorf("external interaction result recorder init failed: %w", err)
	}
	externalResultConsumer, err := streamadapter.NewExternalInteractionResultConsumer(
		messageTransport,
		externalResultRecorder,
		interactionFailures,
		getenvOrDefault(
			"NOTIFICATION_EXTERNAL_RESULT_CONSUMER_NAME",
			"notification-external-result-projector",
		),
		slog.Default(),
	)
	if err != nil {
		return fmt.Errorf("external interaction result consumer init failed: %w", err)
	}
	externalResultSetupCtx, cancelExternalResultSetup := context.WithTimeout(ctx, 10*time.Second)
	externalResultSetupErr := externalResultConsumer.EnsureGroup(externalResultSetupCtx)
	cancelExternalResultSetup()
	if externalResultSetupErr != nil {
		return fmt.Errorf("external interaction result consumer group setup failed: %w", externalResultSetupErr)
	}
	accountClosureConsumer, err := streamadapter.NewUserAccountClosedConsumer(
		messageTransport,
		accountClosureProjection,
		accountClosureStore,
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
	accountClosureConsumer.WithUserAccountRestrictionProjection(
		accountRestrictionProjection,
	)
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
	incomingPublisher, err := realtimeclient.NewIncomingCallPublisher(
		messageTransport,
	)
	if err != nil {
		return fmt.Errorf("incoming call realtime publisher init failed: %w", err)
	}
	incomingCoordinator, err := deliveryapplication.NewIncomingCallDeliveryCoordinator(
		store,
		pushDestinations,
		presenceReader,
		incomingPublisher,
		deliveryAdapter,
		deliveryapplication.WithIncomingCallObserver(
			registerIncomingCallMetrics(),
		),
	)
	if err != nil {
		return fmt.Errorf("incoming call coordinator init failed: %w", err)
	}
	rtcConsumer, err := deliverystream.NewRTCIncomingCallConsumer(
		messageTransport,
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
	appMessageQueries, err := application.NewAppMessageQueryFacade(
		appMessageStore,
		appMessageStore,
		appMessageStore,
	)
	if err != nil {
		return fmt.Errorf("app message query facade init failed: %w", err)
	}
	deliveryQueries, err := deliveryapplication.NewNotificationDeliveryJobQueryFacade(store, store, store)
	if err != nil {
		return fmt.Errorf("notification delivery query facade init failed: %w", err)
	}
	deliveryCommands, err := deliveryapplication.NewNotificationDeliveryJobCommandFacade(store)
	if err != nil {
		return fmt.Errorf("notification delivery command facade init failed: %w", err)
	}
	handler, err := httpadapter.NewHandler(httpadapter.HandlerDependencies{
		AppMessageCommands: appMessageCommands,
		AppMessageQueries:  appMessageQueries,
	})
	if err != nil {
		return fmt.Errorf("notification http handler init failed: %w", err)
	}
	deliveryHandler, err := deliveryhttp.NewHandler(deliveryCommands, deliveryQueries)
	if err != nil {
		return fmt.Errorf("notification delivery http handler init failed: %w", err)
	}
	deliveryHandler.WithIncomingCallCoordinator(incomingCoordinator)

	rootMux := http.NewServeMux()
	rootMux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	readiness := rthealth.NewChecker()
	readiness.Register("mongodb", func(hctx context.Context) error {
		return mongoClient.Ping(hctx, nil)
	})
	readiness.Register("realtime-redis", func(hctx context.Context) error {
		return redisRouter.Scene("realtime").Ping(hctx)
	})
	readiness.Register("general-redis", func(hctx context.Context) error {
		return redisRouter.Scene("general").Ping(hctx)
	})
	readiness.Register("account-security-authority", func(readyCtx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(readyCtx)
	})
	readiness.Register("interaction-consumer", func(context.Context) error {
		return interactionConsumer.Healthy(10 * time.Second)
	})
	readiness.Register("account-closure-consumer", func(context.Context) error {
		return accountClosureConsumer.Healthy(10 * time.Second)
	})
	readiness.Register("rtc-consumer", func(context.Context) error {
		return rtcConsumer.Healthy(10 * time.Second)
	})
	readiness.Register("external-result-consumer", func(context.Context) error {
		return externalResultConsumer.Healthy(10 * time.Second)
	})
	readiness.Register("delivery-outbox-relay", func(context.Context) error {
		return deliveryOutboxRelay.Healthy(10 * time.Second)
	})
	rootMux.HandleFunc("/readyz", readiness.Handler())
	rootMux.Handle("/metrics", rtmetrics.Handler())
	serviceMux := http.NewServeMux()
	handler.RegisterRoutes(serviceMux)
	deliveryHandler.RegisterRoutes(serviceMux)
	serviceHandler, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		serviceMux,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/notification/account-closure/dead-letters:recover",
			Module:   rterr.ModuleNotification,
			Releaser: accountClosureConsumer,
		},
	)
	if err != nil {
		return fmt.Errorf("account-closure recovery route: %w", err)
	}
	rootMux.Handle(
		"/",
		rtauth.RequireGeneratedOperationAuthorization(
			operationsecurity.ForDomain("notification"),
		)(serviceHandler),
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
	timeouts := rtauth.ContractHTTPServerTimeouts(
		operationsecurity.ForDomain("notification"),
	)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(withObservability),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	module.configDigest = strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("notification-service", "CONFIG_VERSION"),
	)
	if module.configDigest == "" {
		module.configDigest = fmt.Sprintf("%s:%s", appEnv, serviceName)
	}
	module.server = server
	module.readiness = readiness
	module.serveError = make(chan error, 1)
	module.workerStarts = []func(context.Context){
		func(workerCtx context.Context) {
			if err := deliveryOutboxRelay.Run(workerCtx, time.Second); err != nil && workerCtx.Err() == nil {
				slog.Error("NotificationDeliveryJob outbox relay stopped", "err", err)
			}
		},
		func(workerCtx context.Context) {
			interactionConsumer.Run(workerCtx, 250*time.Millisecond)
		},
		externalResultConsumer.Run,
		accountClosureConsumer.Run,
		func(workerCtx context.Context) {
			rtcConsumer.Run(workerCtx, 100*time.Millisecond)
		},
		func(workerCtx context.Context) {
			runWorkerLoop(workerCtx, service)
		},
		func(workerCtx context.Context) {
			runIncomingCallWorkerLoop(workerCtx, incomingCoordinator)
		},
	}
	server.Handler = module.admissionHandler(server.Handler)
	server.BaseContext = func(net.Listener) context.Context {
		if module.runContext != nil {
			return module.runContext
		}
		return context.Background()
	}
	return nil
}

func moduleInstanceID(module string, fallback string) string {
	value := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue(module, "SERVICE_INSTANCE_ID"),
	)
	if value == "" {
		return fallback
	}
	return value
}

func (module *Module) Name() string { return "notification-service" }

func (module *Module) ConfigDigest() string {
	if module == nil {
		return ""
	}
	return module.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.server == nil || module.readiness == nil || module.cleanup == nil {
		return errors.New("notification-service module is incomplete")
	}
	return nil
}

func (module *Module) PrepareMigration(context.Context) error {
	return nil
}

func (module *Module) Bind(context.Context) error {
	if module == nil || module.server == nil {
		return errors.New("notification-service HTTP server is unavailable")
	}
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("notification-service listener bind: %w", err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(ctx context.Context) error {
	if module == nil || module.listener == nil {
		return errors.New("notification-service listener is not bound")
	}
	module.runContext, module.workerCancel = context.WithCancel(ctx)
	for _, start := range module.workerStarts {
		module.workerGroup.Add(1)
		module.startWorker(start)
	}
	module.workerGroup.Add(1)
	go func() {
		defer module.workerGroup.Done()
		log.Printf("notification-service listening on %s", module.server.Addr)
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
		return fmt.Errorf("notification-service readiness failed: %v", result.FailedChecks)
	}
	select {
	case err := <-module.serveError:
		return fmt.Errorf("notification-service listener failed: %w", err)
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
		result = errors.Join(result, module.server.Shutdown(ctx))
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
			http.Error(writer, `{"status":"unavailable"}`, http.StatusServiceUnavailable)
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
	coordinator *deliveryapplication.IncomingCallDeliveryCoordinator,
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

func requiredNonNegativeIntEnv(key string) (int, error) {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return 0, fmt.Errorf("%s is required", key)
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value < 0 {
		return 0, fmt.Errorf("%s must be a non-negative integer", key)
	}
	return value, nil
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
