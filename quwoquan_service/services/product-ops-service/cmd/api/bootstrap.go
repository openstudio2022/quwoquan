package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	"quwoquan_service/internal/platform/pgoutbox"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/servicekit"
	accountenforcementapp "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/application"
	accountenforcementobservability "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/observability"
	accountenforcementpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/persistence"
	accountenforcementuser "quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/infrastructure/useraccount"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/logsink"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/messaging"
	opsobservability "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/observability"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
	experimentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	experimentmessaging "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/infrastructure/messaging"
	experimentpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/infrastructure/persistence"
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

const serviceName = "product-ops-service"

// internalRuntimeLogIngestPath 是云侧服务日志上云的内部通道：它在最外层
// 跳过访问/进程日志中间件，避免 product-ops 自身 spool 回灌时把 transport
// 请求再次写进 spool 而形成反馈环。
const internalRuntimeLogIngestPath = "/ops/internal/runtime-logs:ingest"

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定
// 键集不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix(serviceName), &config{})
}

func newModule() (*servicekit.Module, error) {
	// domainRoutes 由领域装配填充，供 unobserved bypass 与匿名放行面复用同
	// 一张路由表；它必须在 Bootstrap 的 Assemble 之后才被读取。
	var domainRoutes http.Handler

	return servicekit.Bootstrap(serviceName, servicekit.BootstrapSpec[config]{
		OperationDescriptors: productOpsGeneratedOperationDescriptors(),
		// 运营台是浏览器直连入口，按 env 派生 origin 策略开跨域。
		CORS:            servicekit.BrowserCORSFromEnv(),
		AuthorityScopes: []string{"user.account.security.read"},
		// 运营台身份走 OIDC；Prod/release 缺配置即 fail-closed。
		OperatorOIDCEnvPrefix: "OPS_OIDC",
		RetiredEnvKeys:        retiredEnvKeys(),
		ValidateConfig:        validateProductOpsConfig,
		RedisScenes:           resolveRedisScenes,
		Assemble: func(asm *servicekit.Assembly, cfg *config) error {
			if err := assembleProductOpsDomain(asm, cfg); err != nil {
				return err
			}
			domainRoutes = asm.Mux
			return nil
		},
		WrapHandler: func(observed http.Handler) http.Handler {
			return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path == internalRuntimeLogIngestPath {
					domainRoutes.ServeHTTP(w, r)
					return
				}
				observed.ServeHTTP(w, r)
			})
		},
	})
}

func assembleProductOpsDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context
	instanceID := asm.Identity.InstanceID

	prometheusReader, err := resolvePrometheusReader(cfg.Environment)
	if err != nil {
		return err
	}

	controlPlaneStore, err := controlplanepersistence.NewPostgresStore(asm.PostgresPool, "product-ops")
	if err != nil {
		return fmt.Errorf("control plane store invalid: %w", err)
	}
	if err := controlPlaneStore.EnsureSchema(ctx); err != nil {
		return fmt.Errorf("control plane schema initialization failed: %w", err)
	}
	experimentStore, err := experimentpersistence.NewPostgresStore(asm.PostgresPool)
	if err != nil {
		return fmt.Errorf("experiment store invalid: %w", err)
	}
	if err := experimentStore.EnsureSchema(ctx); err != nil {
		return fmt.Errorf("experiment schema initialization failed: %w", err)
	}
	assignmentStore, err := assignmentpersistence.NewPostgresStore(asm.PostgresPool)
	if err != nil {
		return fmt.Errorf("experiment assignment store invalid: %w", err)
	}
	if err := assignmentStore.EnsureSchema(ctx); err != nil {
		return fmt.Errorf("experiment assignment schema initialization failed: %w", err)
	}
	accountEnforcementStore, err := accountenforcementpersistence.NewPostgresStore(asm.PostgresPool)
	if err != nil {
		return fmt.Errorf("account enforcement store invalid: %w", err)
	}
	if err := accountEnforcementStore.EnsureSchema(ctx); err != nil {
		return fmt.Errorf("account enforcement schema initialization failed: %w", err)
	}
	premiumPoolStore, err := premiumpoolpersistence.NewPostgresStore(asm.PostgresPool)
	if err != nil {
		return fmt.Errorf("PremiumPoolEntry store invalid: %w", err)
	}
	if err := premiumPoolStore.EnsureSchema(ctx); err != nil {
		return fmt.Errorf("PremiumPoolEntry schema initialization failed: %w", err)
	}

	accountEnforcementService, accountEnforcementDispatcher, err := assembleAccountEnforcement(
		asm, cfg, accountEnforcementStore, instanceID,
	)
	if err != nil {
		return err
	}
	asm.Health.Register(
		"account-enforcement-delivery", accountEnforcementDispatcher.CheckReadiness,
	)
	asm.Workers.Add(accountEnforcementDispatcher.Run)

	experimentFacade, err := experimentapp.NewFacade(experimentStore, experimentStore)
	if err != nil {
		return fmt.Errorf("experiment facade invalid: %w", err)
	}
	assignmentFacade, err := assignmentapp.NewFacade(
		experimentFacade, assignmentStore, assignmentStore,
	)
	if err != nil {
		return fmt.Errorf("experiment assignment facade invalid: %w", err)
	}

	messageTransport, err := requireMessageTransport(
		ctx, cfg.Environment, asm.RedisRouter, asm.RedisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("message transport preflight failed: %w", err)
	}
	if err := asm.RedisRouter.PingAll(ctx); err != nil {
		return fmt.Errorf("redis unavailable: %w", err)
	}

	assignmentConsumer, err := assignmentstream.NewConsumer(
		messageTransport, assignmentFacade, serviceName+"-"+instanceID, nil,
	)
	if err != nil {
		return fmt.Errorf("experiment assignment consumer invalid: %w", err)
	}
	if err := assignmentConsumer.EnsureGroup(ctx); err != nil {
		return fmt.Errorf("experiment assignment consumer group failed: %w", err)
	}
	asm.Health.Register("experiment-assignment-consumer", func(context.Context) error {
		return assignmentConsumer.Healthy(10 * time.Second)
	})
	asm.Workers.Add(assignmentConsumer.Run)

	publisher := messaging.NewRedisEventPublisherWithTransport(messageTransport, serviceName, nil)
	experimentPublisher, err := experimentmessaging.NewPublisher(messageTransport)
	if err != nil {
		return fmt.Errorf("Experiment policy publisher invalid: %w", err)
	}
	for _, outbox := range []struct {
		table     string
		publisher runtimemessaging.EventPublisher
	}{
		{table: "product_ops_outbox", publisher: experimentPublisher},
		{table: "product_control_plane_outbox", publisher: publisher},
		{table: "premium_pool_entry_outbox", publisher: publisher},
	} {
		dispatcher, err := pgoutbox.NewDispatcher(
			asm.PostgresPool, outbox.publisher, outbox.table,
		)
		if err != nil {
			return fmt.Errorf("%s dispatcher invalid: %w", outbox.table, err)
		}
		asm.Workers.Add(dispatcher.Run)
	}

	mongoVisitStore := visitpersistence.NewMongoVisitStore(asm.MongoDB)
	if err := mongoVisitStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("visit index initialization failed: %w", err)
	}

	eventRepository, err := assembleEventRepository(asm, cfg)
	if err != nil {
		return err
	}

	service := newProductServiceWithRuntimeLogs(
		controlPlaneStore,
		application.NewTelemetryServiceWithStoresAndRtcMediaQoeReader(
			instrumentEventLogStore(eventRepository.eventStore),
			eventRepository.batchLedger,
			instrumentRtcMediaQoeSummaryReader(eventRepository.rtcMediaQoeReader),
		),
		visitapplication.NewService(mongoVisitStore),
		application.NewRuntimeLogService(
			eventRepository.runtimeLogStore, eventRepository.batchLedger,
		),
		experimentFacade,
		assignmentFacade,
		publisher,
	)
	service.accountEnforcement = accountEnforcementService
	service.premiumPool = premiumpoolapp.NewService(premiumPoolStore)
	recoveryFailureReporter, err := recoveryreporter.NewReporter(service.runtimeLogs)
	if err != nil {
		return fmt.Errorf("RecoveryFailure reporter init failed: %w", err)
	}
	service.recoveryFailures = recoveryfailure.NewService(recoveryFailureReporter)
	if appReleaseService, appReleaseErr := buildAppReleaseService(*cfg); appReleaseErr != nil {
		log.Printf("product-ops-service app release recovery unavailable: %v", appReleaseErr)
	} else {
		service.appRelease = appReleaseService
	}
	service.prometheus = prometheusReader
	service.runtimeLogStore = eventRepository.runtimeLogStore

	// 运营增长聚合（user_activity_daily）：事件仓库出 distinct session，
	// Mongo 持久化天级活跃与 actor 首见事实；后台循环幂等聚合今天+昨天。
	sessionLister, ok := eventRepository.eventStore.(application.ActiveSessionLister)
	if !ok {
		return fmt.Errorf(
			"event store must support distinct session listing (growth aggregation)",
		)
	}
	growthStore := telemetrypersistence.NewMongoGrowthStore(asm.MongoDB)
	if err := growthStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("growth index initialization failed: %w", err)
	}
	service.growth = application.NewGrowthService(growthStore, sessionLister)
	asm.Workers.Add(func(workerCtx context.Context) {
		service.growth.RunGrowthAggregationLoop(workerCtx, 30*time.Minute)
	})

	registerProductOpsRoutes(asm, service)
	return nil
}

// registerProductOpsRoutes 挂接领域路由。只有不能依赖登录态的启动/恢复入口
// 允许匿名访问：它们分别以固定 schema、严格大小与每来源 IP 配额收紧，不绕过
// 通用 /ops/events 的鉴权要求。
func registerProductOpsRoutes(asm *servicekit.Assembly, service *productService) {
	registerProductOpsRouteHandler(asm, newServerMux(service))
}

func registerProductOpsRouteHandler(asm *servicekit.Assembly, routes http.Handler) {
	unguarded := asm.Unguarded()
	for _, path := range []string{
		"/ops/startup-events",
		"/ops/app-recovery/version",
		"/ops/recovery-failures",
		"/download",
		"/download/",
		internalRuntimeLogIngestPath,
	} {
		unguarded.Handle(path, routes)
	}
	// 领域只挂自己实际拥有的 path 前缀。禁止以 "/" 兜底，否则领域 mux 会
	// 对 servicekit 统一拥有的 /healthz、/readyz、/metrics 形成第二路由面；
	// canonical 探针必须始终由 Bootstrap 外层 mux 回答。
	for _, path := range []string{
		"/ops/",
		"/control-plane/product/",
		"/download",
		"/download/",
	} {
		asm.Mux.Handle(path, routes)
	}
}

type eventRepositoryComposition struct {
	eventStore        application.EventLogStore
	rtcMediaQoeReader application.RtcMediaQoeSummaryReader
	runtimeLogStore   application.RuntimeLogStore
	batchLedger       application.EventBatchLedger
}

// assembleEventRepository 按 generated runtime.log.sink adapter 装配事件仓库。
// 协议与契约证据由 local_contract 测试直接组装 in-memory store；生产二进制
// 不承载任何 Memory composition，缺后端能力时 fail-closed。
func assembleEventRepository(
	asm *servicekit.Assembly, cfg *config,
) (eventRepositoryComposition, error) {
	if cfg.LogSinkAdapterID != logsink.ElasticsearchAdapterID {
		return eventRepositoryComposition{}, fmt.Errorf(
			"runtime.log.sink adapter is unsupported: %s", cfg.LogSinkAdapterID,
		)
	}
	store, err := telemetrypersistence.NewElasticsearchEventLogStore(
		telemetrypersistence.ElasticsearchConfig{
			Endpoint:               cfg.Elasticsearch.Endpoint,
			APIKey:                 cfg.Elasticsearch.APIKey,
			RawIndex:               cfg.Elasticsearch.RawIndex,
			StartupDiagnosticIndex: cfg.Elasticsearch.StartupDiagnosticIndex,
			RuntimeLogIndex:        cfg.Elasticsearch.RuntimeLogIndex,
			AggregateIndex:         cfg.Elasticsearch.AggregateIndex,
			Timeout:                time.Duration(cfg.Elasticsearch.TimeoutMS) * time.Millisecond,
		},
	)
	if err != nil {
		return eventRepositoryComposition{}, fmt.Errorf(
			"Elasticsearch telemetry store invalid: %w", err,
		)
	}
	if err := ensureTelemetryIndices(asm.Context, store); err != nil {
		return eventRepositoryComposition{}, err
	}
	asm.Health.Register("telemetry-elasticsearch", store.Ping)
	startTelemetryAlertLoop(asm.Context, *cfg, store)
	return eventRepositoryComposition{
		eventStore:        store,
		rtcMediaQoeReader: store,
		runtimeLogStore:   store,
		batchLedger: telemetrypersistence.NewRedisEventBatchLedger(
			asm.RedisRouter.Scene("general"),
		),
	}, nil
}

// ensureTelemetryIndices 对索引初始化做有界重试。Docker/Colima 内嵌 DNS 在
// 全栈冷启动最初几秒可能对刚接入网络的容器返回瞬时解析失败；不重试会让本
// 服务秒退，进而卡死「实验策略激活 → recommendation-service healthy」的启动
// 链。重试耗尽仍失败则维持 fail-closed 退出。
func ensureTelemetryIndices(
	ctx context.Context, store *telemetrypersistence.ElasticsearchEventLogStore,
) error {
	err := store.EnsureIndices(ctx)
	for attempt := 1; err != nil && attempt <= 10; attempt++ {
		log.Printf(
			"product-ops-service Elasticsearch telemetry index initialization retry %d/10: %v",
			attempt, err,
		)
		time.Sleep(3 * time.Second)
		err = store.EnsureIndices(ctx)
	}
	if err != nil {
		return fmt.Errorf("Elasticsearch telemetry index initialization failed: %w", err)
	}
	return nil
}

// assembleAccountEnforcement 装配账号处置用例：申诉受理与处置投递各自持有
// 最小 scope 的服务间凭据，二者都指向账号安全 authority 的同一 owner。
func assembleAccountEnforcement(
	asm *servicekit.Assembly,
	cfg *config,
	store *accountenforcementpersistence.PostgresStore,
	instanceID string,
) (*accountenforcementapp.Service, *accountenforcementapp.DeliveryRelay, error) {
	authorityBaseURL := cfg.UserAccountSecurityAuthority.BaseURL
	requestTimeout := time.Duration(cfg.AccountEnforcement.RequestTimeoutMS) * time.Millisecond
	metrics := accountenforcementobservability.Recorder{}

	appealCredentials, err := asm.Auth.ServiceCredentials("user.account.appeal_intake.claim")
	if err != nil {
		return nil, nil, err
	}
	appealIntakes, err := accountenforcementuser.NewAppealIntakeHTTPClient(
		accountenforcementuser.AppealIntakeHTTPClientConfig{
			BaseURL:     authorityBaseURL,
			HTTPClient:  &http.Client{Timeout: requestTimeout},
			Credentials: appealCredentials,
		},
	)
	if err != nil {
		return nil, nil, fmt.Errorf("account appeal intake target invalid: %w", err)
	}

	enforcementCredentials, err := asm.Auth.ServiceCredentials("user.account.enforcement.write")
	if err != nil {
		return nil, nil, err
	}
	enforcementTarget, err := accountenforcementuser.NewHTTPClient(
		accountenforcementuser.HTTPClientConfig{
			BaseURL:     authorityBaseURL,
			HTTPClient:  &http.Client{Timeout: requestTimeout},
			Credentials: enforcementCredentials,
		},
	)
	if err != nil {
		return nil, nil, fmt.Errorf("account enforcement target invalid: %w", err)
	}

	dispatcher, err := accountenforcementapp.NewDeliveryRelay(
		store, enforcementTarget, metrics,
		accountenforcementapp.DispatcherConfig{
			Owner:          instanceID,
			PollInterval:   time.Duration(cfg.AccountEnforcement.PollIntervalMS) * time.Millisecond,
			LeaseDuration:  time.Duration(cfg.AccountEnforcement.LeaseDurationMS) * time.Millisecond,
			RequestTimeout: requestTimeout,
			InitialBackoff: time.Duration(cfg.AccountEnforcement.InitialBackoffMS) * time.Millisecond,
			MaxBackoff:     time.Duration(cfg.AccountEnforcement.MaxBackoffMS) * time.Millisecond,
			MaxPendingAge:  time.Duration(cfg.AccountEnforcement.MaxPendingAgeMS) * time.Millisecond,
			MaxAttempts:    cfg.AccountEnforcement.MaxAttempts,
			BatchSize:      cfg.AccountEnforcement.BatchSize,
		},
	)
	if err != nil {
		return nil, nil, fmt.Errorf("account enforcement dispatcher invalid: %w", err)
	}
	return accountenforcementapp.NewService(store, metrics, appealIntakes), dispatcher, nil
}

// resolvePrometheusReader 装配 L3/L4 指标回读。生产必须有真实 Prometheus：
// 缺地址时运营台的可用性回读会变成静默空值。
func resolvePrometheusReader(environment string) (application.PrometheusQuery, error) {
	prometheusURL := prometheusEndpoint()
	if prometheusURL == "" {
		if environment == "prod" || environment == "release" {
			return nil, fmt.Errorf(
				"PROMETHEUS_URL is required for production L3/L4 readback",
			)
		}
		return nil, nil
	}
	reader, err := opsobservability.NewPrometheusReader(prometheusURL, nil)
	if err != nil {
		return nil, fmt.Errorf("prometheus reader invalid: %w", err)
	}
	return reader, nil
}

// prometheusEndpoint 是平台级注入键，不带服务前缀：同一套 Prometheus 由
// 全部运营侧服务共享。
func prometheusEndpoint() string {
	return strings.TrimSpace(os.Getenv("PROMETHEUS_URL"))
}
