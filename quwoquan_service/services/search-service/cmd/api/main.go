// Package bootstrap owns search-service's private composition for servicehost.
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
	configrelease "quwoquan_service/runtime/configrelease"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
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
	"quwoquan_service/runtime/servicehost"
	recenthttp "quwoquan_service/services/search-service/internal/search/recent_search_state/adapters/inbound/http"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/application"
	recentmetrics "quwoquan_service/services/search-service/internal/search/recent_search_state/infrastructure/metrics"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/infrastructure/persistence"
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

// Module keeps search-service's public HTTP contract and private resources
// together while servicehost owns process lifecycle coordination.
type Module struct {
	configDigest string
	server       *http.Server
	readiness    *rthealth.Checker
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

	// Ranking only owns the search-specific score transform. Experiment policy is
	// projected from Product Ops and never originates in service config.
	Ranking struct {
		TermHeatBoost float64 `yaml:"termHeatBoost"`
	} `yaml:"ranking"`

	ContentService struct {
		BaseURL string `yaml:"baseUrl"`
	} `yaml:"contentService"`
}

// NewModule performs fail-fast service-owned assembly. It does not bind a
// listener, start workers, manage signals, or decide process exit status.
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
		return nil, fmt.Errorf("%s config load failed: %w", serviceName, err)
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
		strings.TrimSpace(
			servicehost.ModuleEnvironmentValue("search-service", "CONFIG_VERSION"),
		),
		strings.TrimSpace(os.Getenv("IMAGE_VERSION")),
	)
	configProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(configProvider)
	if err != nil {
		return nil, fmt.Errorf("%s access token config invalid: %w", serviceName, err)
	}
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		serviceName,
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("%s account security authority credential init failed: %w", serviceName, err)
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
		return nil, fmt.Errorf("%s account security authority config invalid: %w", serviceName, err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return nil, fmt.Errorf("%s access token verifier invalid: %w", serviceName, err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(configProvider)
	if err != nil {
		return nil, fmt.Errorf("%s device ticket config invalid: %w", serviceName, err)
	}
	deviceVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		return nil, fmt.Errorf("%s device ticket verifier invalid: %w", serviceName, err)
	}

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: serviceName, SamplingRatio: 0.1})
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		otelShutdown()
	})

	built, err := searchbackend.Build(cfg.ES)
	if err != nil {
		return nil, fmt.Errorf("%s backend assembly failed: %w", serviceName, err)
	}
	if err := built.EnsureIndex(ctx); err != nil {
		if errors.Is(err, searchruntimees.ErrIndexSchemaIncompatible) {
			return nil, fmt.Errorf("%s search index schema migration failed: %w", serviceName, err)
		}
		return nil, fmt.Errorf("%s search index initialization failed: %w", serviceName, err)
	}

	logger := slog.Default()
	metricsRecorder := searchmetrics.NewRecorder()
	feedbackMetrics := feedbackmetrics.NewRecorder()
	recentMetrics := recentmetrics.NewRecorder()
	redisRouter, messageTransportSceneModes := buildRedisRouter(cfg)
	cleanup = servicehost.ChainCleanup(cleanup, func() {
		_ = redisRouter.Close()
	})
	messageTransport, err := requireSearchAPIMessageTransport(
		ctx,
		appEnv,
		redisRouter,
		messageTransportSceneModes,
	)
	if err != nil {
		return nil, fmt.Errorf("%s message transport construction failed: %w", serviceName, err)
	}
	if err := redisRouter.PingAll(ctx); err != nil {
		return nil, fmt.Errorf("%s redis unavailable: %w", serviceName, err)
	}
	searchSignalPublisher, err := searchsignals.NewStreamPublisher(messageTransport, logger)
	if err != nil {
		return nil, fmt.Errorf("%s search signal publisher init failed: %w", serviceName, err)
	}
	searchSignalAppender, err := signalfactapplication.NewAppender(searchSignalPublisher)
	if err != nil {
		return nil, fmt.Errorf("%s search signal appender init failed: %w", serviceName, err)
	}
	searchSignalPort, err := signalfactadapter.NewAppender(searchSignalAppender)
	if err != nil {
		return nil, fmt.Errorf("%s search signal inbound port init failed: %w", serviceName, err)
	}
	experimentAssignmentPublisher, err := experimentassignment.NewPublisher(messageTransport)
	if err != nil {
		return nil, fmt.Errorf("%s experiment assignment publisher init failed: %w", serviceName, err)
	}
	experiments, err := searchapplication.NewExperiments(experimentAssignmentPublisher)
	if err != nil {
		return nil, fmt.Errorf("%s experiment resolver init failed: %w", serviceName, err)
	}

	// Mongo is authoritative for query logs, feedback facts, term heat,
	// RecentSearchState, and privacy cleanup checkpoints. Every environment uses
	// the same complete production composition.
	var feedbackSink feedbackapplication.Sink
	var termHeat searchapplication.TermHeatProvider
	var queryLogSink requestapplication.QueryLogSink
	var recentFacade *recentsearch.Facade
	var accountClosureConsumer *mqadapter.UserAccountClosedConsumer
	var accountRestrictionConsumer *experimentpolicymq.UserAccountRestrictionConsumer
	var userProfileProjectionConsumer *experimentpolicymq.UserProfileSearchProjectionConsumer
	var accountClosureRecovery *requestapplication.SearchRequestAccountClosureRecoveryCommandFacet
	var accountRestrictionProjection *accountrestrictioninfra.MongoAccountRestrictionProjection
	var feedbackSignalRelay *feedbackstore.SignalRelay
	var experimentPolicyConsumer *experimentpolicymq.ExperimentPolicyConsumer
	var heatStore *queryheatstore.Store
	if strings.TrimSpace(cfg.Mongo.URI) == "" {
		return nil, fmt.Errorf("%s mongo.uri is required", serviceName)
	}
	{
		client, err := rtmongodb.Connect(ctx, rtmongodb.ConnectConfig{
			URI: cfg.Mongo.URI, Database: cfg.Mongo.Database,
		})
		if err != nil {
			return nil, fmt.Errorf("%s mongo connect failed: %w", serviceName, err)
		}
		cleanup = servicehost.ChainCleanup(cleanup, func() {
			_ = client.Disconnect(context.Background())
		})
		db := client.Database(cfg.Mongo.Database)
		experimentPolicyStore, err := experimentpolicy.NewMongoStore(db)
		if err != nil {
			return nil, fmt.Errorf("%s Experiment policy store init failed: %w", serviceName, err)
		}
		if err := experimentPolicyStore.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf("%s Experiment policy index initialization failed: %w", serviceName, err)
		}
		if policy, found, err := experimentPolicyStore.Load(ctx, searchapplication.SearchRankingExperimentID); err != nil {
			return nil, fmt.Errorf("%s Experiment policy restore failed: %w", serviceName, err)
		} else if found {
			if err := experiments.ApplyPolicy(policy); err != nil {
				return nil, fmt.Errorf("%s stored Experiment policy invalid: %w", serviceName, err)
			}
		}
		experimentPolicyConsumer, err = experimentpolicymq.NewExperimentPolicyConsumer(
			messageTransport,
			experimentPolicyStore,
			experiments,
			serviceName+"-"+hostname(),
			logger,
		)
		if err != nil {
			return nil, fmt.Errorf("%s Experiment policy consumer init failed: %w", serviceName, err)
		}
		if _, err := experimentPolicyConsumer.ProcessOnce(ctx); err != nil {
			return nil, fmt.Errorf("%s Experiment policy initial projection failed: %w", serviceName, err)
		}
		feedbackStore := feedbackstore.NewStore(db)
		queryStore := querylogstore.NewStore(db)
		indexCtx, indexCancel := context.WithTimeout(ctx, 30*time.Second)
		if err := feedbackStore.EnsureIndexes(indexCtx); err != nil {
			indexCancel()
			return nil, fmt.Errorf("%s search feedback index initialization failed: %w", serviceName, err)
		}
		if err := queryStore.EnsureIndexes(indexCtx); err != nil {
			indexCancel()
			return nil, fmt.Errorf("%s search query index initialization failed: %w", serviceName, err)
		}
		indexCancel()
		feedbackSink = feedbackStore
		feedbackSignalRelay, err = feedbackstore.NewSignalRelay(
			feedbackStore,
			searchSignalPort,
			feedbackMetrics,
			logger,
		)
		if err != nil {
			return nil, fmt.Errorf(
				"%s feedback signal relay init failed: %v",
				serviceName,
				err,
			)
		}
		queryLogSink = queryStore
		heatStore = queryheatstore.NewStore(
			db,
			feedbackStore,
			queryheat.Config{},
			logger,
		)
		// Hot-query related-terms cache: collapses the per-search Mongo read for
		// repeated hot queries into one read per key per TTL window (backpressure
		// on the Mongo side under concurrency). Best-effort, read-through.
		termHeat = searchapplication.NewCachedTermHeat(heatStore,
			time.Duration(getenvInt("SEARCH_RELATED_TERMS_CACHE_TTL_MS", 2000))*time.Millisecond,
			getenvInt("SEARCH_RELATED_TERMS_CACHE_MAX", 1024),
			metricsRecorder)
		recentStore := recentsearchstore.NewStore(db)
		if err := recentStore.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf(
				"%s recent search index initialization failed: %v",
				serviceName,
				err,
			)
		}
		recentFacade, err = recentsearch.NewFacade(recentStore)
		if err != nil {
			return nil, fmt.Errorf("%s recent search facade init failed: %w", serviceName, err)
		}
		accountRestrictionProjection, err =
			accountrestrictioninfra.NewMongoAccountRestrictionProjection(db)
		if err != nil {
			return nil, fmt.Errorf(
				"%s user account restriction projection init failed: %v",
				serviceName,
				err,
			)
		}
		accountClosureProjection, err := accountclosureinfra.NewMongoProjection(
			db,
			accountRestrictionProjection,
			recentStore,
			feedbackStore,
		)
		if err != nil {
			return nil, fmt.Errorf(
				"%s UserAccountClosed projection init failed: %v",
				serviceName,
				err,
			)
		}
		if err := accountClosureProjection.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf(
				"%s UserAccountClosed projection indexes failed: %v",
				serviceName,
				err,
			)
		}
		if err := accountRestrictionProjection.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf(
				"%s user account restriction projection indexes failed: %v",
				serviceName,
				err,
			)
		}
		userProfileProjection, err :=
			userprofileinfra.NewMongoUserProfileSearchProjection(
				db,
				searchruntimees.NewIndexer(built.Client, built.Client.WriteIndexName()),
			)
		if err != nil {
			return nil, fmt.Errorf("%s UserProfile search projection init failed: %w", serviceName, err)
		}
		if err := userProfileProjection.EnsureIndexes(ctx); err != nil {
			return nil, fmt.Errorf("%s UserProfile search projection indexes failed: %w", serviceName, err)
		}
		userProfileProjectionConsumer, err =
			experimentpolicymq.NewUserProfileSearchProjectionConsumer(
				messageTransport,
				userProfileProjection,
				serviceName+"-user-profile-projection-"+hostname(),
				logger,
			)
		if err != nil {
			return nil, fmt.Errorf("%s UserProfile search projection consumer init failed: %w", serviceName, err)
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
			return nil, fmt.Errorf(
				"%s UserAccountClosed consumer init failed: %v",
				serviceName,
				err,
			)
		}
		accountRestrictionConsumer, err =
			experimentpolicymq.NewUserAccountRestrictionConsumer(
				messageTransport,
				accountRestrictionProjection,
				serviceName+"-search-index-restriction-"+hostname(),
				logger,
			)
		if err != nil {
			return nil, fmt.Errorf(
				"%s account restriction consumer init failed: %v",
				serviceName,
				err,
			)
		}
		accountClosureRecovery, err =
			requestapplication.NewSearchRequestAccountClosureRecoveryCommandFacet(
				accountClosureConsumer,
			)
		if err != nil {
			return nil, fmt.Errorf(
				"%s UserAccountClosed recovery facet init failed: %v",
				serviceName,
				err,
			)
		}
		if err := accountClosureConsumer.EnsureGroup(ctx); err != nil {
			return nil, fmt.Errorf(
				"%s UserAccountClosed consumer group init failed: %v",
				serviceName,
				err,
			)
		}
		if err := accountRestrictionConsumer.EnsureGroup(ctx); err != nil {
			return nil, fmt.Errorf(
				"%s account restriction consumer group init failed: %v",
				serviceName,
				err,
			)
		}
		if err := userProfileProjectionConsumer.EnsureGroup(ctx); err != nil {
			return nil, fmt.Errorf("%s UserProfile search projection consumer group init failed: %w", serviceName, err)
		}
		log.Printf("%s feedback/query-log + term-heat + recent-search enabled (db=%s)", serviceName, cfg.Mongo.Database)
	}

	accountRestrictedBackend, err := searchapplication.NewAccountRestrictionBackend(
		built.Backend,
		accountRestrictionProjection,
	)
	if err != nil {
		return nil, fmt.Errorf("%s account restriction backend init failed: %w", serviceName, err)
	}
	searchCursorCodec, err := searchapplication.NewSearchCursorCodec(accessTokenConfig.Secret)
	if err != nil {
		return nil, fmt.Errorf("%s search cursor codec init failed: %w", serviceName, err)
	}
	searchSvc := searchapplication.NewSearchService(
		accountRestrictedBackend,
		searchapplication.WithSearchCursorCodec(searchCursorCodec),
		// 翻页快照（REQ-007/OPEN-005）：首个后续页惰性 OpenPIT，之后每页续期；
		// 快照失效按 cursor fail-closed，不静默退化为无快照查询。
		searchapplication.WithPaginationSnapshots(built.Client),
	)
	requestFactRecorder := requestapplication.NewRecorder(
		queryLogSink,
		searchSignalPort,
		logger,
	)
	feedbackSvc := feedbackapplication.NewService(feedbackSink)
	decorator := searchapplication.NewRankingDecorator(
		termHeat,
		experiments,
		cfg.Ranking.TermHeatBoost,
		logger,
	)
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
		return nil, fmt.Errorf("%s content intersection credential init failed: %w", serviceName, err)
	}
	intersectionReader, err := intersectionclient.New(intersectionclient.Config{
		BaseURL:       contentBaseURL,
		Authorization: contentAuthorization,
	})
	if err != nil {
		return nil, fmt.Errorf("%s content intersection reader init failed: %w", serviceName, err)
	}
	intersectionAttacher := searchapplication.NewIntersectionAttacher(
		intersectionReader,
		searchapplication.IntersectionAttacherConfig{
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
		return nil, fmt.Errorf("%s runtime log exporter init failed: %w", serviceName, err)
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
		return nil, fmt.Errorf("%s process logger init failed: %w", serviceName, err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		return nil, fmt.Errorf("%s exception logger init failed: %w", serviceName, err)
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
	requesthttp.NewHandler(termHeat).Register(routesMux)
	feedbackhttp.NewHandler(feedbackSvc, feedbackMetrics).Register(routesMux)
	if recentFacade != nil {
		recenthttp.NewRecentSearchHandler(recentFacade, recentMetrics).Register(routesMux)
	}
	var handler http.Handler = routesMux
	// Backpressure: cap concurrent in-flight searches so a slow ES sheds load
	// (typed 503) instead of piling up and collapsing the instance. Aligned with
	// search_slo.yaml#load_model.max_concurrency_per_instance; applied only to the
	// search routes so /healthz and /metrics stay reachable while shedding.
	inflightLimiter := rtgov.NewInflightLimiter(getenvInt("SEARCH_MAX_INFLIGHT", 256))
	searchHandler := httpadapter.MaxInflightMiddleware(inflightLimiter, metricsRecorder)(handler)
	if accountClosureRecovery != nil {
		searchHandler, err = runtimemessaging.WithDeadLetterRecoveryRoute(
			searchHandler,
			runtimemessaging.DeadLetterRecoveryRouteConfig{
				Path:     "/internal/search/account-closure/dead-letters:recover",
				Module:   rterr.ModuleSearch,
				Releaser: accountClosureRecovery,
			},
		)
		if err != nil {
			return nil, fmt.Errorf("%s account-closure recovery route failed: %w", serviceName, err)
		}
	}
	rootMux := http.NewServeMux()
	// Compose liveness stays shallow. Worker / authority / ES readiness stays
	// on /readyz so first-scan Healthy(15s) cannot keep the container unhealthy.
	readiness := rthealth.NewChecker()
	readiness.Register("account-security-authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	if ping := built.HealthPing(); ping != nil {
		readiness.Register("elasticsearch", ping)
	}
	if feedbackSignalRelay != nil {
		readiness.Register(
			"feedback-signal-relay",
			func(hctx context.Context) error {
				return feedbackSignalRelay.Healthy(
					hctx,
					15*time.Second,
				)
			},
		)
	}
	if experimentPolicyConsumer != nil {
		readiness.Register("experiment-policy-consumer", func(context.Context) error {
			return experimentPolicyConsumer.Healthy(15 * time.Second)
		})
	}
	readiness.Register("experiment-policy", func(context.Context) error {
		return experiments.Healthy()
	})
	if accountClosureConsumer != nil {
		readiness.Register(
			"user-account-closed-consumer",
			func(context.Context) error {
				return accountClosureConsumer.Healthy(15 * time.Second)
			},
		)
	}
	if accountRestrictionConsumer != nil {
		readiness.Register(
			"user-account-restriction-consumer",
			func(context.Context) error {
				return accountRestrictionConsumer.Healthy(15 * time.Second)
			},
		)
	}
	if userProfileProjectionConsumer != nil {
		readiness.Register(
			"user-profile-search-projection-consumer",
			func(context.Context) error {
				return userProfileProjectionConsumer.Healthy(15 * time.Second)
			},
		)
	}
	rootMux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	rootMux.HandleFunc("/readyz", readiness.Handler())
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

	timeouts := rtauth.ContractHTTPServerTimeouts(
		operationsecurity.ForDomain("search"),
	)
	server := &http.Server{
		Addr: cfg.Service.HTTP.Addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			DeviceTicketVerifier:     deviceVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(withObs),
		BaseContext:       func(_ net.Listener) context.Context { return ctx },
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
	module := &Module{
		configDigest: strings.TrimSpace(
			servicehost.ModuleEnvironmentValue("search-service", "CONFIG_VERSION"),
		),
		server:     server,
		readiness:  readiness,
		serveError: make(chan error, 1),
		workerStart: []func(context.Context){
			experimentPolicyConsumer.Run,
			feedbackSignalRelay.Run,
			accountClosureConsumer.Run,
			accountRestrictionConsumer.Run,
			userProfileProjectionConsumer.Run,
			func(workerCtx context.Context) {
				startHeatRebuildLoop(workerCtx, heatStore, logger)
			},
		},
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

func (module *Module) Name() string { return serviceName }

func (module *Module) ConfigDigest() string {
	if module == nil {
		return ""
	}
	return module.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.server == nil || module.readiness == nil || module.cleanup == nil {
		return errors.New("search-service module is incomplete")
	}
	return nil
}

func (module *Module) PrepareMigration(context.Context) error {
	return nil
}

func (module *Module) Bind(context.Context) error {
	if module == nil || module.server == nil {
		return errors.New("search-service HTTP server is unavailable")
	}
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("search-service listener bind: %w", err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(ctx context.Context) error {
	if module == nil || module.listener == nil {
		return errors.New("search-service listener is not bound")
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
	if result := module.readiness.Check(ctx); result.Status != "ok" {
		return fmt.Errorf("search-service readiness failed: %v", result.FailedChecks)
	}
	select {
	case err := <-module.serveError:
		return fmt.Errorf("search-service listener failed: %w", err)
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

func generatedSearchOperationHandler(next http.Handler) http.Handler {
	return rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("search"),
	)(next)
}

func loadRuntimeConfig() (config, error) {
	cfg := config{}
	serviceName := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("search-service", "SERVICE_NAME"),
	)
	if serviceName == "" {
		serviceName = "search-service"
	}
	appEnv := getenvOrDefault("APP_ENV", "alpha")
	configRoot := strings.TrimSpace(os.Getenv("CONFIG_ROOT"))
	configVersion := strings.TrimSpace(
		servicehost.ModuleEnvironmentValue("search-service", "CONFIG_VERSION"),
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
