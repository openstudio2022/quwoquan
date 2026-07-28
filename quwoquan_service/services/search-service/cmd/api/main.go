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
	configrelease "quwoquan_service/runtime/configrelease"
	"strconv"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
	"quwoquan_service/generated/operationsecurity"
	rtmongodb "quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtredis "quwoquan_service/runtime/redis"
	searchruntimees "quwoquan_service/runtime/search/es"
	feedbackhttp "quwoquan_service/services/search-service/internal/search/feedback_fact/adapters/inbound/http"
	feedbackapplication "quwoquan_service/services/search-service/internal/search/feedback_fact/application"
	"quwoquan_service/services/search-service/internal/search/feedback_fact/infrastructure/feedbackstore"
	recenthttp "quwoquan_service/services/search-service/internal/search/recent_search_state/adapters/inbound/http"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/application"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/infrastructure/persistence"
	"quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/infrastructure/searchsignals"
	httpadapter "quwoquan_service/services/search-service/internal/search/search_query/adapters/inbound/http"
	mqadapter "quwoquan_service/services/search-service/internal/search/search_query/adapters/inbound/mq"
	"quwoquan_service/services/search-service/internal/search/search_query/application"
	"quwoquan_service/services/search-service/internal/search/search_query/application/queryheat"
	accountclosureinfra "quwoquan_service/services/search-service/internal/search/search_query/infrastructure/accountclosure"
	"quwoquan_service/services/search-service/internal/search/search_query/infrastructure/intersectionclient"
	"quwoquan_service/services/search-service/internal/search/search_query/infrastructure/queryheatstore"
	"quwoquan_service/services/search-service/internal/search/search_query/infrastructure/querylogstore"
	"quwoquan_service/services/search-service/internal/search/search_query/infrastructure/searchbackend"
	"quwoquan_service/services/search-service/internal/search/search_query/infrastructure/searchmetrics"
)

const serviceName = "search-service"

// heatRebuildInterval is how often the search-term heat read model is rebuilt
// from the query/feedback logs. The read-model TTL is wider than this so a brief
// rebuild stall never empties the served heat.
const heatRebuildInterval = 10 * time.Minute

type config struct {
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`

	AccountSecurityAuthority struct {
		BaseURL   string `yaml:"baseUrl"`
		TimeoutMs int    `yaml:"timeoutMs"`
	} `yaml:"accountSecurityAuthority"`

	ES searchbackend.ESConfig `yaml:"es"`

	// Mongo persists query logs + feedback + the heat read model. When unset
	// (alpha without Mongo), the service still serves searches with base ranking.
	Mongo struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongo"`

	Redis struct {
		General redisSceneCfg `yaml:"general"`
		Rec     redisSceneCfg `yaml:"rec"`
	} `yaml:"redis"`

	// Ranking carries the search-term heat boost weight and the AB rollout.
	Ranking struct {
		TermHeatBoost float64 `yaml:"termHeatBoost"`
		Experiment    struct {
			Enabled       bool   `yaml:"enabled"`
			PolicyVersion string `yaml:"policyVersion"`
			Buckets       []struct {
				Name      string `yaml:"name"`
				WeightPct int    `yaml:"weightPct"`
			} `yaml:"buckets"`
		} `yaml:"experiment"`
	} `yaml:"ranking"`

	ContentService struct {
		BaseURL string `yaml:"baseUrl"`
	} `yaml:"contentService"`
}

func main() {
	cfg, err := loadRuntimeConfig()
	if err != nil {
		log.Fatalf("%s config load failed: %v", serviceName, err)
	}
	normalizeDefaults(&cfg)
	applyESEnvOverrides(&cfg.ES)
	applyMongoEnvOverrides(&cfg)
	applyRedisEnvOverrides(&cfg)

	ctx := context.Background()
	appEnv := getenvOrDefault("APP_ENV", "alpha")
	controlplane.StartReleaseConfigAttestation(
		serviceName,
		appEnv,
		strings.TrimSpace(os.Getenv("CONFIG_ROOT")),
		strings.TrimSpace(os.Getenv("CONFIG_VERSION")),
		strings.TrimSpace(os.Getenv("IMAGE_VERSION")),
	)
	configProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(configProvider)
	if err != nil {
		log.Fatalf("%s access token config invalid: %v", serviceName, err)
	}
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		serviceName,
		[]string{"user.account.security.read"},
	)
	if err != nil {
		log.Fatalf("%s account security authority credential init failed: %v", serviceName, err)
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
		log.Fatalf("%s account security authority config invalid: %v", serviceName, err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("%s access token verifier invalid: %v", serviceName, err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(configProvider)
	if err != nil {
		log.Fatalf("%s device ticket config invalid: %v", serviceName, err)
	}
	deviceVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		log.Fatalf("%s device ticket verifier invalid: %v", serviceName, err)
	}

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: serviceName, SamplingRatio: 0.1})
	defer otelShutdown()

	built, err := searchbackend.Build(cfg.ES)
	if err != nil {
		log.Fatalf("%s backend assembly failed: %v", serviceName, err)
	}
	if err := built.EnsureIndex(ctx); err != nil {
		if errors.Is(err, searchruntimees.ErrIndexSchemaIncompatible) {
			log.Fatalf("%s search index schema migration failed: %v", serviceName, err)
		}
		log.Fatalf("%s search index initialization failed: %v", serviceName, err)
	}

	logger := slog.Default()
	metricsRecorder := searchmetrics.NewRecorder()
	redisRouter, messageTransportSceneModes := buildRedisRouter(cfg)
	defer redisRouter.Close()
	messageTransport, err := requireSearchAPIMessageTransport(
		ctx,
		appEnv,
		redisRouter,
		messageTransportSceneModes,
	)
	if err != nil {
		log.Fatalf("%s message transport construction failed: %v", serviceName, err)
	}
	if err := redisRouter.PingAll(ctx); err != nil {
		log.Fatalf("%s redis unavailable: %v", serviceName, err)
	}
	searchSignalPublisher, err := searchsignals.NewStreamPublisher(messageTransport, logger)
	if err != nil {
		log.Fatalf("%s search signal publisher init failed: %v", serviceName, err)
	}

	// Mongo is authoritative for query logs, feedback facts, term heat,
	// RecentSearchState, and privacy cleanup checkpoints. Every environment uses
	// the same complete production composition.
	var feedbackSink feedbackapplication.Sink
	var termHeat application.TermHeatProvider
	var queryLogSink application.QueryLogSink
	var recentFacade *recentsearch.Facade
	var accountClosureConsumer *mqadapter.UserAccountClosedConsumer
	var feedbackSignalRelay *feedbackstore.SignalRelay
	if strings.TrimSpace(cfg.Mongo.URI) == "" {
		log.Fatalf("%s mongo.uri is required", serviceName)
	}
	{
		client := rtmongodb.MustConnect(ctx, rtmongodb.ConnectConfig{
			URI: cfg.Mongo.URI, Database: cfg.Mongo.Database,
		}, serviceName)
		db := client.Database(cfg.Mongo.Database)
		feedbackStore := feedbackstore.NewStore(db)
		queryStore := querylogstore.NewStore(db)
		indexCtx, indexCancel := context.WithTimeout(ctx, 30*time.Second)
		if err := feedbackStore.EnsureIndexes(indexCtx); err != nil {
			indexCancel()
			log.Fatalf("%s search feedback index initialization failed: %v", serviceName, err)
		}
		if err := queryStore.EnsureIndexes(indexCtx); err != nil {
			indexCancel()
			log.Fatalf("%s search query index initialization failed: %v", serviceName, err)
		}
		indexCancel()
		feedbackSink = feedbackStore
		feedbackSignalRelay, err = feedbackstore.NewSignalRelay(
			feedbackStore,
			searchSignalPublisher,
			metricsRecorder,
			logger,
		)
		if err != nil {
			log.Fatalf(
				"%s feedback signal relay init failed: %v",
				serviceName,
				err,
			)
		}
		go feedbackSignalRelay.Run(ctx)
		queryLogSink = queryStore
		heatStore := queryheatstore.NewStore(db, queryheat.Config{}, logger)
		// Hot-query related-terms cache: collapses the per-search Mongo read for
		// repeated hot queries into one read per key per TTL window (backpressure
		// on the Mongo side under concurrency). Best-effort, read-through.
		termHeat = application.NewCachedTermHeat(heatStore,
			time.Duration(getenvInt("SEARCH_RELATED_TERMS_CACHE_TTL_MS", 2000))*time.Millisecond,
			getenvInt("SEARCH_RELATED_TERMS_CACHE_MAX", 1024),
			metricsRecorder)
		startHeatRebuildLoop(ctx, heatStore, logger)
		recentStore := recentsearchstore.NewStore(db)
		if err := recentStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf(
				"%s recent search index initialization failed: %v",
				serviceName,
				err,
			)
		}
		recentFacade, err = recentsearch.NewFacade(recentStore)
		if err != nil {
			log.Fatalf("%s recent search facade init failed: %v", serviceName, err)
		}
		accountClosureProjection, err := accountclosureinfra.NewMongoProjection(db)
		if err != nil {
			log.Fatalf(
				"%s UserAccountClosed projection init failed: %v",
				serviceName,
				err,
			)
		}
		if err := accountClosureProjection.EnsureIndexes(ctx); err != nil {
			log.Fatalf(
				"%s UserAccountClosed projection indexes failed: %v",
				serviceName,
				err,
			)
		}
		accountClosureConsumer, err = mqadapter.NewUserAccountClosedConsumer(
			messageTransport,
			accountClosureProjection,
			accountClosureProjection,
			serviceName+"-"+hostname(),
			logger,
			mqadapter.DefaultUserAccountClosedConsumerConfig(),
		)
		if err != nil {
			log.Fatalf(
				"%s UserAccountClosed consumer init failed: %v",
				serviceName,
				err,
			)
		}
		if err := accountClosureConsumer.EnsureGroup(ctx); err != nil {
			log.Fatalf(
				"%s UserAccountClosed consumer group init failed: %v",
				serviceName,
				err,
			)
		}
		go accountClosureConsumer.Run(ctx)
		log.Printf("%s feedback/query-log + term-heat + recent-search enabled (db=%s)", serviceName, cfg.Mongo.Database)
	}

	searchSvc := application.NewSearchService(built.Backend,
		application.WithQueryLogSink(queryLogSink),
		application.WithSearchSignalPublisher(searchSignalPublisher),
		application.WithLogger(logger))
	feedbackSvc := feedbackapplication.NewService(feedbackSink)
	decorator := application.NewRankingDecorator(termHeat, application.NewExperiments(experimentConfig(cfg)), cfg.Ranking.TermHeatBoost, logger)
	contentBaseURL := strings.TrimSpace(cfg.ContentService.BaseURL)
	if override, ok := configProvider.GetString("CONTENT_SERVICE_BASE_URL"); ok {
		contentBaseURL = override
	}
	contentAuthorization, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		serviceName,
		[]string{"content.object_intersections.read"},
	)
	if err != nil {
		log.Fatalf("%s content intersection credential init failed: %v", serviceName, err)
	}
	intersectionReader, err := intersectionclient.New(intersectionclient.Config{
		BaseURL:       contentBaseURL,
		Authorization: contentAuthorization,
	})
	if err != nil {
		log.Fatalf("%s content intersection reader init failed: %v", serviceName, err)
	}
	intersectionAttacher := application.NewIntersectionAttacher(
		intersectionReader,
		application.IntersectionAttacherConfig{
			Timeout:       300 * time.Millisecond,
			MaxHits:       8,
			MaxConcurrent: 4,
			ReasonLimit:   1,
		},
		logger,
		metricsRecorder,
	)

	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("%s runtime log exporter init failed: %v", serviceName, err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, robs.TraceLogLevelInfo, nil)
	if err != nil {
		log.Fatalf("%s process logger init failed: %v", serviceName, err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		log.Fatalf("%s exception logger init failed: %v", serviceName, err)
	}

	routesMux := http.NewServeMux()
	httpadapter.NewHandlerWithConfig(
		searchSvc,
		decorator,
		metricsRecorder,
		httpadapter.HandlerConfig{
			HotQueries:    termHeat,
			Intersections: intersectionAttacher,
		},
	).Register(routesMux)
	feedbackhttp.NewHandler(feedbackSvc, metricsRecorder).Register(routesMux)
	if recentFacade != nil {
		recenthttp.NewRecentSearchHandler(recentFacade, metricsRecorder).Register(routesMux)
	}
	var handler http.Handler = routesMux
	// Backpressure: cap concurrent in-flight searches so a slow ES sheds load
	// (typed 503) instead of piling up and collapsing the instance. Aligned with
	// search_slo.yaml#load_model.max_concurrency_per_instance; applied only to the
	// search routes so /healthz and /metrics stay reachable while shedding.
	inflightLimiter := rtgov.NewInflightLimiter(getenvInt("SEARCH_MAX_INFLIGHT", 256))
	searchHandler := httpadapter.MaxInflightMiddleware(inflightLimiter, metricsRecorder)(handler)
	if accountClosureConsumer != nil {
		searchHandler, err = runtimemessaging.WithDeadLetterRecoveryRoute(
			searchHandler,
			runtimemessaging.DeadLetterRecoveryRouteConfig{
				Path:     "/internal/search/account-closure/dead-letters:recover",
				Module:   rterr.ModuleSearch,
				Releaser: accountClosureConsumer,
			},
		)
		if err != nil {
			log.Fatalf("%s account-closure recovery route failed: %v", serviceName, err)
		}
	}
	rootMux := http.NewServeMux()
	healthChecker := rthealth.NewChecker()
	healthChecker.Register("account-security-authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	if ping := built.HealthPing(); ping != nil {
		healthChecker.Register("elasticsearch", ping)
	}
	if feedbackSignalRelay != nil {
		healthChecker.Register(
			"feedback-signal-relay",
			func(hctx context.Context) error {
				return feedbackSignalRelay.Healthy(
					hctx,
					15*time.Second,
				)
			},
		)
	}
	if accountClosureConsumer != nil {
		healthChecker.Register(
			"user-account-closed-consumer",
			func(context.Context) error {
				return accountClosureConsumer.Healthy(15 * time.Second)
			},
		)
	}
	rootMux.HandleFunc("/healthz", healthChecker.Handler())
	rootMux.Handle("/metrics", rtmetrics.Handler())
	rootMux.Handle(
		"/",
		generatedSearchOperationHandler(searchHandler),
	)

	serverCfg := rthttp.HTTPServerMiddlewareConfig{
		Service:           serviceName,
		Origin:            "cloud",
		Direction:         "inbound",
		SourceID:          serviceName + ".http",
		Src:               "gateway",
		ServiceName:       serviceName,
		ServiceInstanceID: hostname(),
	}
	withObs := rthttp.NewHTTPServerMiddleware(rootMux, serverCfg, ioLogger, processLogger, exceptionLogger)
	rateLimited := rtgov.RateLimitMiddleware(rtgov.NewRateLimiter(1000))(withObs)

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
	log.Printf("%s listening on %s (es.enabled=%t)", serviceName, cfg.Service.HTTP.Addr, cfg.ES.Enabled)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("%s: %v", serviceName, err)
	}
}

func generatedSearchOperationHandler(next http.Handler) http.Handler {
	return rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("search"),
	)(next)
}

func loadRuntimeConfig() (config, error) {
	cfg := config{}
	serviceName := getenvOrDefault("SERVICE_NAME", "search-service")
	appEnv := getenvOrDefault("APP_ENV", "alpha")
	configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	configVersion := strings.TrimSpace(os.Getenv("CONFIG_VERSION"))
	if !isValidAppEnv(appEnv) {
		return config{}, fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	if requiresConfigVersion(appEnv) && configVersion == "" {
		return config{}, fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	path, err := configrelease.File(configRoot, serviceName, appEnv)
	if err != nil {
		return config{}, err
	}
	if err := mergeConfigFile(&cfg, path); err != nil {
		return config{}, fmt.Errorf("read generated runtime config: %w", err)
	}
	return cfg, nil
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

func normalizeDefaults(cfg *config) {
	if strings.TrimSpace(cfg.Service.Name) == "" {
		cfg.Service.Name = serviceName
	}
	if strings.TrimSpace(cfg.Service.HTTP.Addr) == "" {
		cfg.Service.HTTP.Addr = ":18095"
	}
	if strings.TrimSpace(cfg.ES.Index) == "" {
		cfg.ES.Index = "quwoquan_objects"
	}
}

// applyESEnvOverrides lets the deploy layer inject ES endpoints/credentials as
// environment secrets (consistent with how other services inject *_URI), without
// hardcoding them in committed config.
func applyESEnvOverrides(es *searchbackend.ESConfig) {
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_ENDPOINTS")); v != "" {
		parts := strings.Split(v, ",")
		eps := make([]string, 0, len(parts))
		for _, p := range parts {
			if p = strings.TrimSpace(p); p != "" {
				eps = append(eps, p)
			}
		}
		es.Endpoints = eps
		es.Enabled = true
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_USERNAME")); v != "" {
		es.Username = v
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_PASSWORD")); v != "" {
		es.Password = v
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_ES_API_KEY")); v != "" {
		es.APIKey = v
	}
	switch strings.ToLower(strings.TrimSpace(os.Getenv("SEARCH_ES_ENABLED"))) {
	case "true", "1":
		es.Enabled = true
	case "false", "0":
		es.Enabled = false
	}
}

// applyMongoEnvOverrides lets the deploy layer inject the Mongo endpoint as an
// environment secret (consistent with how *_URI are injected elsewhere).
func applyMongoEnvOverrides(cfg *config) {
	if v := strings.TrimSpace(os.Getenv("SEARCH_MONGO_URI")); v != "" {
		cfg.Mongo.URI = v
	}
	if v := strings.TrimSpace(os.Getenv("SEARCH_MONGO_DATABASE")); v != "" {
		cfg.Mongo.Database = v
	}
	if strings.TrimSpace(cfg.Mongo.URI) != "" && strings.TrimSpace(cfg.Mongo.Database) == "" {
		cfg.Mongo.Database = "quwoquan"
	}
}

func applyRedisEnvOverrides(cfg *config) {
	applyRedisSceneEnv("SEARCH_REDIS_GENERAL", &cfg.Redis.General)
	applyRedisSceneEnv("SEARCH_REDIS_REC", &cfg.Redis.Rec)
}

type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`
	Pool     struct {
		Size           int `yaml:"size"`
		MinIdle        int `yaml:"min_idle"`
		ReadTimeoutMs  int `yaml:"read_timeout_ms"`
		WriteTimeoutMs int `yaml:"write_timeout_ms"`
		DialTimeoutMs  int `yaml:"dial_timeout_ms"`
	} `yaml:"pool"`
}

func applyRedisSceneEnv(prefix string, cfg *redisSceneCfg) {
	if v := strings.TrimSpace(os.Getenv(prefix + "_MODE")); v != "" {
		cfg.Mode = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_ADDR")); v != "" {
		cfg.Addr = v
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_ADDRS")); v != "" {
		cfg.Addrs = strings.Split(v, ",")
	}
	if v := strings.TrimSpace(os.Getenv(prefix + "_PASSWORD")); v != "" {
		cfg.Password = v
	}
	switch strings.ToLower(strings.TrimSpace(os.Getenv(prefix + "_TLS"))) {
	case "true", "1", "yes", "on":
		cfg.TLS = true
	}
}

func buildRedisRouter(cfg config) (*rtredis.Router, map[string]string) {
	base := rtredis.DefaultRouterConfig()
	generalScene := toSceneConfig(cfg.Redis.General)
	base.Scenes["general"] = generalScene
	base.Scenes["rec"] = toSceneConfig(cfg.Redis.Rec)
	return platformredis.MustNewRouter(base), map[string]string{
		"general": generalScene.Mode,
	}
}

func toSceneConfig(cfg redisSceneCfg) rtredis.SceneConfig {
	return rtredis.SceneConfig{
		Mode:           cfg.Mode,
		Addr:           cfg.Addr,
		Addrs:          cfg.Addrs,
		Password:       cfg.Password,
		DB:             cfg.DB,
		TLS:            cfg.TLS,
		PoolSize:       cfg.Pool.Size,
		MinIdleConns:   cfg.Pool.MinIdle,
		ReadTimeoutMs:  cfg.Pool.ReadTimeoutMs,
		WriteTimeoutMs: cfg.Pool.WriteTimeoutMs,
		DialTimeoutMs:  cfg.Pool.DialTimeoutMs,
	}
}

// experimentConfig maps the service config AB block into the application config.
func experimentConfig(cfg config) application.ExperimentConfig {
	out := application.ExperimentConfig{
		Enabled:       cfg.Ranking.Experiment.Enabled,
		PolicyVersion: cfg.Ranking.Experiment.PolicyVersion,
	}
	for _, b := range cfg.Ranking.Experiment.Buckets {
		out.Buckets = append(out.Buckets, application.ExperimentBucket{Name: b.Name, WeightPct: b.WeightPct})
	}
	return out
}

// startHeatRebuildLoop rebuilds the search-term heat read model on a ticker and
// once at startup, both best-effort. It stops when ctx is canceled (graceful
// shutdown), so it never leaks past the server lifetime.
func startHeatRebuildLoop(ctx context.Context, store *queryheatstore.Store, logger *slog.Logger) {
	rebuild := func() {
		runCtx, cancel := context.WithTimeout(ctx, 2*time.Minute)
		defer cancel()
		written, err := store.Rebuild(runCtx)
		if err != nil {
			logger.WarnContext(runCtx, "search term-heat rebuild failed (best-effort)", slog.String("err", err.Error()))
			return
		}
		logger.InfoContext(runCtx, "search term-heat rebuilt", slog.Int("terms", written))
	}
	go func() {
		rebuild()
		ticker := time.NewTicker(heatRebuildInterval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				rebuild()
			}
		}
	}()
}

func getenvOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

// getenvInt reads a positive integer env override, falling back to def when the
// var is unset or not a positive integer (so a bad value never disables the cap).
func getenvInt(key string, def int) int {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			return n
		}
	}
	return def
}

func hostname() string {
	name, err := os.Hostname()
	if err != nil || strings.TrimSpace(name) == "" {
		return "local"
	}
	return name
}
