// realtime-gateway：统一实时通信网关（runtime_session）。
// 职责最小化：ticket 鉴权、WS/LongPoll 连接管理（lease+fencing+presence）、
// 按可信身份订阅 Redis realtime scene 并透传事件。不承载任何业务聚合。
package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
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
	httpadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/http"
	streamadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/stream"
	wsadapter "quwoquan_service/services/realtime-gateway/internal/realtime/connection/adapters/inbound/ws"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/infrastructure/redisstore"
	presenceconnection "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/adapters/inbound/connection"
	presencehttp "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/adapters/inbound/http"
	presenceapp "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/application"
	presenceredis "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/infrastructure/redisstore"
)

func main() {
	if err := run(); err != nil {
		log.Fatalf("realtime-gateway: %v", err)
	}
}

func run() error {
	serviceName := getenvOrDefault("SERVICE_NAME", "realtime-gateway")
	appEnv := getenvOrDefault("APP_ENV", "alpha")
	runtimeConfig, err := loadRealtimeRuntimeConfig(
		serviceName,
		appEnv,
		strings.TrimSpace(os.Getenv("CONFIG_ROOT")),
	)
	if err != nil {
		return fmt.Errorf("runtime config invalid: %w", err)
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName,
		appEnv,
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
	accountSecurityTimeout := time.Duration(
		runtimeConfig.UserService.AccountSecurity.TimeoutMs,
	) * time.Millisecond
	accountSecurityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"realtime-gateway",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return fmt.Errorf(
			"account security authority service credentials invalid: %w",
			err,
		)
	}
	accountSecurityAuthority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL: runtimeConfig.UserService.AccountSecurity.BaseURL,
			HTTPClient: &http.Client{
				Timeout: accountSecurityTimeout,
			},
			Credentials: accountSecurityCredentials,
			Timeout:     accountSecurityTimeout,
		},
	)
	if err != nil {
		return fmt.Errorf("account security authority invalid: %w", err)
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
		ServiceName:   "realtime-gateway",
		SamplingRatio: 0.1,
	})
	defer otelShutdown()

	redisRouter, realtimeScene, err := buildRedisRouter(runtimeConfig)
	if err != nil {
		return err
	}
	defer redisRouter.Close()
	messageTransport, err := requireMessageTransport(
		ctx,
		appEnv,
		redisRouter,
		map[string]string{"realtime": realtimeScene.Mode},
	)
	if err != nil {
		return fmt.Errorf("realtime-gateway message transport preflight failed: %w", err)
	}
	realtimeClient := redisRouter.Scene("realtime")
	if err := realtimeClient.Ping(ctx); err != nil {
		if failFastEnvironment() {
			return fmt.Errorf("realtime redis unavailable: %w", err)
		}
		log.Printf(
			"WARN: realtime-gateway redis ping errorDigest=%s",
			application.ErrorDigest(err),
		)
	}

	logger := slog.Default()
	nodeID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())

	ticketStore := redisstore.NewTicketStore(realtimeClient)
	leaseStore := redisstore.NewLeaseStore(realtimeClient)
	presenceStore, err := presenceredis.NewStore(realtimeClient)
	if err != nil {
		return err
	}
	presenceProjector, err := presenceapp.NewProjector(presenceStore)
	if err != nil {
		return err
	}
	presenceQueries, err := presenceapp.NewQueryFacade(presenceStore)
	if err != nil {
		return err
	}
	presenceRevoker, err := presenceapp.NewRevoker(presenceStore)
	if err != nil {
		return err
	}
	presenceConnection, err := presenceconnection.NewProjector(
		presenceProjector,
		presenceRevoker,
	)
	if err != nil {
		return err
	}
	eventSource := redisstore.NewEventSource(messageTransport)
	resumeReader, err := redisstore.NewResumableEventReader(messageTransport)
	if err != nil {
		return fmt.Errorf("realtime resumable event reader init failed: %w", err)
	}
	accountSecurityStore := redisstore.NewAccountSecurityStateStore(
		realtimeClient,
		presenceConnection,
	)
	accountSecurityRelay := redisstore.NewAccountSecurityRelay(realtimeClient)

	tickets, err := application.NewTicketService(
		ticketStore,
		accountSecurityAuthority,
		accountSecurityStore,
	)
	if err != nil {
		return err
	}
	hub, err := application.NewHub(
		leaseStore,
		presenceConnection,
		eventSource,
		accountSecurityAuthority,
		accountSecurityStore,
		accountSecurityRelay,
		nodeID,
		logger,
	)
	if err != nil {
		return err
	}
	if err := hub.StartAccountSecurityRelay(ctx); err != nil {
		return fmt.Errorf("account security relay startup failed: %w", err)
	}
	defer hub.CloseAccountSecurityRelay()
	durableTransport, ok := messageTransport.(streamadapter.DurableMessageTransport)
	if !ok {
		return fmt.Errorf(
			"realtime message transport does not support durable account security consumption",
		)
	}
	accountSecurityConsumer, err := streamadapter.NewUserAccountSecurityConsumer(
		durableTransport,
		accountSecurityStore,
		accountSecurityRelay,
		hub,
		redisstore.NewAccountSecurityEventFailureStore(realtimeClient),
		"realtime-account-security-"+nodeID,
		logger,
		streamadapter.DefaultUserAccountSecurityConsumerConfig(),
	)
	if err != nil {
		return fmt.Errorf("account security consumer init failed: %w", err)
	}
	consumerSetupCtx, cancelConsumerSetup := context.WithTimeout(
		ctx,
		accountSecurityTimeout,
	)
	consumerSetupErr := accountSecurityConsumer.EnsureGroup(consumerSetupCtx)
	cancelConsumerSetup()
	if consumerSetupErr != nil {
		return fmt.Errorf(
			"account security consumer group setup failed: %w",
			consumerSetupErr,
		)
	}
	go accountSecurityConsumer.Run(ctx)
	handler, err := httpadapter.NewHandler(
		tickets,
		hub,
		resumeReader,
		httpadapter.DefaultTransportConfig(),
	)
	if err != nil {
		return err
	}
	operationDescriptors := operationsecurity.ForDomain("realtime")
	upgradeHandler, err := wsadapter.NewHandler(
		tickets,
		hub,
		logger,
		operationDescriptors,
	)
	if err != nil {
		return err
	}

	guarded := http.NewServeMux()
	handler.Routes(guarded)
	presencehttp.NewHandler(presenceQueries).Routes(guarded)
	guardedHandler, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		guarded,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/realtime/account-closure/dead-letters:recover",
			Module:   rterr.ModuleRealtime,
			Releaser: accountSecurityConsumer,
		},
	)
	if err != nil {
		return fmt.Errorf("account-closure recovery route: %w", err)
	}

	rootMux := http.NewServeMux()
	readinessChecker := rthealth.NewChecker()
	readinessChecker.Register("realtime_redis", func(checkCtx context.Context) error {
		return realtimeClient.Ping(checkCtx)
	})
	readinessChecker.Register(
		"account_security_authority",
		func(checkCtx context.Context) error {
			return accountSecurityAuthority.CheckAccountSecurityAuthority(checkCtx)
		},
	)
	readinessChecker.Register(
		"account_security_relay",
		func(context.Context) error {
			return hub.AccountSecurityRelayHealthy()
		},
	)
	readinessChecker.Register(
		"user_account_security_consumer",
		func(context.Context) error {
			return accountSecurityConsumer.Healthy(10 * time.Second)
		},
	)
	if err := httpadapter.RegisterRuntimeProbeRoutes(
		rootMux,
		readinessChecker,
		rtmetrics.Handler(),
	); err != nil {
		return fmt.Errorf("runtime probe routes: %w", err)
	}
	// WebSocket 在 handler 内先消费一次性 ticket，注入可信 principal 后再
	// 执行同一 runtime operation contract；浏览器握手无需伪造 Bearer header。
	rootMux.HandleFunc("GET /realtime/ws", upgradeHandler.HandleUpgrade)
	rootMux.Handle(
		"/",
		rtauth.EnforceRuntimeOperationContract(operationDescriptors)(guardedHandler),
	)

	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("realtime-gateway runtime log exporter init failed: %v", err)
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
	withObservability := rthttp.NewHTTPServerMiddleware(
		rootMux,
		rthttp.HTTPServerMiddlewareConfig{
			Service:           "realtime-gateway",
			Origin:            "cloud",
			Direction:         "inbound",
			SourceID:          "realtime-gateway.http",
			Src:               "gateway",
			ServiceName:       "realtime-gateway",
			ServiceInstanceID: nodeID,
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)

	addr := strings.TrimSpace(runtimeConfig.Service.HTTP.Addr)
	if override := strings.TrimSpace(os.Getenv("REALTIME_GATEWAY_ADDR")); override != "" {
		addr = override
	}
	if addr == "" {
		return fmt.Errorf("service.http.addr is required")
	}
	timeouts := rtauth.ContractHTTPServerTimeouts(
		operationDescriptors,
	)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(withObservability),
		BaseContext:       func(_ net.Listener) context.Context { return ctx },
		ReadHeaderTimeout: timeouts.ReadHeader,
		// WS 升级后连接被 hijack，Go 不会重置已设置的写截止时间，coder/websocket
		// 也不清除它，所以这里必须不设 WriteTimeout；LongPoll 的上限由 operation
		// guard 施加的 reliability.timeout_ms 承担。
		IdleTimeout: timeouts.Idle,
	}
	log.Printf("realtime-gateway listening on %s", server.Addr)
	return rthttp.ListenAndServeGraceful(server, 15*time.Second)
}

func buildRedisRouter(cfg realtimeRuntimeConfig) (*rtredis.Router, rtredis.SceneConfig, error) {
	sceneConfig := rtredis.SceneConfig{
		Mode:     cfg.Redis.Realtime.Mode,
		Addr:     cfg.Redis.Realtime.Addr,
		Addrs:    cfg.Redis.Realtime.Addrs,
		Password: os.Getenv("REALTIME_REDIS_PASSWORD"),
	}
	if mode := strings.TrimSpace(os.Getenv("REALTIME_REDIS_MODE")); mode != "" {
		sceneConfig.Mode = mode
	}
	if addr := strings.TrimSpace(os.Getenv("REALTIME_REDIS_ADDR")); addr != "" {
		sceneConfig.Addr = addr
	}
	if addrs := strings.TrimSpace(os.Getenv("REALTIME_REDIS_ADDRS")); addrs != "" {
		sceneConfig.Addrs = strings.Split(addrs, ",")
	}
	if failFastEnvironment() && sceneConfig.Mode == "memory" {
		return nil, rtredis.SceneConfig{}, fmt.Errorf(
			"REALTIME_REDIS_MODE=memory is forbidden in %s",
			getenvOrDefault("APP_ENV", ""),
		)
	}
	router, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes:       map[string]rtredis.SceneConfig{"realtime": sceneConfig},
		DefaultScene: "realtime",
	})
	if err != nil {
		return nil, rtredis.SceneConfig{}, err
	}
	return router, sceneConfig, nil
}

func failFastEnvironment() bool {
	switch strings.TrimSpace(os.Getenv("APP_ENV")) {
	case "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func getenvOrDefault(key string, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func hostname() string {
	name, err := os.Hostname()
	if err != nil || strings.TrimSpace(name) == "" {
		return "realtime-gateway-local"
	}
	return name
}
