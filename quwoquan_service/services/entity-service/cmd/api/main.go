package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	configrelease "quwoquan_service/runtime/configrelease"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
	rtmongo "quwoquan_service/internal/platform/mongodb"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	httpadapter "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/adapters/inbound/http"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/accountsecurity"
	homepageexternal "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/external"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/followconsumer"
	entitymessaging "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/messaging"
	entityguard "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/operationguard"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/searchindex"
	claimapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/application"
	claimpersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/infrastructure/persistence"
	reviewapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/application"
	reviewpersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/infrastructure/persistence"
	statusapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/application"
	statuspersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/infrastructure/persistence"
)

type config struct {
	Service struct {
		Name string `yaml:"name"`
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`

	Mongo struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongo"`

	Redis struct {
		Addr     string `yaml:"addr"`
		Password string `yaml:"password"`
		DB       int    `yaml:"db"`
	} `yaml:"redis"`

	ES searchindex.ESConfig `yaml:"es"`

	ContentService struct {
		BaseURL                 string `yaml:"base_url"`
		ObjectIntersectionsPath string `yaml:"object_intersections_path"`
	} `yaml:"content_service"`

	UserAccountSecurityAuthority struct {
		BaseURL   string `yaml:"base_url"`
		TimeoutMS int    `yaml:"timeout_ms"`
	} `yaml:"user_account_security_authority"`
}

func main() {
	cfg, err := loadRuntimeConfig()
	if err != nil {
		log.Fatalf("entity-service config load failed: %v", err)
	}
	normalizeDefaults(&cfg)

	ctx := context.Background()

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "entity-service", SamplingRatio: 0.1})
	defer otelShutdown()

	appEnv := getenvOrDefault("APP_ENV", "alpha")
	messageTransportRouter, messageTransportSceneModes, err := buildEntityMessageTransportRouter(
		appEnv,
		cfg,
	)
	if err != nil {
		log.Fatalf("entity-service message transport Redis config invalid: %v", err)
	}
	defer messageTransportRouter.Close()
	messageTransport, err := requireEntityAPIMessageTransport(
		ctx,
		appEnv,
		messageTransportRouter,
		messageTransportSceneModes,
	)
	if err != nil {
		log.Fatalf("entity-service message transport preflight failed: %v", err)
	}
	var homepageStore application.HomepageDataStore
	var mongoPing func(context.Context) error
	var reviewStore *reviewpersistence.MongoReviewStore
	var claimStore *claimpersistence.MongoStore
	var statusReportStore *statuspersistence.MongoStore
	mongoURI := getenvOrDefault("ENTITY_MONGO_URI", cfg.Mongo.URI)
	if mongoURI == "" {
		// production composition 在所有环境都只装配权威存储；alpha fixture
		// 由独立 runner/test composition 注入，禁止服务入口回退内存实现。
		log.Fatalf("entity-service requires ENTITY_MONGO_URI when APP_ENV=%s", appEnv)
	}
	if mongoURI != "" {
		mongoDBName := getenvOrDefault("ENTITY_MONGO_DATABASE", cfg.Mongo.Database)
		if mongoDBName == "" {
			mongoDBName = "quwoquan_entity"
		}
		mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: mongoURI}, "entity-service")
		mongoDatabase := mongoClient.Database(mongoDBName)
		mongoHomepageStore := homepagepersistence.NewMongoHomepageStore(
			mongoDatabase,
			appEnv != "alpha",
		)
		if err := mongoHomepageStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("entity-service homepage indexes failed: %v", err)
		}
		homepageStore = mongoHomepageStore
		reviewStore = reviewpersistence.NewMongoReviewStore(mongoDatabase, appEnv != "alpha")
		if err := reviewStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("entity-service homepage review indexes failed: %v", err)
		}
		claimStore = claimpersistence.NewMongoStore(mongoDatabase, appEnv != "alpha")
		if err := claimStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("entity-service homepage claim indexes failed: %v", err)
		}
		statusReportStore = statuspersistence.NewMongoStore(mongoDatabase, appEnv != "alpha")
		if err := statusReportStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("entity-service homepage status report indexes failed: %v", err)
		}
		mongoPing = func(hctx context.Context) error {
			return mongoClient.Ping(hctx, nil)
		}
		defer mongoClient.Disconnect(ctx)
	}
	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("entity-service runtime log exporter init failed: %v", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, robs.TraceLogLevelInfo, nil)
	if err != nil {
		log.Fatalf("entity-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		log.Fatalf("entity-service exception logger init failed: %v", err)
	}

	// Assemble the write-time search index. ES endpoints/credentials come from the
	// shared SEARCH_ES_* env (same cluster/index as search-service); when ES is
	// disabled Build returns a no-op Built and the homepage service runs without a
	// projector, so the primary write path is unaffected.
	searchindex.ApplyESEnvOverrides(&cfg.ES)
	searchBuilt, err := searchindex.Build(cfg.ES)
	if err != nil {
		log.Fatalf("entity-service search index build failed: %v", err)
	}
	if err := searchBuilt.EnsureIndex(ctx); err != nil {
		// SearchIndexView is a derived projection. Keep Homepage commands
		// available during a transient ES outage and surface the dependency via
		// healthz; projector/backfill repairs the projection after recovery.
		log.Printf("WARN: entity-service search index ensure failed: %v", err)
	}

	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("entity-service access token config invalid: %v", err)
	}
	accountSecurityAuthorityBaseURL := getenvOrDefault(
		"ENTITY_USER_ACCOUNT_SECURITY_AUTHORITY_BASE_URL",
		cfg.UserAccountSecurityAuthority.BaseURL,
	)
	accountSecurityAuthority, err := accountsecurity.NewAuthority(
		accessTokenConfig,
		accountsecurity.Config{
			BaseURL:   accountSecurityAuthorityBaseURL,
			TimeoutMS: cfg.UserAccountSecurityAuthority.TimeoutMS,
		},
	)
	if err != nil {
		log.Fatalf("entity-service account security authority init failed: %v", err)
	}

	var serviceOpts []application.HomepageServiceOption
	if searchBuilt.Projector != nil {
		serviceOpts = append(serviceOpts, application.WithProjector(searchBuilt.Projector))
	}
	contentBaseURL := getenvOrDefault("CONTENT_SERVICE_BASE_URL", cfg.ContentService.BaseURL)
	contentIntersectionsPath := getenvOrDefault(
		"CONTENT_SERVICE_OBJECT_INTERSECTIONS_PATH",
		cfg.ContentService.ObjectIntersectionsPath,
	)
	if contentBaseURL != "" {
		contentCredentials, credentialErr :=
			rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
				accessTokenConfig,
				"entity-service",
				[]string{"content.object_intersections.read"},
			)
		if credentialErr != nil {
			log.Fatalf("entity-service content credential init failed: %v", credentialErr)
		}
		intersectionReader, readerErr := homepageexternal.NewContentIntersectionReader(
			homepageexternal.ContentIntersectionConfig{
				BaseURL:                 contentBaseURL,
				ObjectIntersectionsPath: contentIntersectionsPath,
				Authorization:           contentCredentials,
			},
		)
		if readerErr != nil {
			log.Fatalf("entity-service content intersection reader failed: %v", readerErr)
		}
		serviceOpts = append(serviceOpts, application.WithIntersectionReader(intersectionReader))
	}
	homepageService := application.NewHomepageServiceWithStore(ctx, homepageStore, serviceOpts...)
	projectionRunners := []namedProjectionRunner{}
	if searchBuilt.Projector != nil {
		searchRelay, relayErr := application.NewHomepageSearchRelay(
			homepageStore,
			searchBuilt.Projector,
		)
		if relayErr != nil {
			log.Fatalf("entity-service homepage search relay failed: %v", relayErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-search", runner: searchRelay,
		})
	}
	if claimStore != nil {
		claimFacade, facadeErr := claimapp.NewFacade(claimapp.DataPorts{
			Aggregates: claimStore,
			Receipts:   claimStore,
			Homepages:  homepageService,
			Queue:      claimStore,
		})
		if facadeErr != nil {
			log.Fatalf("entity-service homepage claim facade failed: %v", facadeErr)
		}
		homepageService.SetClaimFacade(claimFacade)
		claimProjector, projectorErr := application.NewClaimHomepageProjector(
			claimStore,
			homepageService,
		)
		if projectorErr != nil {
			log.Fatalf("entity-service homepage claim projector failed: %v", projectorErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-claim", runner: claimProjector,
		})
	}
	if statusReportStore != nil {
		statusFacade, facadeErr := statusapp.NewFacade(statusapp.DataPorts{
			Aggregates: statusReportStore,
			Receipts:   statusReportStore,
			Homepages:  homepageService,
			Queue:      statusReportStore,
		})
		if facadeErr != nil {
			log.Fatalf("entity-service homepage status report facade failed: %v", facadeErr)
		}
		homepageService.SetStatusReportFacade(statusFacade)
		statusProjector, projectorErr := application.NewStatusHomepageProjector(
			statusReportStore,
			homepageService,
		)
		if projectorErr != nil {
			log.Fatalf("entity-service homepage status projector failed: %v", projectorErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-status", runner: statusProjector,
		})
	}

	// SubjectFollowStateChanged 消费：homepage 关注真相源在 user.SubjectFollow，
	// 本服务只投影 viewerFollowsHomepage / followerCount。启动前已将 generated
	// runtime.message.transport root 解析为唯一的生产消息 transport。
	followConsumer := followconsumer.NewConsumer(
		messageTransport,
		homepageService,
		hostname(),
	)
	go followConsumer.Run(ctx)
	homepageStreamRelay, relayErr := homepageapp.NewLifecycleOutboxRelay(
		homepageStore,
		entitymessaging.NewHomepageLifecycleStreamPublisher(messageTransport),
	)
	if relayErr != nil {
		log.Fatalf("entity-service homepage lifecycle stream relay failed: %v", relayErr)
	}
	projectionRunners = append(projectionRunners, namedProjectionRunner{
		name: "homepage-lifecycle-stream", runner: homepageStreamRelay,
	})
	if claimStore != nil {
		claimStreamRelay, streamErr := claimapp.NewLifecycleOutboxRelay(
			claimStore,
			entitymessaging.NewHomepageClaimLifecycleStreamPublisher(messageTransport),
		)
		if streamErr != nil {
			log.Fatalf("entity-service claim lifecycle stream relay failed: %v", streamErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-claim-lifecycle-stream", runner: claimStreamRelay,
		})
	}
	if statusReportStore != nil {
		statusStreamRelay, streamErr := statusapp.NewLifecycleOutboxRelay(
			statusReportStore,
			entitymessaging.NewHomepageStatusLifecycleStreamPublisher(messageTransport),
		)
		if streamErr != nil {
			log.Fatalf("entity-service status lifecycle stream relay failed: %v", streamErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-status-lifecycle-stream", runner: statusStreamRelay,
		})
	}
	log.Printf("entity-service subject follow consumer enabled")
	httpHandler := httpadapter.NewHandler(homepageService)
	if reviewStore != nil {
		reviewFacade, err := reviewapp.NewFacade(reviewapp.DataPorts{
			Aggregate: reviewStore,
			Page:      reviewStore,
			Homepage:  homepageService,
		})
		if err != nil {
			log.Fatalf("entity-service homepage review facade failed: %v", err)
		}
		httpHandler = httpHandler.WithReviewFacade(reviewFacade)
		reviewRelay, relayErr := reviewapp.NewSummaryRelay(
			reviewStore,
			reviewStore,
			reviewStore,
			homepageService,
		)
		if relayErr != nil {
			log.Fatalf("entity-service homepage review summary relay failed: %v", relayErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-review-summary", runner: reviewRelay,
		})
	}
	for _, runner := range projectionRunners {
		go runProjectionLoop(ctx, runner)
	}
	handler := httpHandler.Routes()
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("entity-service access token verifier invalid: %v", err)
	}
	rootMux := http.NewServeMux()
	healthChecker := rthealth.NewChecker()
	if ping := searchBuilt.HealthPing(); ping != nil {
		healthChecker.Register("elasticsearch", ping)
	}
	if mongoPing != nil {
		healthChecker.Register("mongodb", mongoPing)
	}
	healthChecker.Register(
		"account_security_authority",
		accountSecurityAuthority.CheckAccountSecurityAuthority,
	)
	rootMux.HandleFunc("/healthz", healthChecker.Handler())
	rootMux.Handle("/metrics", rtmetrics.Handler())
	rootMux.Handle("/", entityguard.Handler(handler))
	serverCfg := rthttp.HTTPServerMiddlewareConfig{
		Service:           "entity-service",
		Origin:            "cloud",
		Direction:         "inbound",
		SourceID:          "entity-service.http",
		Src:               "gateway",
		ServiceName:       "entity-service",
		ServiceInstanceID: hostname(),
	}
	withObs := rthttp.NewHTTPServerMiddleware(rootMux, serverCfg, ioLogger, processLogger, exceptionLogger)

	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(withObs)

	addr := getenvOrDefault("ENTITY_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(rateLimited),
		BaseContext:       func(_ net.Listener) context.Context { return ctx },
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("entity-service listening on %s", addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("entity-service: %v", err)
	}
}

type projectionRunner interface {
	RunOnce(ctx context.Context, limit int) (int, error)
}

type namedProjectionRunner struct {
	name   string
	runner projectionRunner
}

func runProjectionLoop(ctx context.Context, named namedProjectionRunner) {
	const (
		interval  = 2 * time.Second
		batchSize = 100
	)
	run := func() {
		if _, err := named.runner.RunOnce(ctx, batchSize); err != nil && ctx.Err() == nil {
			log.Printf("entity-service projection %s failed: %v", named.name, err)
		}
	}
	run()
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			run()
		}
	}
}

func loadRuntimeConfig() (config, error) {
	cfg := config{}
	serviceName := getenvOrDefault("SERVICE_NAME", "entity-service")
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
		cfg.Service.Name = "entity-service"
	}
	if strings.TrimSpace(cfg.Service.HTTP.Addr) == "" {
		cfg.Service.HTTP.Addr = ":18084"
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
		return "local"
	}
	return name
}
