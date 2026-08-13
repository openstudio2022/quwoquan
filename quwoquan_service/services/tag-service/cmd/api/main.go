package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"gopkg.in/yaml.v3"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	configrelease "quwoquan_service/runtime/configrelease"
	"quwoquan_service/runtime/controlplane"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	"quwoquan_service/runtime/servicehost"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	signalstream "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/adapters/inbound/stream"
	indexpersistence "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/infrastructure/persistence"
	feedbackhttp "quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/application/tagfeedback"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/infrastructure/tagfeedbackstore"
	nodehttp "quwoquan_service/services/tag-service/internal/tag/tag_node_view/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
	releasehttp "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/adapters/inbound/http"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

type config struct {
	Config struct {
		Version string `yaml:"version"`
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

	Mongo struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongo"`

	Redis struct {
		General redisSceneCfg `yaml:"general"`
	} `yaml:"redis"`
}

type Module struct {
	configDigest string
	server       *http.Server
	health       *rthealth.Checker
	listener     net.Listener
	admission    atomic.Bool
	serveError   chan error
	workerCancel context.CancelFunc
	workerGroup  sync.WaitGroup
	workerStart  []func(context.Context)
	cleanup      func()
}

var _ servicehost.Module = (*Module)(nil)

func NewModule() (_ *Module, resultErr error) {
	cleanup := func() {}
	initialized := false
	defer func() {
		if !initialized {
			cleanup()
		}
	}()
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		return nil, fmt.Errorf("tag-service runtime identity invalid: %w", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		return nil, fmt.Errorf("tag-service config load failed: %w", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion); err != nil {
		return nil, fmt.Errorf("tag-service config identity failed: %w", err)
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)

	configProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(configProvider)
	if err != nil {
		return nil, fmt.Errorf("tag-service access token config invalid: %w", err)
	}
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		serviceName,
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("tag-service account security authority credential init failed: %w", err)
	}
	accountSecurityAuthorityTimeout := time.Duration(
		cfg.UserAccountSecurityAuthority.TimeoutMs,
	) * time.Millisecond
	accountSecurityAuthority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL: cfg.UserAccountSecurityAuthority.BaseURL,
			HTTPClient: &http.Client{
				Timeout: accountSecurityAuthorityTimeout,
			},
			Credentials: accountSecurityAuthorityCredentials,
			Timeout:     accountSecurityAuthorityTimeout,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("tag-service account security authority config invalid: %w", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return nil, fmt.Errorf("tag-service access token verifier invalid: %w", err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(configProvider)
	if err != nil {
		return nil, fmt.Errorf("tag-service device ticket config invalid: %w", err)
	}
	deviceTicketVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		return nil, fmt.Errorf("tag-service device ticket verifier invalid: %w", err)
	}

	addr := getenvOrDefault("TAG_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18092"
	}

	ctx := context.Background()

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "tag-service", SamplingRatio: 0.1})
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		otelShutdown()
	})

	mongoURI := getenvOrDefault("TAG_MONGO_URI", cfg.Mongo.URI)
	if mongoURI == "" {
		mongoURI = "mongodb://localhost:27017"
	}
	mongoDBName := getenvOrDefault("TAG_MONGO_DATABASE", cfg.Mongo.Database)
	if mongoDBName == "" {
		mongoDBName = "quwoquan_tag"
	}

	mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: mongoURI}, "tag-service")
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		_ = mongoClient.Disconnect(context.Background())
	})

	db := mongoClient.Database(mongoDBName)
	tagNodeStore := persistence.NewMongoTagNodeStore(db.Collection("tag_nodes"))
	objectTagStore := indexpersistence.NewMongoObjectTagIndexStore(db.Collection("object_tag_index"))
	if err := tagNodeStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("tag-service ensure tag_nodes indexes: %w", err)
	}
	if err := objectTagStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("tag-service ensure object_tag_index indexes: %w", err)
	}

	releaseStore := taxonomyreleasestore.NewStore(db)
	if err := releaseStore.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("tag-service ensure tag_taxonomy_releases indexes: %w", err)
	}
	tagService := application.NewTagService(tagNodeStore, objectTagStore, releaseStore)
	releaseFacade, err := taxonomyrelease.NewFacade(releaseStore, tagNodeStore)
	if err != nil {
		return nil, fmt.Errorf("tag-service taxonomy release facade init failed: %w", err)
	}
	feedbackSink := tagfeedbackstore.NewSink(db)
	if err := feedbackSink.EnsureIndexes(ctx); err != nil {
		return nil, fmt.Errorf("tag-service ensure tag_feedback_fact indexes: %w", err)
	}
	feedbackFacade, err := tagfeedback.NewFacade(feedbackSink, tagService)
	if err != nil {
		return nil, fmt.Errorf("tag-service tag feedback facade init failed: %w", err)
	}

	redisRouter, redisSceneModes := buildTagRedisRouter(cfg)
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		_ = redisRouter.Close()
	})
	messageTransport, err := requireTagAPIMessageTransport(
		ctx,
		appEnv,
		redisRouter,
		redisSceneModes,
	)
	if err != nil {
		return nil, fmt.Errorf("tag-service message transport init failed: %w", err)
	}
	profileTagConsumer, err := signalstream.NewUserProfileTagConsumer(
		messageTransport,
		objectTagStore,
		serviceName,
		slog.Default(),
	)
	if err != nil {
		return nil, fmt.Errorf("tag-service user profile tag consumer init failed: %w", err)
	}
	feedbackEventPublisher, err := tagfeedbackstore.NewStreamEventPublisher(
		messageTransport,
	)
	if err != nil {
		return nil, fmt.Errorf("tag-service feedback event publisher init failed: %w", err)
	}
	feedbackEventRelay, err := tagfeedbackstore.NewEventRelay(
		feedbackSink,
		feedbackEventPublisher,
		slog.Default(),
	)
	if err != nil {
		return nil, fmt.Errorf("tag-service feedback event relay init failed: %w", err)
	}

	routesMux := http.NewServeMux()
	nodehttp.NewTagHandler(tagService).Register(routesMux)
	releasehttp.NewTaxonomyReleaseHandler(releaseFacade).Register(routesMux)
	feedbackhttp.NewTagFeedbackHandler(feedbackFacade).Register(routesMux)
	generatedOperationGuard := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("tag"),
	)(routesMux)

	healthChecker := rthealth.NewChecker()
	healthChecker.Register("account-security-authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	healthChecker.Register("mongodb", func(hctx context.Context) error {
		return mongoClient.Ping(hctx, nil)
	})
	healthChecker.Register("taxonomy-projection", func(hctx context.Context) error {
		release, found, err := releaseStore.FindActive(hctx)
		if err != nil {
			return err
		}
		if !found {
			// 冷启动的空库尚无任何 taxonomy release：canonical taxonomy 由
			// Data CLI ship apply 在全栈就绪之后导入，若此处 fail 会构成
			// 「readiness 等导入、导入等 readiness」的环境死锁。空 taxonomy
			// 是合法初始状态（查询按空集服务）；只有「存在 active release
			// 但节点投影与其不一致」才是必须 fail-closed 的损坏状态。
			return nil
		}
		return tagNodeStore.ValidateReleaseProjection(
			hctx,
			release.ReleaseID,
			release.NodeCount,
		)
	})
	healthChecker.Register("redis", redisRouter.PingAll)
	healthChecker.Register("profile-tag-consumer", func(context.Context) error {
		return profileTagConsumer.Healthy(15 * time.Second)
	})
	healthChecker.Register("feedback-event-relay", func(hctx context.Context) error {
		return feedbackEventRelay.Healthy(hctx, 15*time.Second)
	})

	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", generatedOperationGuard)

	instanceID, _ := os.Hostname()
	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		return nil, fmt.Errorf("tag-service runtime log exporter init failed: %w", err)
	}
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		runtimeLogExporter.Close()
	})
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		errorLogWriter.Close()
		standardLogWriter.Close()
	})
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, "info", nil)
	if err != nil {
		return nil, fmt.Errorf("tag-service process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		return nil, fmt.Errorf("tag-service exception logger init failed: %w", err)
	}
	observed := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "tag-service",
		ServiceName:       "tag-service",
		ServiceInstanceID: instanceID,
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observed, rthttp.CORSOptionsFromEnv())

	timeouts := rtauth.ContractHTTPServerTimeouts(
		operationsecurity.ForDomain("tag"),
	)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceTicketVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(corsHandler),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	module := &Module{
		configDigest: configVersion,
		server:       server,
		health:       healthChecker,
		serveError:   make(chan error, 1),
		workerStart: []func(context.Context){
			profileTagConsumer.Run,
			feedbackEventRelay.Run,
		},
		cleanup: cleanup,
	}
	if module.configDigest == "" {
		module.configDigest = cfg.Config.Version
	}
	if module.configDigest == "" {
		module.configDigest = operationsecurity.ContractGraphSHA256
	}
	server.Handler = module.admissionHandler(server.Handler)
	initialized = true
	return module, nil
}

func (module *Module) Name() string { return "tag-service" }

func (module *Module) ConfigDigest() string {
	if module == nil {
		return ""
	}
	return module.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.server == nil || module.health == nil || len(module.workerStart) != 2 {
		return errors.New("tag-service module is incomplete")
	}
	return nil
}

func (module *Module) PrepareMigration(context.Context) error {
	return nil
}

func (module *Module) Bind(context.Context) error {
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("tag-service listener bind: %w", err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(context.Context) error {
	if module.listener == nil {
		return errors.New("tag-service listener is not bound")
	}
	workerContext, workerCancel := context.WithCancel(context.Background())
	module.workerCancel = workerCancel
	for _, start := range module.workerStart {
		module.workerGroup.Add(1)
		module.startWorker(workerContext, start)
	}
	go func() {
		if err := module.server.Serve(module.listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			module.serveError <- err
		}
	}()
	return nil
}

func (module *Module) Ready(ctx context.Context) error {
	if result := module.health.Check(ctx); result.Status != "ok" {
		return fmt.Errorf("tag-service readiness failed: %v", result.FailedChecks)
	}
	select {
	case err := <-module.serveError:
		return fmt.Errorf("tag-service listener failed: %w", err)
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
	}
	if module.cleanup != nil {
		module.cleanup()
		module.cleanup = nil
	}
	return result
}

func (module *Module) startWorker(ctx context.Context, start func(context.Context)) {
	go func() {
		defer module.workerGroup.Done()
		start(ctx)
	}()
}

func (module *Module) admissionHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/healthz", "/metrics":
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

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("tag-service", "SERVICE_NAME"),
	)
	if serviceName == "" {
		serviceName = "tag-service"
	}
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = servicehost.ModuleEnvironmentValue(
		"tag-service",
		"CONFIG_VERSION",
	)
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

func getenvOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
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

func applyEnvOverrides(cfg *config) {
	if v := os.Getenv("TAG_MONGO_URI"); v != "" {
		cfg.Mongo.URI = v
	}
	if v := os.Getenv("TAG_MONGO_DATABASE"); v != "" {
		cfg.Mongo.Database = v
	}
	applyTagRedisEnvOverrides(&cfg.Redis.General)
}

func validateRuntimeConfigurationIdentity(cfg config, configVersion string) error {
	if strings.TrimSpace(configVersion) != "" && strings.TrimSpace(cfg.Config.Version) != "" && cfg.Config.Version != configVersion {
		return fmt.Errorf("CONFIG_VERSION mismatch: env=%s file=%s", configVersion, cfg.Config.Version)
	}
	return nil
}
