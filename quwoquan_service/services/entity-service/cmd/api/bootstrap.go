package bootstrap

import (
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"gopkg.in/yaml.v3"

	"quwoquan_service/runtime/servicekit"

	entitycomposition "quwoquan_service/services/entity-service/cmd/internal/composition"
	httpadapter "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/adapters/inbound/http"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
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

// config 是 entity-service 的声明式配置：通用段内嵌 servicekit.BaseConfig，
// 装配骨架由 servicekit.Bootstrap 承担（DEC-028）。
//
// Redis 只声明 general 一个 scene，与本服务 generated message transport
// binding 的 RequiredRedisScenes 逐字一致；scene 名取 yaml tag，由「声明即装配」
// 直接发现，不再另设 RedisScenes 映射钩子。
type config struct {
	servicekit.BaseConfig `yaml:",inline"`

	Mongo struct {
		URI      string `yaml:"uri" env:"MONGO_URI" required:"true"`
		Database string `yaml:"database" env:"MONGO_DATABASE" required:"true"`
	} `yaml:"mongo"`

	Redis struct {
		General servicekit.RedisSceneConfig `yaml:"general" envPrefix:"REDIS_GENERAL"`
	} `yaml:"redis"`

	ES searchitemindex.ESConfig `yaml:"es"`

	ContentService struct {
		BaseURL                 string `yaml:"base_url" envAbsolute:"CONTENT_SERVICE_BASE_URL"`
		ObjectIntersectionsPath string `yaml:"object_intersections_path" envAbsolute:"CONTENT_SERVICE_OBJECT_INTERSECTIONS_PATH"`
	} `yaml:"content_service"`
}

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定
// 键集不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix("entity-service"), &config{})
}

// retiredEnvKeys 列出被 scene 专属键取代的注入键。它们一旦被继续注入却无人
// 读取，general scene 就会缺地址并回落进程内存——多副本各自持有一份不共享、
// 重启即丢的「Redis」，而 homepage 的跨服务事实流全部建立在跨副本可见的前提
// 上。拒收给出的是「这个键名已经没有读取点」这条准确信息，比让部署面继续注入
// 一个无效键、再由准入判据报一句缺地址更接近修复位置。
func retiredEnvKeys() []string {
	return []string{
		"ENTITY_REDIS_MODE",
		"ENTITY_REDIS_ADDR",
		"ENTITY_REDIS_ADDRS",
		"ENTITY_REDIS_PASSWORD",
		"ENTITY_REDIS_DB",
		"ENTITY_REDIS_TLS",
	}
}

// snapshotGuard 拒收仍带扁平 redis 段或 rec scene 的渲染快照。
//
// 扁平形态（redis.addr / redis.mode / ...）在 scene 化之后没有任何读取点：
// yaml 解码会把整段丢弃，每个 scene 落到 Go 零值，而零值恰好是「未声明 mode
// 且无地址」这条合法的 memory 回落，没有任何运行期信号。rec 同理——本服务的
// generated message transport binding 四环境都只声明 general，一个没有消费点的
// scene 声明只会成为下一次静默失效的温床。
func snapshotGuard(raw []byte) error {
	var document struct {
		Redis map[string]any `yaml:"redis"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		return fmt.Errorf("parse config snapshot for retired redis shape: %w", err)
	}
	for _, retired := range []string{
		"mode", "addr", "addrs", "password", "db", "tls", "pool",
	} {
		if _, found := document.Redis[retired]; found {
			return fmt.Errorf(
				"redis.%s is retired; declare redis.general.* per scene", retired,
			)
		}
	}
	if _, found := document.Redis["rec"]; found {
		return fmt.Errorf(
			"redis.rec is retired; entity-service consumes only the general scene",
		)
	}
	return nil
}

// NewModule assembles entity-service's private dependencies and HTTP contract.
// The process host owns binding, worker lifetime, readiness admission and
// shutdown.
func NewModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap("entity-service", servicekit.BootstrapSpec[config]{
		OperationDescriptors: entityguard.Descriptors(),
		AuthorityScopes:      []string{"user.account.security.read"},
		// entity 不提供设备票据认证能力：不装配 verifier，带票据的请求
		// 仍由中间件 fail-closed 拒绝。
		SkipDeviceTicketAuth: true,
		// entity 按 runtime boundary 判定 operation 契约，不是 public boundary。
		OperationGuard: func(servicekit.Identity) (
			func(http.Handler) http.Handler, error,
		) {
			return entityguard.Handler, nil
		},
		RetiredEnvKeys: retiredEnvKeys(),
		SnapshotGuard:  snapshotGuard,
		Assemble:       assembleEntityDomain,
	})
}

// requireRealRedisOutsideAlpha 是本服务对 general scene 的准入判据：非 alpha
// 环境回落进程内存即 fail-closed。
//
// 配置快照给 mode 的默认值就是 standalone，所以骨架读到「standalone 且无
// addr」时无法区分「要求单点组网」与「本环境不接 Redis」，只能回落 memory
// （servicekit OPEN-013）。也就是说，缺 ENTITY_REDIS_GENERAL_ADDR 在骨架层
// 没有任何信号，只有这条判据能拦住它：message transport 的物理组网只由环境
// 装配注入，静默回落 memory 会让 homepage 的跨服务事实流整体丢失。
func requireRealRedisOutsideAlpha(sceneMode string, appEnv string) error {
	if sceneMode == "memory" && strings.TrimSpace(appEnv) != "alpha" {
		return fmt.Errorf(
			"ENTITY_REDIS_GENERAL_ADDR is required for message transport when APP_ENV=%s",
			appEnv,
		)
	}
	return nil
}

func assembleEntityDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context
	appEnv := asm.Identity.AppEnv

	if err := requireRealRedisOutsideAlpha(asm.RedisSceneModes["general"], appEnv); err != nil {
		return err
	}
	messageTransport, err := requireEntityAPIMessageTransport(
		ctx,
		appEnv,
		asm.RedisRouter,
		asm.RedisSceneModes,
	)
	if err != nil {
		return fmt.Errorf("message transport preflight failed: %w", err)
	}

	mongoDatabase, err := asm.Mongo(servicekit.MongoConfig{
		URI:      cfg.Mongo.URI,
		Database: cfg.Mongo.Database,
	})
	if err != nil {
		return err
	}
	mongoHomepageStore := homepagepersistence.NewMongoHomepageStore(mongoDatabase)
	if err := mongoHomepageStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("homepage indexes failed: %w", err)
	}
	var homepageStore application.HomepageDataStore = mongoHomepageStore
	reviewStore := reviewpersistence.NewMongoReviewStore(mongoDatabase)
	if err := reviewStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("homepage review indexes failed: %w", err)
	}
	claimStore := claimpersistence.NewMongoStore(mongoDatabase)
	if err := claimStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("homepage claim indexes failed: %w", err)
	}
	statusReportStore := statuspersistence.NewMongoStore(mongoDatabase)
	if err := statusReportStore.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("homepage status report indexes failed: %w", err)
	}

	// Assemble the write-time search index. ES endpoints/credentials come from the
	// shared SEARCH_ES_* env (same cluster/index as search-service); when ES is
	// disabled Build returns a no-op Built and the homepage service runs without a
	// projector, so the primary write path is unaffected.
	searchitemindex.ApplyESEnvOverrides(&cfg.ES)
	searchBuilt, err := searchitemindex.Build(cfg.ES)
	if err != nil {
		return fmt.Errorf("search index build failed: %w", err)
	}
	if err := searchBuilt.EnsureIndex(ctx); err != nil {
		// SearchIndexView is a derived projection. Keep Homepage commands
		// available during a transient ES outage and surface the dependency via
		// healthz; projector/backfill repairs the projection after recovery.
		log.Printf("WARN: entity-service search index ensure failed: %v", err)
	}
	if ping := searchBuilt.HealthPing(); ping != nil {
		asm.Health.Register("elasticsearch", ping)
	}

	var serviceOpts []application.HomepageServiceOption
	var searchItemProjection application.Projector
	if searchBuilt.Indexer != nil {
		searchItemIndex := searchitempersistence.NewESIndex(searchBuilt.Indexer, mongoDatabase)
		if err := searchItemIndex.EnsureIndexes(ctx); err != nil {
			return fmt.Errorf("homepage search item indexes failed: %w", err)
		}
		searchItemProjection = entitycomposition.NewHomepageSearchItemProjection(searchItemIndex)
		serviceOpts = append(serviceOpts, application.WithProjector(searchItemProjection))
	}
	if strings.TrimSpace(cfg.ContentService.BaseURL) != "" {
		contentCredentials, credentialErr := asm.Auth.DelegatedPersonaCredentials(
			"content.object_intersections.read",
		)
		if credentialErr != nil {
			return fmt.Errorf("content credential init failed: %w", credentialErr)
		}
		intersectionReader, readerErr := homepageexternal.NewContentIntersectionReader(
			homepageexternal.ContentIntersectionConfig{
				BaseURL:                 cfg.ContentService.BaseURL,
				ObjectIntersectionsPath: cfg.ContentService.ObjectIntersectionsPath,
				Authorization:           contentCredentials,
			},
		)
		if readerErr != nil {
			return fmt.Errorf("content intersection reader failed: %w", readerErr)
		}
		serviceOpts = append(serviceOpts, application.WithIntersectionReader(intersectionReader))
	}
	homepageService := application.NewHomepageServiceWithStore(ctx, homepageStore, serviceOpts...)
	homepageLifecycleHandler := application.NewHomepageLifecycleHandler(homepageService)
	projectionRunners := []namedProjectionRunner{}
	if searchItemProjection != nil {
		searchRelay, relayErr := application.NewHomepageSearchRelay(
			homepageStore,
			searchItemProjection,
		)
		if relayErr != nil {
			return fmt.Errorf("homepage search relay failed: %w", relayErr)
		}
		projectionRunners = append(projectionRunners, namedProjectionRunner{
			name: "homepage-search", runner: searchRelay,
		})
	}

	claimFacade, err := claimapp.NewFacade(claimapp.DataPorts{
		Aggregates: claimStore,
		Receipts:   claimStore,
		Homepages:  entitycomposition.NewHomepageClaimGate(homepageService),
		Queue:      claimStore,
	})
	if err != nil {
		return fmt.Errorf("homepage claim facade failed: %w", err)
	}
	claimProjector, err := application.NewClaimHomepageProjector(
		claimStore,
		homepageLifecycleHandler,
	)
	if err != nil {
		return fmt.Errorf("homepage claim projector failed: %w", err)
	}
	projectionRunners = append(projectionRunners, namedProjectionRunner{
		name: "homepage-claim", runner: claimProjector,
	})

	statusFacade, err := statusapp.NewFacade(statusapp.DataPorts{
		Aggregates: statusReportStore,
		Receipts:   statusReportStore,
		Homepages:  homepageService,
		Queue:      statusReportStore,
	})
	if err != nil {
		return fmt.Errorf("homepage status report facade failed: %w", err)
	}
	statusProjector, err := application.NewStatusHomepageProjector(
		statusReportStore,
		homepageService,
	)
	if err != nil {
		return fmt.Errorf("homepage status projector failed: %w", err)
	}
	projectionRunners = append(projectionRunners, namedProjectionRunner{
		name: "homepage-status", runner: statusProjector,
	})

	// SubjectFollowStateChanged 消费：homepage 关注真相源在 user.SubjectFollow，
	// 本服务只投影 viewerFollowsHomepage / followerCount。启动前已将 generated
	// runtime.message.transport root 解析为唯一的生产消息 transport。
	followConsumer := followconsumer.NewConsumer(
		messageTransport,
		homepageService,
		asm.Identity.InstanceID,
	)
	asm.Workers.Add(followConsumer.Run)

	homepageStreamRelay, err := homepageapp.NewLifecycleOutboxRelay(
		homepageStore,
		entitymessaging.NewHomepageLifecycleStreamPublisher(messageTransport),
	)
	if err != nil {
		return fmt.Errorf("homepage lifecycle stream relay failed: %w", err)
	}
	projectionRunners = append(projectionRunners, namedProjectionRunner{
		name: "homepage-lifecycle-stream", runner: homepageStreamRelay,
	})
	claimStreamRelay, err := claimapp.NewLifecycleOutboxRelay(
		claimStore,
		entitymessaging.NewHomepageClaimLifecycleStreamPublisher(messageTransport),
	)
	if err != nil {
		return fmt.Errorf("claim lifecycle stream relay failed: %w", err)
	}
	projectionRunners = append(projectionRunners, namedProjectionRunner{
		name: "homepage-claim-lifecycle-stream", runner: claimStreamRelay,
	})
	statusStreamRelay, err := statusapp.NewLifecycleOutboxRelay(
		statusReportStore,
		entitymessaging.NewHomepageStatusLifecycleStreamPublisher(messageTransport),
	)
	if err != nil {
		return fmt.Errorf("status lifecycle stream relay failed: %w", err)
	}
	projectionRunners = append(projectionRunners, namedProjectionRunner{
		name: "homepage-status-lifecycle-stream", runner: statusStreamRelay,
	})
	log.Printf("entity-service subject follow consumer enabled")

	homepageHostAuthorityEvaluator, err := homepageapp.NewHostAuthorityEvaluator(
		homepageStore,
		time.Now,
	)
	if err != nil {
		return fmt.Errorf("homepage host authority composition failed: %w", err)
	}
	httpHandler := httpadapter.NewHandler(homepageService).
		WithHostAuthorityEvaluator(homepageHostAuthorityEvaluator).
		WithClaimRequestHandler(claimhttp.NewHandler(claimFacade)).
		WithStatusReportHandler(statushttp.NewHandler(statusFacade))

	reviewFacade, err := reviewapp.NewFacade(reviewapp.DataPorts{
		Aggregate: reviewStore,
		Page:      reviewStore,
		Homepage:  homepageService,
	})
	if err != nil {
		return fmt.Errorf("homepage review facade failed: %w", err)
	}
	httpHandler = httpHandler.WithReviewHandler(reviewhttp.NewHandler(reviewFacade))
	reviewRelay, err := reviewapp.NewSummaryRelay(
		reviewStore,
		reviewStore,
		reviewStore,
		homepageLifecycleHandler,
	)
	if err != nil {
		return fmt.Errorf("homepage review summary relay failed: %w", err)
	}
	projectionRunners = append(projectionRunners, namedProjectionRunner{
		name: "homepage-review-summary", runner: reviewRelay,
	})
	reviewPublisher, err := reviewmessaging.NewEventPublisher(messageTransport)
	if err != nil {
		return fmt.Errorf("homepage review event publisher failed: %w", err)
	}
	reviewStreamRelay, err := reviewapp.NewOutboxRelay(
		reviewStore,
		reviewStore,
		reviewPublisher,
		"entity.homepage-review-event-stream",
	)
	if err != nil {
		return fmt.Errorf("homepage review stream relay failed: %w", err)
	}
	projectionRunners = append(projectionRunners, namedProjectionRunner{
		name: "homepage-review-event-stream", runner: reviewStreamRelay,
	})

	for _, start := range projectionWorkerStarts(projectionRunners) {
		asm.Workers.Add(start)
	}
	asm.Mux.Handle("/", httpHandler.Routes())
	return nil
}
