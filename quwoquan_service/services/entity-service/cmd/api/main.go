package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
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
	entitycomposition "quwoquan_service/services/entity-service/cmd/internal/composition"
	httpadapter "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/adapters/inbound/http"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/accountsecurity"
	homepageexternal "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/external"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/followconsumer"
	entitymessaging "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/messaging"
	entityguard "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/operationguard"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
	claimhttp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/adapters/inbound/http"
	claimapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/application"
	claimpersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/infrastructure/persistence"
	reviewhttp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/adapters/inbound/http"
	reviewapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/application"
	reviewmessaging "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/infrastructure/messaging"
	reviewpersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/infrastructure/persistence"
	searchitempersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/infrastructure/persistence"
	searchitemindex "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/infrastructure/searchindex"
	statushttp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/adapters/inbound/http"
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

	ES searchitemindex.ESConfig `yaml:"es"`

	ContentService struct {
		BaseURL                 string `yaml:"base_url"`
		ObjectIntersectionsPath string `yaml:"object_intersections_path"`
	} `yaml:"content_service"`

	UserAccountSecurityAuthority struct {
		BaseURL   string `yaml:"base_url"`
		TimeoutMS int    `yaml:"timeout_ms"`
	} `yaml:"user_account_security_authority"`
}

// Module is entity-service's service-owned servicehost adapter.
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
	runContext   context.Context
}

var _ servicehost.Module = (*Module)(nil)

// NewModule assembles entity-service's private dependencies and HTTP contract.
// The process host owns binding, worker lifetime, readiness admission and
// shutdown; this constructor returns every fail-fast composition error.
func NewModule() (_ *Module, resultErr error) {
	cleanup := func() {}
	initialized := false
	defer func() {
		if !initialized {
			cleanup()
		}
	}()

	cfg, err := loadRuntimeConfig()
	if err != nil {
		return nil, fmt.Errorf("entity-service config load failed: %w", err)
	}
	normalizeDefaults(&cfg)
	controlplane.StartReleaseConfigAttestation(
		"entity-service",
		getenvOrDefault("APP_ENV", "alpha"),
		strings.TrimSpace(os.Getenv("CONFIG_ROOT")),
		strings.TrimSpace(
			servicehost.ModuleEnvironmentValue("entity-service", "CONFIG_VERSION"),
		),
		strings.TrimSpace(os.Getenv("IMAGE_VERSION")),
	)

	ctx := context.Background()

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "entity-service", SamplingRatio: 0.1})
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		otelShutdown()
	})

	appEnv := getenvOrDefault("APP_ENV", "alpha")
	messageTransportRouter, messageTransportSceneModes, err := buildEntityMessageTransportRouter(
		appEnv,
		cfg,
	)
	if err != nil {
		return nil, fmt.Errorf("entity-service message transport Redis config invalid: %w", err)
	}
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		_ = messageTransportRouter.Close()
	})
	messageTransport, err := requireEntityAPIMessageTransport(
		ctx,
		appEnv,
		messageTransportRouter,
		messageTransportSceneModes,
	)
	if err != nil {
		return nil, fmt.Errorf("entity-service message transport preflight failed: %w", err)
	}
	var homepageStore application.HomepageDataStore
	var mongoPing func(context.Context) error
	var reviewStore *reviewpersistence.MongoReviewStore
	var claimStore *claimpersistence.MongoStore
	var statusReportStore *statuspersistence.MongoStore
	var mongoDatabase *mongo.Database
	mongoURI := getenvOrDefault("ENTITY_MONGO_URI", cfg.Mongo.URI)
	if mongoURI == "" {
		// production composition 在所有环境都只装配权威存储；alpha fixture
		// 由独立 runner/test composition 注入，禁止服务入口回退内存实现。
		return nil, fmt.Errorf("entity-service requires ENTITY_MONGO_URI when APP_ENV=%s", appEnv)
	}
	if mongoURI != "" {
		mongoDBName := getenvOrDefault("ENTITY_MONGO_DATABASE", cfg.Mongo.Database)
		if mongoDBName == "" {
			mongoDBName = "quwoquan_entity"
		}
		mongoClient, connectErr := rtmongo.Connect(ctx, rtmongo.ConnectConfig{URI: mongoURI})
		if connectErr != nil {
			return nil, fmt.Errorf("entity-service mongo connect failed: %w", connectErr)
		}
		cleanup = servicehost.ChainCleanup(cleanup, func() {
			_ = mongoClient.Disconnect(context.Background())
		})
		mongoDatabase = mongoClient.Database(mongoDBName)
		mongoHomepageStore := homepagepersistence.NewMongoHomepageStore(mongoDatabase)
		if err := mongoHomepageStore.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf("entity-service homepage indexes failed: %w", err)
		}
		homepageStore = mongoHomepageStore
		reviewStore = reviewpersistence.NewMongoReviewStore(mongoDatabase)
		if err := reviewStore.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf("entity-service homepage review indexes failed: %w", err)
		}
		claimStore = claimpersistence.NewMongoStore(mongoDatabase)
		if err := claimStore.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf("entity-service homepage claim indexes failed: %w", err)
		}
		statusReportStore = statuspersistence.NewMongoStore(mongoDatabase)
		if err := statusReportStore.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf("entity-service homepage status report indexes failed: %w", err)
		}
		mongoPing = func(hctx context.Context) error {
			return mongoClient.Ping(hctx, nil)
		}
	}
	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		return nil, fmt.Errorf("entity-service runtime log exporter init failed: %w", err)
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
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, robs.TraceLogLevelInfo, nil)
	if err != nil {
		return nil, fmt.Errorf("entity-service process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		return nil, fmt.Errorf("entity-service exception logger init failed: %w", err)
	}

	// Assemble the write-time search index. ES endpoints/credentials come from the
	// shared SEARCH_ES_* env (same cluster/index as search-service); when ES is
	// disabled Build returns a no-op Built and the homepage service runs without a
	// projector, so the primary write path is unaffected.
	searchitemindex.ApplyESEnvOverrides(&cfg.ES)
	searchBuilt, err := searchitemindex.Build(cfg.ES)
	if err != nil {
		return nil, fmt.Errorf("entity-service search index build failed: %w", err)
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
		return nil, fmt.Errorf("entity-service access token config invalid: %w", err)
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
		return nil, fmt.Errorf("entity-service account security authority init failed: %w", err)
	}

	var serviceOpts []application.HomepageServiceOption
	var searchItemProjection application.Projector
	if searchBuilt.Indexer != nil {
		searchItemIndex := searchitempersistence.NewESIndex(searchBuilt.Indexer, mongoDatabase)
		if err := searchItemIndex.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf("entity-service homepage search item indexes failed: %w", err)
		}
		searchItemProjection = entitycomposition.NewHomepageSearchItemProjection(searchItemIndex)
		serviceOpts = append(serviceOpts, application.WithProjector(searchItemProjection))
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
			return nil, fmt.Errorf("entity-service content credential init failed: %w", credentialErr)
		}
		intersectionReader, readerErr := homepageexternal.NewContentIntersectionReader(
			homepageexternal.ContentIntersectionConfig{
				BaseURL:                 contentBaseURL,
				ObjectIntersectionsPath: contentIntersectionsPath,
				Authorization:           contentCredentials,
			},
		)
		if readerErr != nil {
			return nil, fmt.Errorf("entity-service content intersection reader failed: %w", readerErr)
		}
		serviceOpts = append(serviceOpts, application.WithIntersectionReader(intersectionReader))
	}
	homepageService := application.NewHomepageServiceWithStore(ctx, homepageStore, serviceOpts...)
	homepageLifecycleHandler := application.NewHomepageLifecycleHandler(homepageService)
	projectionRunners := []namedProjectionRunner{}
	var claimFacade *claimapp.Facade
	var statusFacade *statusapp.Facade
	if searchItemProjection != nil {
		searchRelay, relayErr := application.NewHomepageSearchRelay(
			homepageStore,
			searchItemProjection,
		)
		if relayErr != nil {
			return nil, fmt.Errorf("entity-service homepage search relay failed: %w", relayErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-search", runner: searchRelay,
		})
	}
	if claimStore != nil {
		var facadeErr error
		claimFacade, facadeErr = claimapp.NewFacade(claimapp.DataPorts{
			Aggregates: claimStore,
			Receipts:   claimStore,
			Homepages:  entitycomposition.NewHomepageClaimGate(homepageService),
			Queue:      claimStore,
		})
		if facadeErr != nil {
			return nil, fmt.Errorf("entity-service homepage claim facade failed: %w", facadeErr)
		}
		claimProjector, projectorErr := application.NewClaimHomepageProjector(
			claimStore,
			homepageLifecycleHandler,
		)
		if projectorErr != nil {
			return nil, fmt.Errorf("entity-service homepage claim projector failed: %w", projectorErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-claim", runner: claimProjector,
		})
	}
	if statusReportStore != nil {
		var facadeErr error
		statusFacade, facadeErr = statusapp.NewFacade(statusapp.DataPorts{
			Aggregates: statusReportStore,
			Receipts:   statusReportStore,
			Homepages:  homepageService,
			Queue:      statusReportStore,
		})
		if facadeErr != nil {
			return nil, fmt.Errorf("entity-service homepage status report facade failed: %w", facadeErr)
		}
		statusProjector, projectorErr := application.NewStatusHomepageProjector(
			statusReportStore,
			homepageService,
		)
		if projectorErr != nil {
			return nil, fmt.Errorf("entity-service homepage status projector failed: %w", projectorErr)
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
	homepageStreamRelay, relayErr := homepageapp.NewLifecycleOutboxRelay(
		homepageStore,
		entitymessaging.NewHomepageLifecycleStreamPublisher(messageTransport),
	)
	if relayErr != nil {
		return nil, fmt.Errorf("entity-service homepage lifecycle stream relay failed: %w", relayErr)
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
			return nil, fmt.Errorf("entity-service claim lifecycle stream relay failed: %w", streamErr)
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
			return nil, fmt.Errorf("entity-service status lifecycle stream relay failed: %w", streamErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-status-lifecycle-stream", runner: statusStreamRelay,
		})
	}
	log.Printf("entity-service subject follow consumer enabled")
	homepageHostAuthorityEvaluator, err := homepageapp.NewHostAuthorityEvaluator(
		homepageStore,
		time.Now,
	)
	if err != nil {
		return nil, fmt.Errorf("entity homepage host authority composition failed: %w", err)
	}
	httpHandler := httpadapter.NewHandler(homepageService).
		WithHostAuthorityEvaluator(homepageHostAuthorityEvaluator)
	if claimFacade != nil {
		httpHandler = httpHandler.WithClaimRequestHandler(claimhttp.NewHandler(claimFacade))
	}
	if statusFacade != nil {
		httpHandler = httpHandler.WithStatusReportHandler(statushttp.NewHandler(statusFacade))
	}
	if reviewStore != nil {
		reviewFacade, err := reviewapp.NewFacade(reviewapp.DataPorts{
			Aggregate: reviewStore,
			Page:      reviewStore,
			Homepage:  homepageService,
		})
		if err != nil {
			return nil, fmt.Errorf("entity-service homepage review facade failed: %w", err)
		}
		httpHandler = httpHandler.WithReviewHandler(reviewhttp.NewHandler(reviewFacade))
		reviewRelay, relayErr := reviewapp.NewSummaryRelay(
			reviewStore,
			reviewStore,
			reviewStore,
			homepageLifecycleHandler,
		)
		if relayErr != nil {
			return nil, fmt.Errorf("entity-service homepage review summary relay failed: %w", relayErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-review-summary", runner: reviewRelay,
		})
		reviewPublisher, publisherErr := reviewmessaging.NewEventPublisher(messageTransport)
		if publisherErr != nil {
			return nil, fmt.Errorf("entity-service homepage review event publisher failed: %w", publisherErr)
		}
		reviewStreamRelay, streamErr := reviewapp.NewOutboxRelay(
			reviewStore,
			reviewStore,
			reviewPublisher,
			"entity.homepage-review-event-stream",
		)
		if streamErr != nil {
			return nil, fmt.Errorf("entity-service homepage review stream relay failed: %w", streamErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-review-event-stream", runner: reviewStreamRelay,
		})
	}
	handler := httpHandler.Routes()
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return nil, fmt.Errorf("entity-service access token verifier invalid: %w", err)
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
	rootMux.HandleFunc("/readyz", healthChecker.Handler())
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

	addr := getenvOrDefault("ENTITY_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	timeouts := rtauth.ContractHTTPServerTimeouts(entityguard.Descriptors())
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(withObs),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	module := &Module{
		configDigest: strings.TrimSpace(
			servicehost.ModuleEnvironmentValue("entity-service", "CONFIG_VERSION"),
		),
		server:     server,
		health:     healthChecker,
		serveError: make(chan error, 1),
		workerStart: append(
			[]func(context.Context){followConsumer.Run},
			projectionWorkerStarts(projectionRunners)...,
		),
		cleanup: cleanup,
	}
	if module.configDigest == "" {
		module.configDigest = fmt.Sprintf("%s:%s", appEnv, cfg.Service.Name)
	}
	server.Handler = module.admissionHandler(server.Handler)
	server.BaseContext = func(net.Listener) context.Context {
		if module.runContext != nil {
			return module.runContext
		}
		return context.Background()
	}
	initialized = true
	return module, nil
}

func (module *Module) Name() string { return "entity-service" }

func (module *Module) ConfigDigest() string {
	if module == nil {
		return ""
	}
	return module.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.server == nil || module.health == nil || module.cleanup == nil {
		return errors.New("entity-service module is incomplete")
	}
	return nil
}

func (module *Module) PrepareMigration(context.Context) error {
	return nil
}

func (module *Module) Bind(context.Context) error {
	if module == nil || module.server == nil {
		return errors.New("entity-service HTTP server is unavailable")
	}
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("entity-service listener bind: %w", err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(ctx context.Context) error {
	if module == nil || module.listener == nil {
		return errors.New("entity-service listener is not bound")
	}
	module.runContext, module.workerCancel = context.WithCancel(ctx)
	for _, start := range module.workerStart {
		module.workerGroup.Add(1)
		module.startWorker(start)
	}
	module.workerGroup.Add(1)
	go func() {
		defer module.workerGroup.Done()
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
	if result := module.health.Check(ctx); result.Status != "ok" {
		return fmt.Errorf("entity-service readiness failed: %v", result.FailedChecks)
	}
	select {
	case err := <-module.serveError:
		return fmt.Errorf("entity-service listener failed: %w", err)
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

type projectionRunner interface {
	RunOnce(ctx context.Context, limit int) (int, error)
}

type namedProjectionRunner struct {
	name   string
	runner projectionRunner
}

func projectionWorkerStarts(runners []namedProjectionRunner) []func(context.Context) {
	starts := make([]func(context.Context), 0, len(runners))
	for _, runner := range runners {
		runner := runner
		starts = append(starts, func(ctx context.Context) {
			runProjectionLoop(ctx, runner)
		})
	}
	return starts
}

func runProjectionLoop(ctx context.Context, named namedProjectionRunner) {
	const (
		interval  = 2 * time.Second
		batchSize = 100
	)
	delay := time.Duration(0)
	consecutiveFailures := 0
	for {
		if delay > 0 {
			timer := time.NewTimer(delay)
			select {
			case <-ctx.Done():
				timer.Stop()
				return
			case <-timer.C:
			}
		}
		if _, err := named.runner.RunOnce(ctx, batchSize); err != nil && ctx.Err() == nil {
			log.Printf("entity-service projection %s failed: %v", named.name, err)
			consecutiveFailures++
			delay = projectionRetryDelay(interval, consecutiveFailures)
		} else {
			consecutiveFailures = 0
			delay = interval
		}
	}
}

func projectionRetryDelay(base time.Duration, attempt int) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	if attempt > 5 {
		attempt = 5
	}
	delay := base * time.Duration(1<<(attempt-1))
	if delay > 30*time.Second {
		return 30 * time.Second
	}
	return delay
}

func loadRuntimeConfig() (config, error) {
	cfg := config{}
	serviceName := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("entity-service", "SERVICE_NAME"),
	)
	if serviceName == "" {
		serviceName = "entity-service"
	}
	appEnv := getenvOrDefault("APP_ENV", "alpha")
	configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	configVersion := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("entity-service", "CONFIG_VERSION"),
	)
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
