package main

import (
	"context"
	"fmt"
	"log"
	"log/slog"
	"net/http"
	"os"
	configrelease "quwoquan_service/runtime/configrelease"
	"strconv"
	"strings"
	"sync"
	"time"

	"gopkg.in/yaml.v3"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtmongo "quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	rtauth "quwoquan_service/runtime/auth"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rtotel "quwoquan_service/runtime/otel"

	runtimeconfig "quwoquan_service/runtime/config"
	rterr "quwoquan_service/runtime/errors"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/rtc-service/internal/rtc/call_session/adapters/inbound/http"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/adapters/inbound/mq"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	callsession "quwoquan_service/services/rtc-service/internal/rtc/call_session/domain"
	rtccache "quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/cache"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/livekit"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/persistence"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/providerbinding"
	rtcconfig "quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/runtimeconfig"
)

type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`
	Pool     struct {
		Size    int `yaml:"size"`
		MinIdle int `yaml:"min_idle"`
	} `yaml:"pool"`
}

type config struct {
	Config struct {
		Version         string `yaml:"version"`
		MinImageVersion string `yaml:"min_image_version"`
		MaxImageVersion string `yaml:"max_image_version"`
	} `yaml:"config"`

	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`

	UserAccountSecurityAuthority struct {
		BaseURL   string `yaml:"base_url"`
		TimeoutMs int    `yaml:"timeout_ms"`
	} `yaml:"user_account_security_authority"`

	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`

	Redis struct {
		Realtime redisSceneCfg `yaml:"realtime"`
		General  redisSceneCfg `yaml:"general"`
	} `yaml:"redis"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("rtc-service runtime identity invalid: %v", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("rtc-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("rtc-service config compatibility failed: %v", err)
	}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("rtc-service access token config invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("rtc-service access token verifier invalid: %v", err)
	}
	accountSecurityAuthority, err := rtcconfig.NewAccountSecurityAuthority(
		accessTokenConfig,
		cfg.UserAccountSecurityAuthority.BaseURL,
		cfg.UserAccountSecurityAuthority.TimeoutMs,
	)
	if err != nil {
		log.Fatalf("rtc-service account security authority invalid: %v", err)
	}

	addr := getenvOrDefault("RTC_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18083"
	}

	logger := slog.Default()
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())

	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("rtc-service runtime log exporter init failed: %v", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, "info", nil)
	if err != nil {
		log.Fatalf("rtc-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		log.Fatalf("rtc-service exception logger init failed: %v", err)
	}

	router := buildRedisRouter(cfg)
	defer router.Close()

	ctx := context.Background()
	messageTransport, err := requireRTCMessageTransport(
		ctx,
		appEnv,
		router,
		map[string]string{
			"general":  toSceneConfig(cfg.Redis.General).Mode,
			"realtime": toSceneConfig(cfg.Redis.Realtime).Mode,
		},
	)
	if err != nil {
		log.Fatalf("rtc-service message transport preflight failed: %v", err)
	}

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "rtc-service", SamplingRatio: 0.1})
	defer otelShutdown()

	if err := router.PingAll(ctx); err != nil {
		log.Printf("WARN: rtc-service redis ping: %v", err)
	}
	mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: cfg.MongoDB.URI}, "rtc-service")
	defer func() { _ = mongoClient.Disconnect(ctx) }()

	mongoDB := mongoClient.Database(cfg.MongoDB.Database)
	callStore := persistence.NewMongoCallStore(mongoDB)
	if err := callStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("rtc-service call session indexes unavailable: %v", err)
	}
	callCache := rtccache.NewCallStateCache(router.Scene("general"))
	realtimePublisher := mq.NewRealtimePublisher(messageTransport)

	mediaBinding, err := providerbinding.ResolveMediaTransport(
		appEnv,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("rtc-service media transport binding invalid: %v", err)
	}
	var roomAdapter application.MediaRoomProvider
	switch mediaBinding.AdapterID {
	case livekit.ProtocolFixtureAdapterID:
		roomAdapter = livekit.NewProtocolFixtureRoomAdapter()
	case livekit.AdapterID:
		livekitCB := rtgov.NewCircuitBreaker(5, 15*time.Second, logger)
		livekitClient := rtgov.WrapClientWithCB(
			&http.Client{Timeout: mediaBinding.Timeout},
			livekitCB,
		)
		roomAdapter = livekit.NewLiveKitRoomAdapter(
			mediaBinding.ConnectionURL,
			mediaBinding.APIKey,
			mediaBinding.APISecret,
			livekit.WithHTTPClient(livekitClient),
		)
	default:
		log.Fatalf(
			"rtc-service media transport adapter mismatch: got %q",
			mediaBinding.AdapterID,
		)
	}
	domainSvc := callsession.NewCallSessionService()

	userServiceBaseURL := strings.TrimSpace(os.Getenv("USER_SERVICE_BASE_URL"))
	if userServiceBaseURL == "" && failFastEnvironment(appEnv) {
		log.Fatalf("rtc-service requires USER_SERVICE_BASE_URL in %s for the one-to-one relationship gate", appEnv)
	}
	relationshipGate := application.DenyRelationshipGate()
	if userServiceBaseURL != "" {
		profileCB := rtgov.NewCircuitBreaker(5, 15*time.Second, logger)
		profileClient := rtgov.WrapClientWithCB(&http.Client{Timeout: 2 * time.Second}, profileCB)
		relationshipGate = httpadapter.NewUserRelationshipGate(userServiceBaseURL, profileClient)
	}
	orchestrator := application.NewCallOrchestrator(
		callStore,
		callCache,
		domainSvc,
		roomAdapter,
		relationshipGate,
		application.WithCallAccountSecurityGate(
			application.NewCallAccountSecurityGate(accountSecurityAuthority),
		),
	)
	outboxRelay := application.NewCallOutboxRelay(
		callStore,
		realtimePublisher,
	)
	accountSecurityFailures := rtccache.NewAccountSecurityEventFailureStore(
		router.Scene("general"),
	)
	accountSecurityConsumer, err := mq.NewUserAccountSecurityConsumer(
		messageTransport,
		orchestrator,
		accountSecurityFailures,
		instanceID,
		logger,
		mq.DefaultUserAccountSecurityConsumerConfig(),
	)
	if err != nil {
		log.Fatalf("rtc-service account security consumer invalid: %v", err)
	}
	workerCtx, cancelWorkers := context.WithCancel(context.Background())
	var workerWG sync.WaitGroup
	workerWG.Add(3)
	go func() {
		defer workerWG.Done()
		runRecoveringWorker(
			workerCtx,
			logger,
			"rtc call outbox relay",
			func(runCtx context.Context) error {
				return outboxRelay.Run(runCtx, 100*time.Millisecond)
			},
		)
	}()
	// 振铃超时收割：无人接听迁移 ended/no_answer 并经 outbox 下发 call.ended
	//（storage.yaml lifecycle_timers.ring_timeout 同源）。
	go func() {
		defer workerWG.Done()
		runRecoveringWorker(
			workerCtx,
			logger,
			"rtc ring timeout sweeper",
			func(runCtx context.Context) error {
				return orchestrator.RunRingTimeoutSweeper(runCtx, 5*time.Second)
			},
		)
	}()
	go func() {
		defer workerWG.Done()
		accountSecurityConsumer.Run(workerCtx)
	}()
	handler := httpadapter.NewCallHandler(orchestrator).Routes()
	handler, err = runtimemessaging.WithDeadLetterRecoveryRoute(
		handler,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/rtc/account-closure/dead-letters:recover",
			Module:   rterr.ModuleRTC,
			Releaser: accountSecurityConsumer,
		},
	)
	if err != nil {
		log.Fatalf("rtc account-closure recovery route failed: %v", err)
	}

	healthChecker := rthealth.NewChecker()
	healthChecker.Register("redis", func(hctx context.Context) error {
		return router.PingAll(hctx)
	})
	healthChecker.Register("mongodb", func(hctx context.Context) error {
		return mongoClient.Ping(hctx, nil)
	})
	healthChecker.Register("account_security_authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	healthChecker.Register("user_account_security_consumer", func(context.Context) error {
		return accountSecurityConsumer.Healthy(10 * time.Second)
	})
	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle(
		"/",
		rtauth.RequireGeneratedOperationAuthorization(
			operationsecurity.ForDomain("rtc"),
		)(handler),
	)

	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "rtc-service",
		ServiceName:       "rtc-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "rtc-service",
		Src:               "rtc-service",
	}, ioLogger, processLogger, exceptionLogger)

	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(observedHandler)
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		log.Fatalf("rtc-service device ticket config invalid: %v", err)
	}
	deviceVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		log.Fatalf("rtc-service device ticket verifier invalid: %v", err)
	}
	authenticated := rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      accessVerifier,
		DeviceTicketVerifier:     deviceVerifier,
		AccountSecurityAuthority: accountSecurityAuthority,
	})(rateLimited)
	server := &http.Server{
		Addr:              addr,
		Handler:           authenticated,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	logger.Info("rtc-service starting", "addr", addr, "env", appEnv)
	serveErr := rthttp.ListenAndServeGraceful(server, 15*time.Second)
	cancelWorkers()
	workerWG.Wait()
	if serveErr != nil {
		log.Fatalf("rtc-service: %v", serveErr)
	}
}

func runRecoveringWorker(
	ctx context.Context,
	logger *slog.Logger,
	name string,
	run func(context.Context) error,
) {
	for {
		err := run(ctx)
		if err == nil || ctx.Err() != nil {
			return
		}
		logger.Error(name+" stopped", "error", err)
		retry := time.NewTimer(time.Second)
		select {
		case <-ctx.Done():
			if !retry.Stop() {
				select {
				case <-retry.C:
				default:
				}
			}
			return
		case <-retry.C:
		}
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "rtc-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")

	if !isValidAppEnv(appEnv) {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	if requiresConfigVersion(appEnv) && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
}

func isValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func requiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod":
		return true
	default:
		return false
	}
}

func failFastEnvironment(appEnv string) bool {
	switch strings.TrimSpace(appEnv) {
	case "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func getenvOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func hostname() string {
	h, err := os.Hostname()
	if err != nil {
		return "unknown"
	}
	return h
}

func mergeConfigFile(cfg *config, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err := yaml.Unmarshal(raw, cfg); err != nil {
		return fmt.Errorf("parse %s: %w", path, err)
	}
	return nil
}

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	cfg := config{}
	path, err := configrelease.File(configRoot, serviceName, appEnv)
	if err != nil {
		return config{}, err
	}
	if err := mergeConfigFile(&cfg, path); err != nil {
		return config{}, fmt.Errorf("read generated runtime config: %w", err)
	}
	return cfg, nil
}

func validateRuntimeCompatibility(cfg config, configVersion, imageVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	if strings.TrimSpace(imageVersion) == "" {
		return nil
	}
	if cfg.Config.MinImageVersion != "" && compareSemver(imageVersion, cfg.Config.MinImageVersion) < 0 {
		return fmt.Errorf("IMAGE_VERSION=%s below min_image_version=%s", imageVersion, cfg.Config.MinImageVersion)
	}
	if cfg.Config.MaxImageVersion != "" && compareSemver(imageVersion, cfg.Config.MaxImageVersion) > 0 {
		return fmt.Errorf("IMAGE_VERSION=%s above max_image_version=%s", imageVersion, cfg.Config.MaxImageVersion)
	}
	return nil
}

func compareSemver(a, b string) int {
	parse := func(v string) [3]int {
		var out [3]int
		parts := strings.Split(strings.TrimPrefix(strings.TrimSpace(v), "v"), ".")
		for i := 0; i < len(parts) && i < 3; i++ {
			n, _ := strconv.Atoi(parts[i])
			out[i] = n
		}
		return out
	}
	av := parse(a)
	bv := parse(b)
	for i := 0; i < 3; i++ {
		if av[i] > bv[i] {
			return 1
		}
		if av[i] < bv[i] {
			return -1
		}
	}
	return 0
}

func applyEnvOverrides(cfg *config) {
	if v := os.Getenv("MONGO_URI"); v != "" {
		cfg.MongoDB.URI = v
	}
	if v := os.Getenv("MONGO_DATABASE"); v != "" {
		cfg.MongoDB.Database = v
	}

	applyRedisSceneEnv("RTC_REDIS_REALTIME", &cfg.Redis.Realtime)
	applyRedisSceneEnv("RTC_REDIS_GENERAL", &cfg.Redis.General)

	if v := os.Getenv("REDIS_ADDR"); v != "" {
		if cfg.Redis.General.Addr == "" {
			cfg.Redis.General.Addr = v
		}
		if cfg.Redis.Realtime.Addr == "" {
			cfg.Redis.Realtime.Addr = v
		}
	}
}

func applyRedisSceneEnv(prefix string, cfg *redisSceneCfg) {
	if v := os.Getenv(prefix + "_MODE"); v != "" {
		cfg.Mode = v
	}
	if v := os.Getenv(prefix + "_ADDR"); v != "" {
		cfg.Addr = v
	}
	if v := os.Getenv(prefix + "_ADDRS"); v != "" {
		cfg.Addrs = strings.Split(v, ",")
	}
	if v := os.Getenv(prefix + "_PASSWORD"); v != "" {
		cfg.Password = v
	}
	if v := os.Getenv(prefix + "_TLS"); v == "true" || v == "1" {
		cfg.TLS = true
	}
}

func buildRedisRouter(cfg config) *rtredis.Router {
	generalScene := toSceneConfig(cfg.Redis.General)
	routerCfg := rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"realtime": toSceneConfig(cfg.Redis.Realtime),
			"general":  generalScene,
			"rec":      generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	}
	return platformredis.MustNewRouter(routerCfg)
}

func toSceneConfig(r redisSceneCfg) rtredis.SceneConfig {
	mode := strings.ToLower(strings.TrimSpace(r.Mode))
	if mode == "" {
		mode = "standalone"
	}
	if mode == "standalone" && r.Addr == "" {
		mode = "memory"
	}
	if mode == "cluster" && len(r.Addrs) == 0 {
		mode = "memory"
	}
	return rtredis.SceneConfig{
		Mode:         mode,
		Addr:         r.Addr,
		Addrs:        r.Addrs,
		Password:     r.Password,
		DB:           r.DB,
		TLS:          r.TLS,
		PoolSize:     r.Pool.Size,
		MinIdleConns: r.Pool.MinIdle,
	}
}
