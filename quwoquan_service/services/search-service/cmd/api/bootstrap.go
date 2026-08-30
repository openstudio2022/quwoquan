// Package bootstrap owns search-service's declarative composition for servicekit.
package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rterr "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	runtimemessaging "quwoquan_service/runtime/messaging"
	searchruntimees "quwoquan_service/runtime/search/es"
	"quwoquan_service/runtime/servicekit"
	bindingdescriptor "quwoquan_service/services/search-service/generated/search/search_request_fact"
	recenthttp "quwoquan_service/services/search-service/internal/search/recent_search_state/adapters/inbound/http"
	recentsearch "quwoquan_service/services/search-service/internal/search/recent_search_state/application"
	recentmetrics "quwoquan_service/services/search-service/internal/search/recent_search_state/infrastructure/metrics"
	recentsearchstore "quwoquan_service/services/search-service/internal/search/recent_search_state/infrastructure/persistence"
	signalfactadapter "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/adapters/inbound/fact"
	signalfactapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
	"quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/infrastructure/searchsignals"
	feedbackhttp "quwoquan_service/services/search-service/internal/search/search_feedback_fact/adapters/inbound/http"
	feedbackapplication "quwoquan_service/services/search-service/internal/search/search_feedback_fact/application"
	"quwoquan_service/services/search-service/internal/search/search_feedback_fact/infrastructure/feedbackstore"
	feedbackmetrics "quwoquan_service/services/search-service/internal/search/search_feedback_fact/infrastructure/metrics"
	httpadapter "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/http"
	experimentpolicymq "quwoquan_service/services/search-service/internal/search/search_index_view/adapters/inbound/mq"
	searchapplication "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	accountrestrictioninfra "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/accountrestriction"
	"quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/experimentassignment"
	"quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/experimentpolicy"
	"quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/intersectionclient"
	"quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/searchbackend"
	"quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/searchmetrics"
	userprofileinfra "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/userprofile"
	requesthttp "quwoquan_service/services/search-service/internal/search/search_request_fact/adapters/inbound/http"
	mqadapter "quwoquan_service/services/search-service/internal/search/search_request_fact/adapters/inbound/mq"
	requestapplication "quwoquan_service/services/search-service/internal/search/search_request_fact/application"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application/queryheat"
	accountclosureinfra "quwoquan_service/services/search-service/internal/search/search_request_fact/infrastructure/accountclosure"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/infrastructure/queryheatstore"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/infrastructure/querylogstore"
)

const serviceName = "search-service"

// heatRebuildInterval is how often the search-term heat read model is rebuilt
// from the query/feedback logs. The read-model TTL is wider than this so a brief
// rebuild stall never empties the served heat.
const heatRebuildInterval = 10 * time.Minute

const searchAPIMessageTransportRoot = "search-service-api"

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定键集
// 不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix(serviceName), &config{})
}

// NewModule assembles search-service without binding a listener, starting
// workers, admitting traffic, or owning process signals.
func NewModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap(serviceName, servicekit.BootstrapSpec[config]{
		OperationDescriptors: operationsecurity.ForDomain("search"),
		AuthorityScopes:      []string{"user.account.security.read"},
		SnapshotGuard:        rejectRetiredSearchSnapshotSections,
		ValidateConfig:       validateSearchConfig,
		Assemble:             assembleSearchDomain,
	})
}

func assembleSearchDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context
	logger := slog.Default()
	metricsRecorder := searchmetrics.NewRecorder()
	feedbackMetrics := feedbackmetrics.NewRecorder()
	recentMetrics := recentmetrics.NewRecorder()

	built, err := assembleSearchBackend(asm, cfg)
	if err != nil {
		return err
	}

	binding, bindingFound := bindingdescriptor.CompiledBindingFor(
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	messageTransport, err := servicekit.NewMessageTransport(
		ctx,
		asm.Identity.AppEnv,
		servicekit.MessageTransportSpec{
			RootID:       searchAPIMessageTransportRoot,
			BindingFound: bindingFound,
			Binding: runtimemessaging.MessageTransportBinding{
				State: binding.State, AdapterID: binding.AdapterID,
				TimeoutMilliseconds: binding.TimeoutMilliseconds,
			},
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		asm.RedisRouter,
		asm.RedisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("message transport construction failed: %w", err)
	}
	// 启动期 ping 与 readiness 上的 redis 检查目的不同：前者不允许一个连不上
	// Redis 的实例进入 Bind/Start 相位，后者只回答运行期抖动。
	if err := asm.RedisRouter.PingAll(ctx); err != nil {
		return fmt.Errorf("redis unavailable: %w", err)
	}

	searchSignalPublisher, err := searchsignals.NewStreamPublisher(messageTransport, logger)
	if err != nil {
		return fmt.Errorf("search signal publisher init failed: %w", err)
	}
	searchSignalAppender, err := signalfactapplication.NewAppender(searchSignalPublisher)
	if err != nil {
		return fmt.Errorf("search signal appender init failed: %w", err)
	}
	searchSignalPort, err := signalfactadapter.NewAppender(searchSignalAppender)
	if err != nil {
		return fmt.Errorf("search signal inbound port init failed: %w", err)
	}
	experimentAssignmentPublisher, err := experimentassignment.NewPublisher(messageTransport)
	if err != nil {
		return fmt.Errorf("experiment assignment publisher init failed: %w", err)
	}
	experiments, err := searchapplication.NewExperiments(experimentAssignmentPublisher)
	if err != nil {
		return fmt.Errorf("experiment resolver init failed: %w", err)
	}

	stores, err := assembleMongoStores(asm, cfg, mongoStoreDeps{
		built:            built,
		experiments:      experiments,
		messageTransport: messageTransport,
		searchSignalPort: searchSignalPort,
		feedbackMetrics:  feedbackMetrics,
		metricsRecorder:  metricsRecorder,
		logger:           logger,
	})
	if err != nil {
		return err
	}

	accountRestrictedBackend, err := searchapplication.NewAccountRestrictionBackend(
		built.Backend,
		stores.accountRestrictionProjection,
	)
	if err != nil {
		return fmt.Errorf("account restriction backend init failed: %w", err)
	}
	searchCursorCodec, err := searchapplication.NewSearchCursorCodec(
		asm.Auth.AccessTokenConfig.Secret,
	)
	if err != nil {
		return fmt.Errorf("search cursor codec init failed: %w", err)
	}
	searchSvc := searchapplication.NewSearchService(
		accountRestrictedBackend,
		searchapplication.WithSearchCursorCodec(searchCursorCodec),
		// 翻页快照（REQ-007/OPEN-005）：首个后续页惰性 OpenPIT，之后每页续期；
		// 快照失效按 cursor fail-closed，不静默退化为无快照查询。
		searchapplication.WithPaginationSnapshots(built.Client),
	)
	requestFactRecorder := requestapplication.NewRecorder(
		stores.queryLogSink,
		searchSignalPort,
		logger,
	)
	feedbackSvc := feedbackapplication.NewService(stores.feedbackSink)
	decorator := searchapplication.NewRankingDecorator(
		stores.termHeat,
		experiments,
		cfg.Ranking.TermHeatBoost,
		logger,
	)
	intersectionAttacher, err := assembleIntersectionAttacher(asm, cfg, logger, metricsRecorder)
	if err != nil {
		return err
	}

	routesMux := http.NewServeMux()
	httpadapter.NewHandlerWithConfig(
		searchSvc,
		decorator,
		metricsRecorder,
		httpadapter.HandlerConfig{
			Intersections:   intersectionAttacher,
			RequestFacts:    requestFactRecorder,
			CandidateDigest: strings.TrimSpace(os.Getenv("QWQ_RELEASE_CANDIDATE_DIGEST")),
			// 热点首屏 result 缓存：TTL 受 index freshness（30s）约束，
			// singleflight 防同 key 过期击穿（spike 档同热词并发穿透是真实场景）。
			OwnerSearchCache: searchapplication.NewOwnerSearchCache(10*time.Second, 512),
		},
	).Register(routesMux)
	requesthttp.NewHandler(stores.termHeat).Register(routesMux)
	feedbackhttp.NewHandler(feedbackSvc, feedbackMetrics).Register(routesMux)
	recenthttp.NewRecentSearchHandler(stores.recentFacade, recentMetrics).Register(routesMux)

	// 背压只包住领域路由：ES 变慢时以 typed 503 卸载，而 /healthz、/readyz、
	// /metrics 由骨架挂在限流之外，卸载期间仍可被探测与抓取。
	inflightLimiter := rtgov.NewInflightLimiter(cfg.Serving.MaxInflight)
	var domainHandler http.Handler = httpadapter.MaxInflightMiddleware(
		inflightLimiter, metricsRecorder,
	)(routesMux)
	domainHandler, err = runtimemessaging.WithDeadLetterRecoveryRoute(
		domainHandler,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/search/account-closure/dead-letters:recover",
			Module:   rterr.ModuleSearch,
			Releaser: stores.accountClosureRecovery,
		},
	)
	if err != nil {
		return fmt.Errorf("account-closure recovery route failed: %w", err)
	}
	asm.Mux.Handle("/", domainHandler)

	asm.Health.Register("feedback-signal-relay", func(hctx context.Context) error {
		return stores.feedbackSignalRelay.Healthy(hctx, 15*time.Second)
	})
	asm.Health.Register("experiment-policy-consumer", func(context.Context) error {
		return stores.experimentPolicyConsumer.Healthy(15 * time.Second)
	})
	asm.Health.Register("experiment-policy", func(context.Context) error {
		return experiments.Healthy()
	})
	asm.Health.Register("user-account-closed-consumer", func(context.Context) error {
		return stores.accountClosureConsumer.Healthy(15 * time.Second)
	})
	asm.Health.Register("user-account-restriction-consumer", func(context.Context) error {
		return stores.accountRestrictionConsumer.Healthy(15 * time.Second)
	})
	asm.Health.Register(
		"user-profile-search-projection-consumer",
		func(context.Context) error {
			return stores.userProfileProjectionConsumer.Healthy(15 * time.Second)
		},
	)

	asm.Workers.Add(stores.experimentPolicyConsumer.Run)
	asm.Workers.Add(stores.feedbackSignalRelay.Run)
	asm.Workers.Add(stores.accountClosureConsumer.Run)
	asm.Workers.Add(stores.accountRestrictionConsumer.Run)
	asm.Workers.Add(stores.userProfileProjectionConsumer.Run)
	asm.Workers.Add(func(workerCtx context.Context) {
		startHeatRebuildLoop(workerCtx, stores.heatStore, logger)
	})
	return nil
}

// assembleSearchBackend 显式装配 Elasticsearch：骨架只自动装配
// Mongo/Postgres/Redis，ES 客户端、索引初始化与健康检查归本服务。
func assembleSearchBackend(
	asm *servicekit.Assembly, cfg *config,
) (searchbackend.Built, error) {
	built, err := searchbackend.Build(cfg.ES)
	if err != nil {
		return searchbackend.Built{}, fmt.Errorf("backend assembly failed: %w", err)
	}
	if err := ensureSearchIndex(asm.Context, built); err != nil {
		return searchbackend.Built{}, err
	}
	if readiness := built.ReadinessCheck(); readiness != nil {
		asm.Health.Register("elasticsearch", readiness)
	}
	return built, nil
}

// ensureSearchIndex 对索引初始化做有界重试。Docker/Colima 内嵌 DNS 在全栈冷
// 启动最初几秒可能对刚接入网络的容器返回瞬时解析失败；不重试会让本服务秒退，
// 而 ES 自身的 readiness 又排在本服务之后，形成「readiness 等索引、索引等
// readiness」的启动死锁。schema 不兼容是确定性结论，重试只会推迟同一个失败，
// 因此不进入重试直接 fail-closed。
func ensureSearchIndex(ctx context.Context, built searchbackend.Built) error {
	err := built.EnsureIndex(ctx)
	for attempt := 1; err != nil && attempt <= 10; attempt++ {
		if errors.Is(err, searchruntimees.ErrIndexSchemaIncompatible) {
			break
		}
		slog.WarnContext(
			ctx,
			"search index initialization retry",
			slog.Int("attempt", attempt),
			slog.Int("max_attempts", 10),
			slog.String("err", err.Error()),
		)
		time.Sleep(3 * time.Second)
		err = built.EnsureIndex(ctx)
	}
	if err != nil {
		if errors.Is(err, searchruntimees.ErrIndexSchemaIncompatible) {
			return fmt.Errorf("search index schema migration failed: %w", err)
		}
		return fmt.Errorf("search index initialization failed: %w", err)
	}
	return nil
}

// mongoStoreDeps 是 Mongo 侧读写模型装配所需的外部构件。
type mongoStoreDeps struct {
	built            searchbackend.Built
	experiments      *searchapplication.Experiments
	messageTransport *runtimemessaging.RedisMessageTransport
	searchSignalPort *signalfactadapter.Appender
	feedbackMetrics  *feedbackmetrics.Recorder
	metricsRecorder  *searchmetrics.Recorder
	logger           *slog.Logger
}

// mongoStores 汇集 Mongo 权威存储派生出的读写模型、投影与消费者。
type mongoStores struct {
	feedbackSink                  feedbackapplication.Sink
	termHeat                      searchapplication.TermHeatProvider
	queryLogSink                  requestapplication.QueryLogSink
	heatStore                     *queryheatstore.Store
	recentFacade                  *recentsearch.Facade
	accountRestrictionProjection  *accountrestrictioninfra.MongoAccountRestrictionProjection
	accountClosureRecovery        *requestapplication.SearchRequestAccountClosureRecoveryCommandFacet
	feedbackSignalRelay           *feedbackstore.SignalRelay
	experimentPolicyConsumer      *experimentpolicymq.ExperimentPolicyConsumer
	accountClosureConsumer        *mqadapter.UserAccountClosedConsumer
	accountRestrictionConsumer    *experimentpolicymq.UserAccountRestrictionConsumer
	userProfileProjectionConsumer *experimentpolicymq.UserProfileSearchProjectionConsumer
}

// assembleMongoStores 装配 query log、feedback、搜索词热力、RecentSearchState、
// 账号处置投影与实验策略投影。Mongo 是它们的权威存储，四环境共用同一套完整
// 生产组合，缺连接由骨架的声明式装配 fail-closed。
func assembleMongoStores(
	asm *servicekit.Assembly, cfg *config, deps mongoStoreDeps,
) (mongoStores, error) {
	ctx := asm.Context
	db := asm.MongoDB
	stores := mongoStores{}

	experimentPolicyStore, err := experimentpolicy.NewMongoStore(db)
	if err != nil {
		return mongoStores{}, fmt.Errorf("experiment policy store init failed: %w", err)
	}
	if err := experimentPolicyStore.EnsureIndexes(ctx); err != nil {
		return mongoStores{}, fmt.Errorf(
			"experiment policy index initialization failed: %w", err,
		)
	}
	if policy, found, err := experimentPolicyStore.Load(
		ctx, searchapplication.SearchRankingExperimentID,
	); err != nil {
		return mongoStores{}, fmt.Errorf("experiment policy restore failed: %w", err)
	} else if found {
		if err := deps.experiments.ApplyPolicy(policy); err != nil {
			return mongoStores{}, fmt.Errorf("stored experiment policy invalid: %w", err)
		}
	}
	stores.experimentPolicyConsumer, err = experimentpolicymq.NewExperimentPolicyConsumer(
		deps.messageTransport,
		experimentPolicyStore,
		deps.experiments,
		asm.Identity.ServiceName+"-"+asm.Identity.InstanceID,
		deps.logger,
	)
	if err != nil {
		return mongoStores{}, fmt.Errorf("experiment policy consumer init failed: %w", err)
	}
	if _, err := stores.experimentPolicyConsumer.ProcessOnce(ctx); err != nil {
		return mongoStores{}, fmt.Errorf(
			"experiment policy initial projection failed: %w", err,
		)
	}

	feedbackStore := feedbackstore.NewStore(db)
	queryStore := querylogstore.NewStore(db)
	indexCtx, indexCancel := context.WithTimeout(ctx, 30*time.Second)
	defer indexCancel()
	if err := feedbackStore.EnsureIndexes(indexCtx); err != nil {
		return mongoStores{}, fmt.Errorf(
			"search feedback index initialization failed: %w", err,
		)
	}
	if err := queryStore.EnsureIndexes(indexCtx); err != nil {
		return mongoStores{}, fmt.Errorf(
			"search query index initialization failed: %w", err,
		)
	}
	stores.feedbackSink = feedbackStore
	stores.queryLogSink = queryStore
	stores.feedbackSignalRelay, err = feedbackstore.NewSignalRelay(
		feedbackStore,
		deps.searchSignalPort,
		deps.feedbackMetrics,
		deps.logger,
	)
	if err != nil {
		return mongoStores{}, fmt.Errorf("feedback signal relay init failed: %w", err)
	}
	stores.heatStore = queryheatstore.NewStore(db, feedbackStore, queryheat.Config{}, deps.logger)
	// Hot-query related-terms cache: collapses the per-search Mongo read for
	// repeated hot queries into one read per key per TTL window (backpressure
	// on the Mongo side under concurrency). Best-effort, read-through.
	stores.termHeat = searchapplication.NewCachedTermHeat(
		stores.heatStore,
		time.Duration(cfg.Serving.RelatedTermsCacheTTLMs)*time.Millisecond,
		cfg.Serving.RelatedTermsCacheMax,
		deps.metricsRecorder,
	)

	recentStore := recentsearchstore.NewStore(db)
	if err := recentStore.EnsureIndexes(ctx); err != nil {
		return mongoStores{}, fmt.Errorf(
			"recent search index initialization failed: %w", err,
		)
	}
	stores.recentFacade, err = recentsearch.NewFacade(recentStore)
	if err != nil {
		return mongoStores{}, fmt.Errorf("recent search facade init failed: %w", err)
	}

	stores.accountRestrictionProjection, err =
		accountrestrictioninfra.NewMongoAccountRestrictionProjection(db)
	if err != nil {
		return mongoStores{}, fmt.Errorf(
			"user account restriction projection init failed: %w", err,
		)
	}
	accountClosureProjection, err := accountclosureinfra.NewMongoProjection(
		db,
		stores.accountRestrictionProjection,
		recentStore,
		feedbackStore,
	)
	if err != nil {
		return mongoStores{}, fmt.Errorf("UserAccountClosed projection init failed: %w", err)
	}
	if err := accountClosureProjection.EnsureIndexes(ctx); err != nil {
		return mongoStores{}, fmt.Errorf("UserAccountClosed projection indexes failed: %w", err)
	}
	if err := stores.accountRestrictionProjection.EnsureIndexes(ctx); err != nil {
		return mongoStores{}, fmt.Errorf(
			"user account restriction projection indexes failed: %w", err,
		)
	}

	userProfileProjection, err := userprofileinfra.NewMongoUserProfileSearchProjection(
		db,
		searchruntimees.NewIndexer(deps.built.Client, deps.built.Client.WriteIndexName()),
	)
	if err != nil {
		return mongoStores{}, fmt.Errorf(
			"UserProfile search projection init failed: %w", err,
		)
	}
	if err := userProfileProjection.EnsureIndexes(ctx); err != nil {
		return mongoStores{}, fmt.Errorf(
			"UserProfile search projection indexes failed: %w", err,
		)
	}
	stores.userProfileProjectionConsumer, err =
		experimentpolicymq.NewUserProfileSearchProjectionConsumer(
			deps.messageTransport,
			userProfileProjection,
			asm.Identity.ServiceName+"-user-profile-projection-"+asm.Identity.InstanceID,
			deps.logger,
		)
	if err != nil {
		return mongoStores{}, fmt.Errorf(
			"UserProfile search projection consumer init failed: %w", err,
		)
	}
	stores.accountClosureConsumer, err = mqadapter.NewUserAccountClosedConsumer(
		deps.messageTransport,
		accountClosureProjection,
		accountClosureProjection,
		asm.Identity.ServiceName+"-"+asm.Identity.InstanceID,
		deps.logger,
		mqadapter.DefaultUserAccountClosedConsumerConfig(),
	)
	if err != nil {
		return mongoStores{}, fmt.Errorf("UserAccountClosed consumer init failed: %w", err)
	}
	stores.accountRestrictionConsumer, err =
		experimentpolicymq.NewUserAccountRestrictionConsumer(
			deps.messageTransport,
			stores.accountRestrictionProjection,
			asm.Identity.ServiceName+"-search-index-restriction-"+asm.Identity.InstanceID,
			deps.logger,
		)
	if err != nil {
		return mongoStores{}, fmt.Errorf("account restriction consumer init failed: %w", err)
	}
	stores.accountClosureRecovery, err =
		requestapplication.NewSearchRequestAccountClosureRecoveryCommandFacet(
			stores.accountClosureConsumer,
		)
	if err != nil {
		return mongoStores{}, fmt.Errorf(
			"UserAccountClosed recovery facet init failed: %w", err,
		)
	}
	if err := stores.accountClosureConsumer.EnsureGroup(ctx); err != nil {
		return mongoStores{}, fmt.Errorf(
			"UserAccountClosed consumer group init failed: %w", err,
		)
	}
	if err := stores.accountRestrictionConsumer.EnsureGroup(ctx); err != nil {
		return mongoStores{}, fmt.Errorf(
			"account restriction consumer group init failed: %w", err,
		)
	}
	if err := stores.userProfileProjectionConsumer.EnsureGroup(ctx); err != nil {
		return mongoStores{}, fmt.Errorf(
			"UserProfile search projection consumer group init failed: %w", err,
		)
	}
	deps.logger.InfoContext(
		ctx,
		"search feedback/query-log + term-heat + recent-search enabled",
		slog.String("database", cfg.Mongo.Database),
	)
	return stores, nil
}

// assembleIntersectionAttacher 装配「搜索结果为什么与我相关」的交集读取：
// 凭据是委派 persona 的最小 scope，交集失败按 best-effort 省略，不放大为搜索
// 失败。
func assembleIntersectionAttacher(
	asm *servicekit.Assembly,
	cfg *config,
	logger *slog.Logger,
	metricsRecorder *searchmetrics.Recorder,
) (*searchapplication.IntersectionAttacher, error) {
	contentAuthorization, err := asm.Auth.DelegatedPersonaCredentials(
		"content.object_intersections.read",
	)
	if err != nil {
		return nil, fmt.Errorf("content intersection credential init failed: %w", err)
	}
	intersectionReader, err := intersectionclient.New(intersectionclient.Config{
		BaseURL:       strings.TrimSpace(cfg.ContentService.BaseURL),
		Authorization: contentAuthorization,
	})
	if err != nil {
		return nil, fmt.Errorf("content intersection reader init failed: %w", err)
	}
	return searchapplication.NewIntersectionAttacher(
		intersectionReader,
		searchapplication.IntersectionAttacherConfig{
			Timeout:       300 * time.Millisecond,
			MaxHits:       8,
			MaxConcurrent: 4,
			ReasonLimit:   1,
		},
		logger,
		metricsRecorder,
	), nil
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
}
