package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	rtmongo "quwoquan_service/internal/platform/mongodb"

	"quwoquan_service/internal/platform/pgoutbox"
	"quwoquan_service/runtime/artifactidentity"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	accountenforcementapp "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/application"
	accountenforcementobservability "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/observability"
	accountenforcementpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/persistence"
	accountenforcementuser "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/useraccount"
	apprelease "quwoquan_service/services/product-ops-service/internal/product_ops/app_release/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/logsink"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/messaging"
	opsobservability "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/observability"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
	experimenthttp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/adapters/inbound/http"
	experimentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	experimentmessaging "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/infrastructure/messaging"
	experimentpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/infrastructure/persistence"
	assignmenthttp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/adapters/inbound/http"
	assignmentstream "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/adapters/inbound/stream"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
	assignmentpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/infrastructure/persistence"
	premiumpoolapp "quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/application"
	premiumpoolpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/infrastructure/persistence"
	recoveryfailure "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/application"
	recoveryreporter "quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/infrastructure/eventrecord"
	visitapplication "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/application"
	visitpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/infrastructure/persistence"
)

type productService struct {
	store              controlplane.StateStore
	telemetry          *application.TelemetryService
	visits             *visitapplication.Service
	runtimeLogs        *application.RuntimeLogService
	runtimeLogStore    application.RuntimeLogStore
	growth             *application.GrowthService
	prometheus         application.PrometheusQuery
	experimentHTTP     *experimenthttp.Handler
	assignmentHTTP     *assignmenthttp.Handler
	publisher          runtimemessaging.EventPublisher
	appRelease         *apprelease.Service
	recoveryFailures   *recoveryfailure.Service
	accountEnforcement *accountenforcementapp.Service
	premiumPool        *premiumpoolapp.Service
}

func main() {
	if _, err := artifactidentity.LoadAndValidate(
		os.Getenv("QWQ_ARTIFACT_IDENTITY_FILE"),
		os.Getenv("APP_ENV"),
	); err != nil {
		log.Fatalf("product-ops-service artifact identity invalid: %v", err)
	}
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("product-ops-service runtime identity invalid: %v", err)
	}
	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("product-ops-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	cfg, err = resolveLogSinkBinding(
		cfg,
		appEnv,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("product-ops-service log sink binding invalid: %v", err)
	}
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("product-ops-service config identity failed: %v", err)
	}
	if err := validateRequiredRuntimeConfig(cfg, appEnv); err != nil {
		log.Fatalf("product-ops-service required runtime config invalid: %v", err)
	}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("product-ops-service access token config invalid: %v", err)
	}
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		serviceName,
		[]string{"user.account.security.read"},
	)
	if err != nil {
		log.Fatalf("product-ops-service account security authority credential init failed: %v", err)
	}
	accountEnforcementCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		serviceName,
		[]string{"user.account.enforcement.write"},
	)
	if err != nil {
		log.Fatalf("product-ops-service account enforcement credential init failed: %v", err)
	}
	accountAppealIntakeCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		serviceName,
		[]string{"user.account.appeal_intake.claim"},
	)
	if err != nil {
		log.Fatalf("product-ops-service account appeal intake credential init failed: %v", err)
	}
	accountSecurityAuthorityTimeout := time.Duration(
		cfg.AccountSecurityAuthority.TimeoutMS,
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
		log.Fatalf("product-ops-service account security authority config invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("product-ops-service access token verifier invalid: %v", err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		log.Fatalf("product-ops-service device ticket config invalid: %v", err)
	}
	deviceTicketVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		log.Fatalf("product-ops-service device ticket verifier invalid: %v", err)
	}
	operatorOIDCVerifier, err := rtauth.NewOIDCVerifierFromEnv("OPS_OIDC")
	if err != nil {
		log.Fatalf("product-ops-service operator OIDC verifier invalid: %v", err)
	}
	if operatorOIDCVerifier == nil &&
		rtauth.OperatorOIDCRequiredForEnvironment(appEnv) {
		log.Fatal("product-ops-service operator OIDC issuer/audience/JWKS configuration is required")
	}
	var prometheusReader application.PrometheusQuery
	if prometheusURL := strings.TrimSpace(os.Getenv("PROMETHEUS_URL")); prometheusURL != "" {
		prometheusReader, err = opsobservability.NewPrometheusReader(prometheusURL, nil)
		if err != nil {
			log.Fatalf("product-ops-service prometheus reader invalid: %v", err)
		}
	} else if appEnv == "prod" || appEnv == "release" {
		log.Fatal("product-ops-service PROMETHEUS_URL is required for production L3/L4 readback")
	}
	addr := getenvOrDefault("PRODUCT_OPS_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if strings.TrimSpace(addr) == "" {
		addr = ":18086"
	}
	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "product-ops-service", SamplingRatio: 0.1})
	defer otelShutdown()

	ctx, cancelRuntime := context.WithCancel(context.Background())
	defer cancelRuntime()
	instanceID, _ := os.Hostname()
	if strings.TrimSpace(instanceID) == "" {
		instanceID = serviceName
	}
	postgresConfig, err := pgxpool.ParseConfig(cfg.Postgres.DSN)
	if err != nil {
		log.Fatalf("product-ops-service postgres config invalid: %v", err)
	}
	postgresConfig.MaxConns = 20
	postgresConfig.MinConns = 2
	postgresConfig.HealthCheckPeriod = 30 * time.Second
	postgresPool, err := pgxpool.NewWithConfig(ctx, postgresConfig)
	if err != nil {
		log.Fatalf("product-ops-service postgres connect failed: %v", err)
	}
	defer postgresPool.Close()
	if err := postgresPool.Ping(ctx); err != nil {
		log.Fatalf("product-ops-service postgres unavailable: %v", err)
	}
	store, err := controlplanepersistence.NewPostgresStore(postgresPool, "product-ops")
	if err != nil {
		log.Fatalf("product-ops-service control plane store invalid: %v", err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		log.Fatalf("product-ops-service control plane schema initialization failed: %v", err)
	}
	experimentStore, err := experimentpersistence.NewPostgresStore(postgresPool)
	if err != nil {
		log.Fatalf("product-ops-service experiment store invalid: %v", err)
	}
	if err := experimentStore.EnsureSchema(ctx); err != nil {
		log.Fatalf("product-ops-service experiment schema initialization failed: %v", err)
	}
	assignmentStore, err := assignmentpersistence.NewPostgresStore(postgresPool)
	if err != nil {
		log.Fatalf("product-ops-service experiment assignment store invalid: %v", err)
	}
	if err := assignmentStore.EnsureSchema(ctx); err != nil {
		log.Fatalf("product-ops-service experiment assignment schema initialization failed: %v", err)
	}
	accountEnforcementStore, err := accountenforcementpersistence.NewPostgresStore(postgresPool)
	if err != nil {
		log.Fatalf("product-ops-service account enforcement store invalid: %v", err)
	}
	if err := accountEnforcementStore.EnsureSchema(ctx); err != nil {
		log.Fatalf("product-ops-service account enforcement schema initialization failed: %v", err)
	}
	premiumPoolStore, err := premiumpoolpersistence.NewPostgresStore(postgresPool)
	if err != nil {
		log.Fatalf("product-ops-service PremiumPoolEntry store invalid: %v", err)
	}
	if err := premiumPoolStore.EnsureSchema(ctx); err != nil {
		log.Fatalf("product-ops-service PremiumPoolEntry schema initialization failed: %v", err)
	}
	premiumPoolService := premiumpoolapp.NewService(premiumPoolStore)
	accountEnforcementMetrics := accountenforcementobservability.Recorder{}
	accountAppealIntakes, err := accountenforcementuser.NewAppealIntakeHTTPClient(
		accountenforcementuser.AppealIntakeHTTPClientConfig{
			BaseURL: cfg.AccountSecurityAuthority.BaseURL,
			HTTPClient: &http.Client{
				Timeout: time.Duration(cfg.AccountEnforcement.RequestTimeoutMS) * time.Millisecond,
			},
			Credentials: accountAppealIntakeCredentials,
		},
	)
	if err != nil {
		log.Fatalf("product-ops-service account appeal intake target invalid: %v", err)
	}
	accountEnforcementService := accountenforcementapp.NewService(
		accountEnforcementStore,
		accountEnforcementMetrics,
		accountAppealIntakes,
	)
	accountEnforcementTarget, err := accountenforcementuser.NewHTTPClient(
		accountenforcementuser.HTTPClientConfig{
			BaseURL: cfg.AccountSecurityAuthority.BaseURL,
			HTTPClient: &http.Client{
				Timeout: time.Duration(cfg.AccountEnforcement.RequestTimeoutMS) * time.Millisecond,
			},
			Credentials: accountEnforcementCredentials,
		},
	)
	if err != nil {
		log.Fatalf("product-ops-service account enforcement target invalid: %v", err)
	}
	accountEnforcementDispatcher, err := accountenforcementapp.NewDeliveryRelay(
		accountEnforcementStore,
		accountEnforcementTarget,
		accountEnforcementMetrics,
		accountenforcementapp.DispatcherConfig{
			Owner:          instanceID,
			PollInterval:   time.Duration(cfg.AccountEnforcement.PollIntervalMS) * time.Millisecond,
			LeaseDuration:  time.Duration(cfg.AccountEnforcement.LeaseDurationMS) * time.Millisecond,
			RequestTimeout: time.Duration(cfg.AccountEnforcement.RequestTimeoutMS) * time.Millisecond,
			InitialBackoff: time.Duration(cfg.AccountEnforcement.InitialBackoffMS) * time.Millisecond,
			MaxBackoff:     time.Duration(cfg.AccountEnforcement.MaxBackoffMS) * time.Millisecond,
			MaxPendingAge:  time.Duration(cfg.AccountEnforcement.MaxPendingAgeMS) * time.Millisecond,
			MaxAttempts:    cfg.AccountEnforcement.MaxAttempts,
			BatchSize:      cfg.AccountEnforcement.BatchSize,
		},
	)
	if err != nil {
		log.Fatalf("product-ops-service account enforcement dispatcher invalid: %v", err)
	}
	experimentFacade, err := experimentapp.NewFacade(
		experimentStore,
		experimentStore,
	)
	if err != nil {
		log.Fatalf("product-ops-service experiment facade invalid: %v", err)
	}
	assignmentFacade, err := assignmentapp.NewFacade(
		experimentFacade,
		assignmentStore,
		assignmentStore,
	)
	if err != nil {
		log.Fatalf("product-ops-service experiment assignment facade invalid: %v", err)
	}
	router, messageTransportSceneModes, err := buildRedisRouter(cfg)
	if err != nil {
		log.Fatalf("product-ops-service redis config invalid: %v", err)
	}
	defer router.Close()
	messageTransport, err := requireMessageTransport(
		ctx,
		appEnv,
		router,
		messageTransportSceneModes,
	)
	if err != nil {
		log.Fatalf("product-ops-service message transport preflight failed: %v", err)
	}
	if err := router.PingAll(ctx); err != nil {
		log.Fatalf("product-ops-service redis unavailable: %v", err)
	}
	healthChecker := rthealth.NewChecker()
	healthChecker.Register("account-security-authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	healthChecker.Register("redis", func(ctx context.Context) error {
		return router.PingAll(ctx)
	})
	healthChecker.Register("account-enforcement-delivery", accountEnforcementDispatcher.CheckReadiness)
	go accountEnforcementDispatcher.Run(ctx)
	assignmentConsumer, err := assignmentstream.NewConsumer(
		messageTransport,
		assignmentFacade,
		serviceName+"-"+instanceID,
		nil,
	)
	if err != nil {
		log.Fatalf("product-ops-service experiment assignment consumer invalid: %v", err)
	}
	if err := assignmentConsumer.EnsureGroup(ctx); err != nil {
		log.Fatalf("product-ops-service experiment assignment consumer group failed: %v", err)
	}
	healthChecker.Register("experiment-assignment-consumer", func(context.Context) error {
		return assignmentConsumer.Healthy(10 * time.Second)
	})
	go assignmentConsumer.Run(ctx)
	publisher := messaging.NewRedisEventPublisherWithTransport(messageTransport, serviceName, nil)
	experimentPublisher, err := experimentmessaging.NewPublisher(messageTransport)
	if err != nil {
		log.Fatalf("product-ops-service Experiment policy publisher invalid: %v", err)
	}
	outboxDispatcher, err := pgoutbox.NewDispatcher(postgresPool, experimentPublisher, "product_ops_outbox")
	if err != nil {
		log.Fatalf("product-ops-service outbox dispatcher invalid: %v", err)
	}
	go outboxDispatcher.Run(ctx)
	controlPlaneOutboxDispatcher, err := pgoutbox.NewDispatcher(
		postgresPool,
		publisher,
		"product_control_plane_outbox",
	)
	if err != nil {
		log.Fatalf("product-ops-service control-plane outbox dispatcher invalid: %v", err)
	}
	go controlPlaneOutboxDispatcher.Run(ctx)
	premiumPoolOutboxDispatcher, err := pgoutbox.NewDispatcher(
		postgresPool,
		publisher,
		"premium_pool_entry_outbox",
	)
	if err != nil {
		log.Fatalf("product-ops-service PremiumPoolEntry outbox dispatcher invalid: %v", err)
	}
	go premiumPoolOutboxDispatcher.Run(ctx)
	mongoClient, err := rtmongo.Connect(ctx, rtmongo.ConnectConfig{URI: cfg.MongoDB.URI})
	if err != nil {
		log.Fatalf("product-ops-service mongodb unavailable: %v", err)
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = mongoClient.Disconnect(shutdownCtx)
	}()
	dbName := strings.TrimSpace(cfg.MongoDB.Database)
	mongoVisitStore := visitpersistence.NewMongoVisitStore(mongoClient.Database(dbName))
	if err := mongoVisitStore.EnsureIndexes(ctx); err != nil {
		log.Fatalf("product-ops-service visit index initialization failed: %v", err)
	}
	visitService := visitapplication.NewService(mongoVisitStore)
	healthChecker.Register("mongodb", func(ctx context.Context) error {
		return mongoClient.Ping(ctx, nil)
	})
	healthChecker.Register("postgres", func(ctx context.Context) error {
		return postgresPool.Ping(ctx)
	})
	var eventStore application.EventLogStore
	var rtcMediaQoeReader application.RtcMediaQoeSummaryReader
	var runtimeLogStore application.RuntimeLogStore
	var batchLedger application.EventBatchLedger
	// 协议与契约证据由 local_contract 测试直接组装 in-memory store；生产二进制
	// 不承载任何 Memory composition，缺后端能力时按下方分支 fail-fast。
	switch cfg.LogSinkAdapterID {
	case logsink.ElasticsearchAdapterID:
		elasticsearchStore, err := telemetrypersistence.NewElasticsearchEventLogStore(
			telemetrypersistence.ElasticsearchConfig{
				Endpoint:               strings.TrimSpace(cfg.Elasticsearch.Endpoint),
				APIKey:                 strings.TrimSpace(cfg.Elasticsearch.APIKey),
				RawIndex:               strings.TrimSpace(cfg.Elasticsearch.RawIndex),
				StartupDiagnosticIndex: strings.TrimSpace(cfg.Elasticsearch.StartupDiagnosticIndex),
				RuntimeLogIndex:        strings.TrimSpace(cfg.Elasticsearch.RuntimeLogIndex),
				AggregateIndex:         strings.TrimSpace(cfg.Elasticsearch.AggregateIndex),
				Timeout:                time.Duration(cfg.Elasticsearch.TimeoutMS) * time.Millisecond,
			},
		)
		if err != nil {
			log.Fatalf(
				"product-ops-service Elasticsearch telemetry store invalid: %v",
				err,
			)
		}
		// Docker/Colima 内嵌 DNS 在全栈冷启动最初几秒可能对刚接入网络的容器
		// 返回瞬时解析失败（"server misbehaving"）。索引初始化对这种基础设施
		// 抖动必须做有界重试，否则本服务秒退，进而卡死「实验策略激活 →
		// recommendation-service healthy」的全栈启动链；重试耗尽仍失败则维持
		// fail-fast 语义退出。
		ensureErr := elasticsearchStore.EnsureIndices(ctx)
		for attempt := 1; ensureErr != nil && attempt <= 10; attempt++ {
			log.Printf(
				"product-ops-service Elasticsearch telemetry index initialization retry %d/10: %v",
				attempt,
				ensureErr,
			)
			time.Sleep(3 * time.Second)
			ensureErr = elasticsearchStore.EnsureIndices(ctx)
		}
		if ensureErr != nil {
			log.Fatalf(
				"product-ops-service Elasticsearch telemetry index initialization failed: %v",
				ensureErr,
			)
		}
		eventStore = elasticsearchStore
		rtcMediaQoeReader = elasticsearchStore
		runtimeLogStore = elasticsearchStore
		batchLedger = telemetrypersistence.NewRedisEventBatchLedger(
			router.Scene("general"),
		)
		healthChecker.Register(
			"telemetry-elasticsearch",
			elasticsearchStore.Ping,
		)
		log.Printf(
			"product-ops-service telemetry storage=elasticsearch raw=%s runtime=%s aggregate=%s visit_storage=mongodb db=%s",
			cfg.Elasticsearch.RawIndex,
			cfg.Elasticsearch.RuntimeLogIndex,
			cfg.Elasticsearch.AggregateIndex,
			dbName,
		)
		startTelemetryAlertLoop(ctx, cfg, elasticsearchStore)
	default:
		log.Fatalf(
			"product-ops-service runtime.log.sink adapter is unsupported: %s",
			cfg.LogSinkAdapterID,
		)
	}
	service := newProductServiceWithRuntimeLogs(
		store,
		application.NewTelemetryServiceWithStoresAndRtcMediaQoeReader(
			instrumentEventLogStore(eventStore),
			batchLedger,
			instrumentRtcMediaQoeSummaryReader(rtcMediaQoeReader),
		),
		visitService,
		application.NewRuntimeLogService(runtimeLogStore, batchLedger),
		experimentFacade,
		assignmentFacade,
		publisher,
	)
	service.accountEnforcement = accountEnforcementService
	service.premiumPool = premiumPoolService
	recoveryFailureReporter, err := recoveryreporter.NewReporter(service.runtimeLogs)
	if err != nil {
		log.Fatalf("product-ops-service RecoveryFailure reporter init failed: %v", err)
	}
	service.recoveryFailures = recoveryfailure.NewService(recoveryFailureReporter)
	appReleaseService, appReleaseErr := buildAppReleaseService(cfg)
	if appReleaseErr != nil {
		log.Printf("product-ops-service app release recovery unavailable: %v", appReleaseErr)
	} else {
		service.appRelease = appReleaseService
	}
	service.prometheus = prometheusReader
	service.runtimeLogStore = runtimeLogStore
	// 运营增长聚合（user_activity_daily）：事件仓库出 distinct session，
	// Mongo 持久化天级活跃与 actor 首见事实；后台循环幂等聚合今天+昨天。
	if sessionLister, ok := eventStore.(application.ActiveSessionLister); ok {
		growthStore := telemetrypersistence.NewMongoGrowthStore(mongoClient.Database(dbName))
		if err := growthStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("product-ops-service growth index initialization failed: %v", err)
		}
		service.growth = application.NewGrowthService(growthStore, sessionLister)
		go service.growth.RunGrowthAggregationLoop(ctx, 30*time.Minute)
	} else {
		log.Fatal("product-ops-service event store must support distinct session listing (growth aggregation)")
	}
	mux := newServerMux(service, healthChecker)
	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", mux)
	// 只有不能依赖登录态的启动/恢复入口允许匿名访问；它们分别以
	// 固定 schema、严格大小和每来源 IP 配额收紧，不绕过通用 /ops/events 的鉴权要求。
	outerMux.HandleFunc("/ops/startup-events", func(w http.ResponseWriter, r *http.Request) {
		mux.ServeHTTP(w, r)
	})
	outerMux.HandleFunc("/ops/app-recovery/version", func(w http.ResponseWriter, r *http.Request) {
		mux.ServeHTTP(w, r)
	})
	outerMux.HandleFunc("/ops/recovery-failures", func(w http.ResponseWriter, r *http.Request) {
		mux.ServeHTTP(w, r)
	})
	outerMux.Handle("/download", mux)
	outerMux.Handle("/download/", mux)
	// 云侧服务日志上云的内部通道：以 X-Runtime-Log-Ingest-Token 机器凭据
	// fail-closed（handler 内校验），不走用户 JWT；app sourceType 被拒绝。该路径
	// 在最外层跳过 access/process logger，避免 product-ops 自身 spool 回灌时把
	// transport 请求再次写进 spool 而形成反馈环。
	internalRuntimeLogIngest := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mux.ServeHTTP(w, r)
	})
	outerMux.Handle(
		"/",
		requireProductOpsGeneratedOperationAuthorization(mux),
	)

	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("product-ops-service runtime log exporter init failed: %v", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(
		os.Stdout,
		512,
		runtimeLogExporter.Export,
	)
	errorLogWriter := robs.NewRuntimeLogExportWriter(
		os.Stderr,
		512,
		runtimeLogExporter.Export,
	)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, pErr := robs.NewProcessTraceLogger(
		standardLogWriter,
		errorLogWriter,
		"info",
		nil,
	)
	if pErr != nil {
		log.Fatalf("product-ops-service process logger init failed: %v", pErr)
	}
	exceptionLogger, eErr := robs.NewExceptionLogger(
		standardLogWriter,
		errorLogWriter,
		nil,
	)
	if eErr != nil {
		log.Fatalf("product-ops-service exception logger init failed: %v", eErr)
	}
	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "product-ops-service",
		ServiceName:       "product-ops-service",
		ServiceInstanceID: instanceID,
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())
	hotConfigStore := controlplane.NewHotConfigStore()
	go startConfigSyncLoop(serviceName, appEnv, configRoot, configVersion, imageVersion, instanceID, hotConfigStore)

	servedHandler := withProductOpsInternalRuntimeLogIngestBypass(
		internalRuntimeLogIngest,
		corsHandler,
	)
	timeouts := rtauth.ContractHTTPServerTimeouts(
		productOpsGeneratedOperationDescriptors(),
	)
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceTicketVerifier,
			OperatorOIDCVerifier:     operatorOIDCVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(servedHandler),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	log.Printf("product-ops-service listening on %s", addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("product-ops-service: %v", err)
	}
}

func withProductOpsInternalRuntimeLogIngestBypass(
	internalRuntimeLogIngest http.Handler,
	observed http.Handler,
) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/ops/internal/runtime-logs:ingest" {
			internalRuntimeLogIngest.ServeHTTP(w, r)
			return
		}
		observed.ServeHTTP(w, r)
	})
}

func newProductService(
	store controlplane.StateStore,
	telemetry *application.TelemetryService,
	visits *visitapplication.Service,
	experiments *experimentapp.Facade,
	assignments *assignmentapp.Facade,
	publishers ...runtimemessaging.EventPublisher,
) *productService {
	return newProductServiceWithRuntimeLogs(
		store,
		telemetry,
		visits,
		nil,
		experiments,
		assignments,
		publishers...,
	)
}

func newProductServiceWithRuntimeLogs(
	store controlplane.StateStore,
	telemetry *application.TelemetryService,
	visits *visitapplication.Service,
	runtimeLogs *application.RuntimeLogService,
	experiments *experimentapp.Facade,
	assignments *assignmentapp.Facade,
	publishers ...runtimemessaging.EventPublisher,
) *productService {
	var publisher runtimemessaging.EventPublisher
	if len(publishers) > 0 {
		publisher = publishers[0]
	}
	if store == nil || telemetry == nil || visits == nil || experiments == nil || assignments == nil {
		panic("product service requires control-plane store, telemetry, visits, experiment and assignment facades")
	}
	experimentHandler, err := experimenthttp.NewHandler(experiments, assignments)
	if err != nil {
		panic(err)
	}
	assignmentHandler, err := assignmenthttp.NewHandler(assignments)
	if err != nil {
		panic(err)
	}
	return &productService{
		store: store, telemetry: telemetry, visits: visits, runtimeLogs: runtimeLogs,
		experimentHTTP: experimentHandler, assignmentHTTP: assignmentHandler,
		publisher: publisher,
	}
}

func (s *productService) putIfMissing(namespace, id string, value any) error {
	_, ok, err := s.store.GetDocument(namespace, id)
	if err != nil || ok {
		return err
	}
	return s.putDocument(namespace, id, value)
}

func (s *productService) putWorkflowIfMissing(objectType, objectID, workflowID, state string) error {
	_, ok, err := s.store.GetWorkflow(objectType, objectID)
	if err != nil || ok {
		return err
	}
	return s.store.UpsertWorkflow(controlplane.WorkflowState{
		ObjectType: objectType,
		ObjectID:   objectID,
		WorkflowID: workflowID,
		State:      state,
		History:    []controlplane.WorkflowTransition{},
		UpdatedAt:  nowRFC3339(),
	})
}

func (s *productService) putDocument(namespace, id string, value any) error {
	return s.store.PutDocument(namespace, id, documentFromStruct(value))
}

func decodeDocument[T any](doc controlplane.Document) (T, error) {
	var out T
	data, err := json.Marshal(doc)
	if err != nil {
		return out, err
	}
	if err := json.Unmarshal(data, &out); err != nil {
		return out, err
	}
	return out, nil
}

func documentFromStruct(value any) controlplane.Document {
	data, _ := json.Marshal(value)
	var out controlplane.Document
	_ = json.Unmarshal(data, &out)
	return out
}

func approvalExistsForIntent(
	items []controlplane.ApprovalDecision,
	actor string,
	payloadDigest string,
	decision string,
) bool {
	for _, item := range items {
		if item.Actor == actor &&
			item.Mode == "dual" &&
			item.PayloadDigest == payloadDigest &&
			item.Decision == decision {
			return true
		}
	}
	return false
}

func distinctApprovalActors(items []controlplane.ApprovalDecision) []string {
	seen := map[string]bool{}
	out := make([]string, 0)
	for _, item := range items {
		if item.Actor == "" || seen[item.Actor] {
			continue
		}
		seen[item.Actor] = true
		out = append(out, item.Actor)
	}
	sort.Strings(out)
	return out
}

func dualApprovalPayloadDigest(before controlplane.Document, intent string) string {
	payload, _ := json.Marshal(struct {
		Before controlplane.Document `json:"before"`
		Intent string                `json:"intent"`
	}{Before: before, Intent: strings.TrimSpace(intent)})
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:])
}

func dualApprovalSatisfied(
	items []controlplane.ApprovalDecision,
	payloadDigest string,
	decision string,
) bool {
	actors := make(map[string]struct{}, 2)
	for _, item := range items {
		if item.Mode != "dual" ||
			item.PayloadDigest != payloadDigest ||
			item.Decision != decision {
			continue
		}
		actor := strings.TrimSpace(item.Actor)
		if actor != "" {
			actors[actor] = struct{}{}
		}
	}
	return len(actors) >= 2
}

func distinctMatchingApprovalActors(
	items []controlplane.ApprovalDecision,
	payloadDigest string,
	decision string,
) []string {
	seen := make(map[string]struct{}, 2)
	for _, item := range items {
		if item.Mode != "dual" ||
			item.PayloadDigest != payloadDigest ||
			item.Decision != decision {
			continue
		}
		if actor := strings.TrimSpace(item.Actor); actor != "" {
			seen[actor] = struct{}{}
		}
	}
	out := make([]string, 0, len(seen))
	for actor := range seen {
		out = append(out, actor)
	}
	sort.Strings(out)
	return out
}

func countMatchingApprovals(
	items []controlplane.ApprovalDecision,
	payloadDigest string,
	decision string,
) int {
	return len(distinctMatchingApprovalActors(items, payloadDigest, decision))
}

func actorFromRequest(r *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		if actor := strings.TrimSpace(principal.Actor.AccountID); actor != "" {
			return actor
		}
		if actor := strings.TrimSpace(principal.Actor.DeviceActorID); actor != "" {
			return actor
		}
	}
	return "unverified"
}

func environmentFromRequest(r *http.Request) string {
	_ = r
	if env := strings.TrimSpace(os.Getenv("APP_ENV")); env != "" {
		return env
	}
	return "unknown"
}

func requestIDFromRequest(r *http.Request) string {
	if requestID := strings.TrimSpace(r.Header.Get("X-Request-Id")); requestID != "" {
		return requestID
	}
	return "req-" + strings.ReplaceAll(nowRFC3339(), ":", "")
}

func traceIDFromRequest(r *http.Request) string {
	if traceID := strings.TrimSpace(r.Header.Get("X-Trace-Id")); traceID != "" {
		return traceID
	}
	return "trace-" + strings.ReplaceAll(nowRFC3339(), ":", "")
}

func segmentBetween(path, prefix, suffix string) string {
	value := strings.TrimPrefix(path, prefix)
	value = strings.TrimSuffix(value, suffix)
	return strings.Trim(value, "/")
}

func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339)
}

func cloneMap(in map[string]any) map[string]any {
	data, _ := json.Marshal(in)
	var out map[string]any
	_ = json.Unmarshal(data, &out)
	return out
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeRuntimeNotFound(
	w http.ResponseWriter,
	r *http.Request,
	_ int,
	_ string,
	_ string,
) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "route_not_found"),
			"接口不存在",
			"route not found",
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
