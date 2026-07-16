package main

import (
	"context"
	"database/sql"
	"log"
	"log/slog"
	"net/http"
	"os"
	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtmongo "quwoquan_service/internal/platform/mongodb"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	runtimelearning "quwoquan_service/runtime/learning"
	runtimemedia "quwoquan_service/runtime/media"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	rtrec "quwoquan_service/runtime/recommendation"
	rtrecpolicy "quwoquan_service/runtime/recpolicy"
	rtredis "quwoquan_service/runtime/redis"
	httpadapter "quwoquan_service/services/content-service/internal/adapters/http"
	behaviorapp "quwoquan_service/services/content-service/internal/application/behavior"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	outboundshareapp "quwoquan_service/services/content-service/internal/application/content/outbound_share_fact/command"
	feedapp "quwoquan_service/services/content-service/internal/application/feed"
	importerapp "quwoquan_service/services/content-service/internal/application/importer"
	intersectionapp "quwoquan_service/services/content-service/internal/application/intersection"
	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	"quwoquan_service/services/content-service/internal/application/ports"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
	reportapp "quwoquan_service/services/content-service/internal/application/report"
	mediainfra "quwoquan_service/services/content-service/internal/infrastructure/content/media"
	outboundshareinfra "quwoquan_service/services/content-service/internal/infrastructure/content/outbound_share_fact/persistence"
	"quwoquan_service/services/content-service/internal/infrastructure/intersectionmetrics"
	learninginfra "quwoquan_service/services/content-service/internal/infrastructure/learning"
	"quwoquan_service/services/content-service/internal/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/infrastructure/placeindex"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
	"quwoquan_service/services/content-service/internal/infrastructure/searchindex"
	"strings"
	"time"
)

// redisSceneCfg holds configuration for a single Redis deployment (one logical scene).
type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`  // "standalone" (default) | "cluster"
	Addr     string   `yaml:"addr"`  // standalone: host:port
	Addrs    []string `yaml:"addrs"` // cluster: [host:port, ...]
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`  // cluster mode ignores this
	TLS      bool     `yaml:"tls"` // set true for Alibaba Cloud / VeCache public endpoints
	Pool     struct {
		Size           int `yaml:"size"`     // 0 = auto
		MinIdle        int `yaml:"min_idle"` // 0 = auto
		ReadTimeoutMs  int `yaml:"read_timeout_ms"`
		WriteTimeoutMs int `yaml:"write_timeout_ms"`
		DialTimeoutMs  int `yaml:"dial_timeout_ms"`
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
	Mongo struct {
		URI        string `yaml:"uri"`
		Database   string `yaml:"database"`
		Collection string `yaml:"collection"`
	} `yaml:"mongo"`
	Postgres struct {
		ReportDSN string `yaml:"report_dsn"`
	} `yaml:"postgres"`

	// Redis scenes:
	//   rec     — recommendation hot path (session signals, exposed, negative)
	//   general — entity cache, assistant context, rate limiting (reserved)
	Redis struct {
		Rec      redisSceneCfg `yaml:"rec"`
		General  redisSceneCfg `yaml:"general"`
		Realtime redisSceneCfg `yaml:"realtime"`
	} `yaml:"redis"`

	RecModelService struct {
		URL       string `yaml:"url"`
		TimeoutMs int    `yaml:"timeout_ms"`
		Enabled   bool   `yaml:"enabled"`
	} `yaml:"rec_model_service"`

	Embedding struct {
		Endpoint string `yaml:"endpoint"`
		APIKey   string `yaml:"api_key"`
		Model    string `yaml:"model"`
		Enabled  bool   `yaml:"enabled"`
	} `yaml:"embedding"`

	OSS struct {
		Endpoint        string `yaml:"endpoint"`
		Bucket          string `yaml:"bucket"`
		Region          string `yaml:"region"`
		AccessKeyID     string `yaml:"access_key_id"`
		AccessKeySecret string `yaml:"access_key_secret"`
		CDNDomain       string `yaml:"cdn_domain"`
		CDNSignKey      string `yaml:"cdn_sign_key"`
		PresignTTLMin   int    `yaml:"presign_ttl_minutes"`
		CDNTTLMin       int    `yaml:"cdn_ttl_minutes"`
		UseSSL          bool   `yaml:"use_ssl"`
	} `yaml:"oss"`

	// ES is the write side of the unified search index (content.search_index_worker).
	// Endpoints/credentials are injected per-env via the shared SEARCH_ES_* env so
	// content-service and search-service target the same cluster/index. Disabled by
	// default; when off the search-index projector is a no-op and the write path is
	// unaffected.
	ES searchindex.ESConfig `yaml:"es"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("content-service runtime identity invalid: %v", err)
	}

	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("content-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("content-service config compatibility failed: %v", err)
	}
	if err := preflightConfig(cfg, appEnv); err != nil {
		log.Fatalf("content-service config preflight failed: %v", err)
	}

	ctx := context.Background()

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "content-service", SamplingRatio: 0.1})
	defer otelShutdown()

	addr := getenvOrDefault("CONTENT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18080"
	}

	logger := slog.Default()
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())

	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, "info", nil)
	if err != nil {
		log.Fatalf("content-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("content-service exception logger init failed: %v", err)
	}

	router := buildRedisRouter(cfg)
	defer router.Close()
	if err := router.PingAll(ctx); err != nil {
		log.Printf("WARN: content-service redis ping: %v", err)
	}
	hotPath := rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec")))
	eventPub := messaging.NewRedisEventPublisher(router.Scene("general"), "content-service", logger)
	behaviorEventPub := runtimemessaging.EventPublisher(eventPub)

	// Read path: SessionCache wraps HotPath with L1 cache + singleflight
	sessionCache := rtrec.NewSessionCache(hotPath, 2*time.Second, 10000)

	// Write path: BufferedHotPath wraps HotPath with async channel
	bufferedWriter := rtrec.NewBufferedHotPath(hotPath, rtrec.WithBufferLogger(logger))
	defer bufferedWriter.Stop()

	// SIT6 商用装配：Mongo/PostgreSQL/OSS 均为启动必需依赖，不存在内存降级。
	var store *persistence.MongoPostStore
	var postQueryReader *persistence.MongoPostQueryReader
	var reactionStore *persistence.MongoContentReactionStore
	var reactionServiceCore *reactionapp.Service
	var commentDataAdapter *persistence.MongoCommentDataAdapter
	var commentServiceCore *commentapp.CommentService
	var outboundShareFacades *outboundshareapp.Facades
	var reportStore *persistence.PGReportStore
	var postServiceOpts []postapp.PostServiceOption
	var mediaStore *persistence.MongoMediaStore
	var mongoCandidateSources []rtrec.CandidateSource
	var bulkImportService *importerapp.BulkImportService
	var behaviorEventStore ports.BehaviorEventStore
	var wishlistEventStore ports.WishlistEventStore
	var dailyMetricsStore *persistence.DailyMetricsStore
	var authorImpactStore *persistence.AuthorImpactStore
	var authorImpactEvidenceStore *persistence.AuthorImpactEvidenceStore
	var intersectionService *intersectionapp.IntersectionService
	recOpts := []rtrec.EngineOption{
		rtrec.WithRecallTimeout(150 * time.Millisecond),
		rtrec.WithLogger(logger),
	}
	var learningSink runtimelearning.Sink
	postServiceOpts = append(postServiceOpts, postapp.WithSignalProcessor(bufferedWriter))
	postServiceOpts = append(postServiceOpts, postapp.WithLogger(logger))
	postServiceOpts = append(postServiceOpts, postapp.WithStoryRuntimeConfig(resolveStoryRuntimeConfig()))

	healthChecker := rthealth.NewChecker()
	healthChecker.Register("redis", func(hctx context.Context) error {
		return router.PingAll(hctx)
	})

	mongoURI := resolveMongoURI(cfg)
	if mongoURI != "" {
		mongoClient := rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: mongoURI}, "content-service")
		healthChecker.Register("mongodb", func(hctx context.Context) error {
			return mongoClient.Ping(hctx, nil)
		})
		defer func() {
			shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			_ = mongoClient.Disconnect(shutdownCtx)
		}()
		dbName := cfg.Mongo.Database
		if dbName == "" {
			dbName = "quwoquan_content"
		}
		collName := cfg.Mongo.Collection
		if collName == "" {
			collName = "posts"
		}
		db := mongoClient.Database(dbName)
		mongoStore := persistence.NewMongoPostStore(db.Collection(collName))
		if err := mongoStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service post indexes init failed: %v", err)
		}
		store = mongoStore
		postQueryReader = persistence.NewMongoPostQueryReader(db.Collection(collName))
		outboundShareSink := outboundshareinfra.NewMongoAppendSink(db)
		if err := outboundShareSink.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service OutboundShareFact indexes init failed: %v", err)
		}
		outboundShareFacades = outboundshareapp.BindFacades(outboundshareapp.NewService(
			outboundShareSink,
			outboundshareinfra.NewShareablePostReader(postQueryReader),
		))
		mediaStore = persistence.NewMongoMediaStore(db.Collection("media_upload_sessions"))
		if err := mediaStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service MediaUploadSession/MediaAsset indexes init failed: %v", err)
		}
		commentDataAdapter = persistence.NewMongoCommentDataAdapter(db)
		if err := commentDataAdapter.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service Comment indexes init failed: %v", err)
		}
		postServiceOpts = append(postServiceOpts, postapp.WithCommentReaders(commentDataAdapter))
		startCommentOutboxRelay(
			ctx, commentDataAdapter, commentDataAdapter,
			messaging.NewCommentOutboxPublisher(eventPub),
			"content-comment-runtime-events", "content_comment_outbox_events",
			healthChecker, logger,
		)
		startCommentOutboxRelay(
			ctx, commentDataAdapter, commentDataAdapter,
			commentapp.NewCommentCountProjector(commentDataAdapter, mongoStore),
			"content-comment-post-count", "content_comment_post_count",
			healthChecker, logger,
		)
		reactionStore = persistence.NewMongoContentReactionStore(db)
		if err := reactionStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service ContentReaction indexes init failed: %v", err)
		}
		postServiceOpts = append(postServiceOpts, postapp.WithProfileReactionActivityReader(reactionStore))
		postServiceOpts = append(postServiceOpts, postapp.WithProfileCommentReactionValueReader(reactionStore))
		reactionServiceCore = reactionapp.NewService(
			reactionapp.BindDataPorts(
				reactionStore,
				persistence.NewReactionTargetReader(postQueryReader, commentDataAdapter),
			),
		)
		startPostOutboxRelay(
			ctx,
			store,
			store,
			reactionapp.NewPostDeletionConsumer(reactionServiceCore, reactionStore),
			"content-post-deletion-reaction-lifecycle",
			"content_post_deletion_reaction_lifecycle",
			healthChecker,
			logger,
		)
		startReactionOutboxRelay(
			ctx,
			reactionStore,
			reactionStore,
			messaging.NewContentReactionOutboxPublisher(eventPub),
			"content-reaction-runtime-events",
			"content_reaction_outbox_events",
			healthChecker,
			logger,
		)
		startReactionOutboxRelay(
			ctx,
			reactionStore,
			reactionStore,
			reactionapp.NewActiveReactionCountProjector(reactionStore, mongoStore),
			"content-reaction-post-like-count",
			"content_reaction_post_like_count",
			healthChecker,
			logger,
		)
		startReactionOutboxRelay(
			ctx,
			reactionStore,
			reactionStore,
			reactionapp.NewActiveReactionCountProjector(
				reactionStore,
				persistence.NewMongoDiscoveryFeedLikeCountWriter(db),
			),
			"content-reaction-discovery-like-count",
			"content_reaction_discovery_like_count",
			healthChecker,
			logger,
		)
		startReactionOutboxRelay(
			ctx,
			reactionStore,
			reactionStore,
			reactionapp.NewPersonaLikeCountProjector(
				reactionStore,
				persistence.NewMongoRecommendFeatureLikeCountWriter(db),
			),
			"content-reaction-recommend-like-count",
			"content_reaction_recommend_like_count",
			healthChecker,
			logger,
		)
		log.Printf("content-service storage=mongodb db=%s collection=%s", dbName, collName)

		learningSink = learninginfra.NewMongoSink(db, logger)

		shareInteractionStore := persistence.NewMongoShareInteractionStore(db, logger)
		postServiceOpts = append(postServiceOpts,
			postapp.WithShareInteractionStore(shareInteractionStore),
		)
		log.Printf("content-service interaction storage=mongodb (Comment aggregate + ContentReaction aggregate + rm_profile_share_interactions)")

		// Entity tag index for entity interest propagation in projector
		entityTagIndex := recinfra.NewMongoEntityTagIndex(db)
		entityPropagation := rtrec.NewEntityInterestPropagation(entityTagIndex)

		// In-process projectors: discovery feed + recommendation features.
		discoveryProjector := recinfra.NewDiscoveryFeedProjector(db)
		// Rule-based segment SSOT, loaded from segments.yaml (env-overridable
		// path). Population definitions stay a separate SSOT from policy.yaml
		// (scoring strategy); the engine reads resolved memberships from
		// rm_recommend_feature.segments. Load failure degrades membership only.
		segmentsPath := os.Getenv("QWQ_SEGMENTS_PATH")
		if segmentsPath == "" {
			segmentsPath = "contracts/metadata/recommendation/rec_model/segments.yaml"
		}
		segDefs, segErr := recinfra.LoadSegments(segmentsPath)
		if segErr != nil {
			log.Printf("WARN: load segment definitions from %s: %v (segment membership disabled)", segmentsPath, segErr)
		}
		interestAgg := recinfra.NewInterestProfileAggregator(db, recinfra.DefaultInterestProfileConfig(), eventPub, recinfra.WithSegments(segDefs))
		recommendProjector := recinfra.NewRecommendFeatureProjector(db, recinfra.WithEntityPropagation(entityPropagation), recinfra.WithSignalProcessor(bufferedWriter), recinfra.WithInterestAggregator(interestAgg))
		relationshipProjection := recinfra.NewPersonaRelationshipProjection(db)
		if err := relationshipProjection.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service persona relationship projection startup failed: %v", err)
		}
		go recinfra.NewPersonaRelationshipProjectionConsumer(
			router.Scene("general"), relationshipProjection, instanceID, logger,
		).Run(ctx, 500*time.Millisecond)
		premiumPoolProjector := recinfra.NewPremiumPoolProjector(db)
		go recinfra.NewPremiumPoolEventConsumer(router.Scene("general"), premiumPoolProjector, logger).Run(ctx)
		searchSignalConsumer := recinfra.NewSearchSignalConsumer(router.Scene("general"), recommendProjector, instanceID, logger)
		go searchSignalConsumer.Run(ctx, 500*time.Millisecond)

		// Write-time search index projector (content.search_index_worker). Disabled
		// when ES is off (alpha): Built is empty and the projector is nil, so the
		// write path is unaffected. When enabled we ensure the shared index exists
		// up front so increments have somewhere to land, and register a liveness ping.
		searchBuilt, searchErr := searchindex.Build(cfg.ES, store, searchindex.WithLogger(logger))
		if searchErr != nil {
			log.Printf("WARN: content-service search index assembly failed (search indexing disabled): %v", searchErr)
		}
		// First-party place projector (R-S05e): location.place objects reuse the
		// SAME ES indexer (one geo mechanism, one client) and a derived
		// place_snapshots store. Built only when ES is enabled, so alpha is
		// unaffected.
		var placeProjector *placeindex.PlaceProjector
		if searchBuilt.Client != nil {
			healthChecker.Register("elasticsearch", searchBuilt.HealthPing())
			if err := searchBuilt.EnsureIndex(ctx); err != nil {
				log.Printf("WARN: content-service ensure ES search index failed: %v", err)
			}
			placeStore := placeindex.NewMongoPlaceStore(db.Collection(placeindex.PlaceSnapshotCollection), logger)
			placeProjector = placeindex.NewProjector(searchBuilt.Indexer, store, placeStore, placeindex.WithLogger(logger))
			log.Printf("content-service search index projector enabled (es endpoints=%d index=%s, place objects on)", len(cfg.ES.Endpoints), searchBuilt.Client.IndexName())
		}
		// Each derived read model and the external event bus owns an independent
		// durable checkpoint. A late sink outage therefore cannot replay sinks
		// that already converged, and a failed sink never gets acknowledged by a
		// shared fan-out watermark.
		startPostOutboxRelay(ctx, store, store,
			messaging.NewPostOutboxPublisher(eventPub),
			"content-runtime-events", "post_outbox_events", healthChecker, logger)
		startPostOutboxRelay(ctx, store, store,
			messaging.NewPostLifecycleStreamPublisher(router.Scene("general")),
			"content-post-lifecycle-stream", "post_outbox_lifecycle_stream", healthChecker, logger)
		startPostOutboxRelay(ctx, store, store,
			messaging.NewPostOutboxPublisher(messaging.NewInProcessProjectorPublisher(
				&projectorAdapter{discovery: discoveryProjector},
			)),
			"content-discovery-projection", "post_outbox_discovery", healthChecker, logger)
		startPostOutboxRelay(ctx, store, store,
			messaging.NewPostOutboxPublisher(messaging.NewInProcessProjectorPublisher(
				&projectorAdapter{recommend: recommendProjector},
			)),
			"content-recommend-projection", "post_outbox_recommend", healthChecker, logger)
		startPostOutboxRelay(ctx, store, store,
			messaging.NewPostOutboxPublisher(messaging.NewInProcessProjectorPublisher(
				&projectorAdapter{premium: premiumPoolProjector},
			)),
			"content-premium-projection", "post_outbox_premium", healthChecker, logger)
		if searchBuilt.Projector != nil {
			startPostOutboxRelay(ctx, store, store,
				messaging.NewPostOutboxPublisher(messaging.NewInProcessProjectorPublisher(
					&projectorAdapter{search: searchBuilt.Projector},
				)),
				"content-search-projection", "post_outbox_search", healthChecker, logger)
		}
		if placeProjector != nil {
			startPostOutboxRelay(ctx, store, store,
				messaging.NewPostOutboxPublisher(messaging.NewInProcessProjectorPublisher(
					&projectorAdapter{place: placeProjector},
				)),
				"content-place-projection", "post_outbox_place", healthChecker, logger)
		}
		// Non-Post interaction facts still use the transport publisher.
		// Post lifecycle facts are emitted exclusively by the durable relays above.
		postServiceOpts = append(postServiceOpts, postapp.WithEventPublisher(eventPub))
		behaviorEventPub = eventPub

		// Periodic raw-affinity decay so $inc growth never permanently
		// fossilizes stale interests. A per-day Redis single-flight lock
		// (SET NX) ensures only one replica runs the non-idempotent $multiply
		// decay each day. Read-time freshness decay (ComputeInterestProfile) is
		// separate; this decays the stored affinity counters themselves.
		startDailyAffinityDecay(ctx, interestAgg, router.Scene("general"), logger)
		recOpts = append(recOpts, rtrec.WithFeatureProvider(recinfra.NewFeatureStore(db)))

		// Multi-channel recall sources
		tagSource := recinfra.NewTagRecallSource(db)
		hotSource := recinfra.NewHotRecallSource(db, 48*time.Hour)
		authorSource := recinfra.NewAuthorRecallSource(db)
		exploreSource := recinfra.NewExploreRecallSource(db)
		mongoSource := recinfra.NewMongoCandidateSource(db)
		mongoCandidateSources = []rtrec.CandidateSource{
			tagSource,
			hotSource,
			authorSource,
			exploreSource,
			mongoSource,
		}
		recOpts = append(recOpts, rtrec.WithPreRanker(rtrec.NewQualityPreRanker(72*time.Hour)))
		log.Printf("content-service multi-channel recall enabled: tag/hot/author/explore/mongo/postRepo")

		// Vector recall (optional, requires embedding service)
		if cfg.Embedding.Enabled && cfg.Embedding.Endpoint != "" {
			embCB := rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default())
			embClient := rtgov.WrapClientWithCB(&http.Client{Timeout: 10 * time.Second}, embCB)
			var embOpts []rtrec.RemoteEmbeddingOption
			embOpts = append(embOpts, rtrec.WithEmbeddingClient(embClient))
			if cfg.Embedding.Model != "" {
				embOpts = append(embOpts, rtrec.WithEmbeddingModel(cfg.Embedding.Model))
			}
			embedder := rtrec.NewRemoteEmbeddingService(cfg.Embedding.Endpoint, cfg.Embedding.APIKey, embOpts...)
			vectorSource := recinfra.NewVectorRecallWithEmbedding(db, embedder)
			mongoCandidateSources = append(mongoCandidateSources, vectorSource)
			log.Printf("content-service vector recall enabled endpoint=%s", cfg.Embedding.Endpoint)
		}

		// Social recall source
		socialProvider := recinfra.NewMongoSocialGraphProvider(db)
		socialCandidateDB := recinfra.NewMongoSocialCandidateDB(db)
		socialRecall := rtrec.NewSocialRecallSource(socialProvider, socialCandidateDB, 7*24*time.Hour)
		mongoCandidateSources = append(mongoCandidateSources, socialRecall)
		recOpts = append(recOpts, rtrec.WithSocialMiner(rtrec.NewSocialInterestMiner(socialProvider)))
		collabCfg := rtrecpolicy.Baseline().ExposureGovernance.CollaborativeRecall
		if collaborativeRecallRollbackDisabled() {
			collabCfg.Enabled = false
			log.Printf("content-service collaborative recall disabled by disable_collaborative_recall_sources rollback flag")
		}
		if collabCfg.Enabled {
			collabSource := rtrec.NewCollaborativeRecallSource(
				recinfra.NewMongoCollaborativeCandidateStore(db),
				rtrec.CollaborativeRecallConfig{
					Enabled:          collabCfg.Enabled,
					MaxI2ICandidates: collabCfg.MaxI2ICandidates,
					MaxU2ICandidates: collabCfg.MaxU2ICandidates,
					QuotaPct:         collabCfg.QuotaPct,
				},
			)
			mongoCandidateSources = append(mongoCandidateSources, collabSource)
			log.Printf("content-service collaborative recall enabled quotaPct=%d i2i=%d u2i=%d", collabCfg.QuotaPct, collabCfg.MaxI2ICandidates, collabCfg.MaxU2ICandidates)
		}
		if premiumPoolSourceRollbackDisabled() {
			log.Printf("content-service premium pool source disabled by disable_premium_pool_source rollback flag")
		} else {
			premiumPoolSource := recinfra.NewPremiumPoolSource(recinfra.NewMongoPremiumPoolCandidateReader(db))
			mongoCandidateSources = append(mongoCandidateSources, premiumPoolSource)
			log.Printf("content-service premium pool source enabled recall_path=%s", recinfra.PremiumPoolRecallPath)
		}
		intersectionPolicy := rtrecpolicy.Baseline().Intersection
		// 事实交集读穿透：MongoIntersectionSource（请求期 compute）外包一层
		// rm_viewer_object_intersection 读模型，使 summary/list/feed 热路径零图谱计算，
		// 仅在缺失/分维度保鲜过期时回算并回写（WP-2）。
		intersectionCompute := recinfra.NewMongoIntersectionSource(
			socialProvider,
			recinfra.NewMongoEntityTagIndex(db),
			socialCandidateDB,
		)
		intersectionReadModel := recinfra.NewReadModelIntersectionSource(
			intersectionCompute,
			recinfra.NewMongoViewerIntersectionStore(db, logger),
			intersectionPolicy.FreshnessTTLDaysByDimension,
		)
		intersectionOpts := []intersectionapp.IntersectionServiceOption{
			intersectionapp.WithIntersectionSource(intersectionReadModel),
			intersectionapp.WithIntersectionMetrics(intersectionmetrics.New()),
			// 已读水位耐久兜底：Redis 退化为加速缓存，Redis flush/宕机后读位不丢、写降级不阻断主请求。
			intersectionapp.WithIntersectionWatermarkStore(recinfra.NewMongoWatermarkStore(db, logger)),
			intersectionapp.WithIntersectionLogger(logger),
		}
		if intersectionPolicy.CooldownDays > 0 {
			intersectionOpts = append(intersectionOpts, intersectionapp.WithIntersectionCooldownDays(intersectionPolicy.CooldownDays))
		}
		if intersectionPolicy.NegativeFeedbackCooldownDays > 0 {
			intersectionOpts = append(intersectionOpts, intersectionapp.WithIntersectionNegativeFeedbackCooldownDays(intersectionPolicy.NegativeFeedbackCooldownDays))
		}
		if intersectionPolicy.MaxCandidateWindow > 0 {
			intersectionOpts = append(intersectionOpts, intersectionapp.WithIntersectionMaxCandidateWindow(intersectionPolicy.MaxCandidateWindow))
		}
		intersectionService = intersectionapp.NewIntersectionService(router, intersectionOpts...)
		log.Printf("content-service social recall + social miner enabled")

		bulkImportService = importerapp.NewBulkImportService(recinfra.NewMongoBulkImportStore(db))
		behaviorEventStore = persistence.NewMongoBehaviorEventStore(db, logger)
		wishlistEventStore = persistence.NewMongoWishlistEventStore(db, logger)
		dailyMetricsStore = persistence.NewDailyMetricsStore(db, logger)
		authorImpactStore = persistence.NewAuthorImpactStore(db, logger)
		authorImpactEvidenceStore = persistence.NewAuthorImpactEvidenceStore(db, logger)
	}

	learningRecorder := runtimelearning.NewBufferedRecorder(learningSink, logger, runtimelearning.WithFlushSize(32), runtimelearning.WithFlushInterval(2*time.Second))
	defer learningRecorder.Stop()
	recFeedback := rtrec.NewFeedbackRecorder(learningRecorder, rtrec.WithScoreCache(rtredis.NewRecAdapter(router.Scene("rec"))))
	recOpts = append(recOpts, rtrec.WithFeedbackRecorder(recFeedback))

	reportDSN := resolveReportDSN(cfg)
	if reportDSN != "" {
		db, err := sql.Open("postgres", reportDSN)
		if err != nil {
			log.Fatalf("content-service report postgres open failed: %v", err)
		}
		db.SetMaxOpenConns(10)
		db.SetMaxIdleConns(3)
		db.SetConnMaxLifetime(30 * time.Minute)
		defer db.Close()
		pgReportStore, err := persistence.NewPGReportStore(db)
		if err != nil {
			log.Fatalf("content-service report postgres init failed: %v", err)
		}
		healthChecker.Register("report-postgres", func(hctx context.Context) error {
			return db.PingContext(hctx)
		})
		reportStore = pgReportStore
		startReportOutboxRelay(ctx, reportStore, reportStore,
			messaging.NewReportOutboxPublisher(eventPub),
			"content-report-runtime-events", "report_outbox_events", healthChecker, logger)
		log.Printf("content-service report storage=postgres")
	}

	// OSS / Media storage
	ossCfg := runtimemedia.OSSConfig{
		Endpoint:        contentOSSEndpoint(getenvOrDefault("CONTENT_OSS_ENDPOINT", cfg.OSS.Endpoint), cfg.OSS.UseSSL),
		Bucket:          getenvOrDefault("CONTENT_OSS_BUCKET", cfg.OSS.Bucket),
		Region:          getenvOrDefault("CONTENT_OSS_REGION", cfg.OSS.Region),
		AccessKeyID:     getenvOrDefault("CONTENT_OSS_ACCESS_KEY_ID", cfg.OSS.AccessKeyID),
		AccessKeySecret: getenvOrDefault("CONTENT_OSS_ACCESS_KEY_SECRET", cfg.OSS.AccessKeySecret),
		CDNDomain:       getenvOrDefault("CONTENT_CDN_DOMAIN", cfg.OSS.CDNDomain),
		CDNSignKey:      getenvOrDefault("CONTENT_CDN_SIGN_KEY", cfg.OSS.CDNSignKey),
		PresignTTL:      time.Duration(cfg.OSS.PresignTTLMin) * time.Minute,
		CDNTTL:          time.Duration(cfg.OSS.CDNTTLMin) * time.Minute,
	}
	if ossCfg.PresignTTL == 0 {
		ossCfg.PresignTTL = 15 * time.Minute
	}
	if ossCfg.CDNTTL == 0 {
		ossCfg.CDNTTL = 60 * time.Minute
	}
	if strings.TrimSpace(ossCfg.Endpoint) == "" || strings.TrimSpace(ossCfg.Bucket) == "" ||
		strings.TrimSpace(ossCfg.Region) == "" || strings.TrimSpace(ossCfg.AccessKeyID) == "" ||
		strings.TrimSpace(ossCfg.AccessKeySecret) == "" || strings.TrimSpace(ossCfg.CDNDomain) == "" ||
		strings.TrimSpace(ossCfg.CDNSignKey) == "" {
		log.Fatal("content-service OSS endpoint, bucket, region, credentials, CDN domain and signing key are required")
	}
	ossPresigner := runtimemedia.NewS3PresignClient(ossCfg)
	log.Printf("content-service oss presigner=s3 endpoint=%s bucket=%s", ossCfg.Endpoint, ossCfg.Bucket)
	mediaObjectGateway, err := mediainfra.NewObjectGateway(mediainfra.ObjectGatewayConfig{
		Bucket: ossCfg.Bucket, CDNDomain: ossCfg.CDNDomain, CDNSignKey: ossCfg.CDNSignKey, DeliveryTTL: ossCfg.CDNTTL,
	}, ossPresigner)
	if err != nil {
		log.Fatalf("content-service media object gateway invalid: %v", err)
	}
	if mediaStore == nil {
		log.Fatal("content-service MediaUploadSession/MediaAsset store is not configured")
	}
	mediaServiceCore := mediaapp.NewMediaService(mediaapp.BindDataPorts(mediaStore), mediaObjectGateway)
	mediaService := mediaapp.BindFacades(mediaServiceCore)
	commentServiceCore = commentapp.NewCommentService(commentapp.BindDataPorts(
		commentDataAdapter,
		persistence.NewCommentAttachmentReader(mediaStore, mediaObjectGateway),
		reactionStore,
	))

	source := recinfra.NewPostProjectionSource(store, store)
	rawCandidateSources := append(mongoCandidateSources, source)
	candidateSources := make([]rtrec.CandidateSource, 0, len(rawCandidateSources))
	for _, candidateSource := range rawCandidateSources {
		if gated := recinfra.GatePremiumStreamSource(candidateSource); gated != nil {
			candidateSources = append(candidateSources, gated)
		}
	}

	if (appEnv == "beta" || appEnv == "gamma" || appEnv == "prod") &&
		(!cfg.RecModelService.Enabled || strings.TrimSpace(cfg.RecModelService.URL) == "") {
		log.Fatalf("recommendation service is required in APP_ENV=%s", appEnv)
	}
	if cfg.RecModelService.Enabled && cfg.RecModelService.URL != "" {
		timeout := time.Duration(cfg.RecModelService.TimeoutMs) * time.Millisecond
		if timeout <= 0 {
			timeout = 50 * time.Millisecond
		}
		modelTokenConfig, err := rtauth.LoadAccessTokenConfig(
			runtimeconfig.EnvRuntimeConfigProvider{},
		)
		if err != nil {
			log.Fatalf("recommendation service auth config invalid: %v", err)
		}
		modelCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
			modelTokenConfig,
			"content-service",
			[]string{"recommendation.model.score"},
		)
		if err != nil {
			log.Fatalf("recommendation service credentials invalid: %v", err)
		}
		client, err := recinfra.NewHTTPModelServiceClient(
			cfg.RecModelService.URL,
			timeout,
			modelCredentials,
		)
		if err != nil {
			log.Fatalf("recommendation service client invalid: %v", err)
		}
		remoteScorer := rtrec.NewRemoteModelScorer(client, "content_feed")
		recOpts = append(recOpts, rtrec.WithScorer(remoteScorer))
		log.Printf("content-service rec-model-service enabled url=%s timeout=%v", cfg.RecModelService.URL, timeout)
	}

	// Recommendation scoring policy — single source of weights, secondary
	// coefficients, AB experiments, and segment targeting (policy.yaml). The
	// store seeds from the codegen baseline (fail-safe) and hot-reloads the
	// live YAML via validate-before-swap + last-good retention, so editing the
	// metadata takes effect without restart and a bad edit never degrades
	// scoring. Replaces the former per-service experiment registration; there
	// is no second source of experiment/weight config.
	policyStore := rtrecpolicy.NewStoreFromBaseline()
	policyPath := os.Getenv("QWQ_REC_POLICY_PATH")
	if policyPath == "" {
		policyPath = "contracts/metadata/recommendation/rec_model/policy.yaml"
	}
	if _, statErr := os.Stat(policyPath); statErr == nil {
		go rtrecpolicy.StartSyncLoop(ctx, policyStore, logger, rtrecpolicy.SyncConfig{Path: policyPath})
		log.Printf("content-service rec policy hot-reload enabled path=%s baseline=%s", policyPath, rtrecpolicy.BaselinePolicyVersion)
	} else {
		log.Printf("content-service rec policy using codegen baseline=%s (no live file at %s)", rtrecpolicy.BaselinePolicyVersion, policyPath)
	}
	recOpts = append(recOpts, rtrec.WithPolicyStore(policyStore))
	recOpts = append(recOpts, rtrec.WithExposureGovernance(sessionCache, sessionCache))

	engine := rtrec.NewEngine(sessionCache, candidateSources, recOpts...)
	feedServiceOpts := []feedapp.FeedServiceOption{}
	if intersectionService != nil {
		feedServiceOpts = append(feedServiceOpts, feedapp.WithFeedIntersectionProvider(intersectionService))
	}
	if postQueryReader == nil {
		log.Fatal("content-service Post query reader is not configured")
	}
	feedService := feedapp.NewFeedService(engine, postQueryReader, feedServiceOpts...)
	postQueryService := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail: postQueryReader,
		Author: postQueryReader,
	})
	if reactionStore == nil || reactionServiceCore == nil || commentDataAdapter == nil || commentServiceCore == nil {
		log.Fatal("content-service Comment/ContentReaction object composition is not configured")
	}
	reactionService := reactionapp.BindFacades(reactionServiceCore)
	commentService := commentapp.BindFacades(commentServiceCore)
	postDataPorts := postapp.WithMediaAssetBindingReader(
		postapp.BindDataPorts(store),
		mediainfra.NewPostBindingReader(mediaStore),
	)
	postServiceCore := postapp.NewPostService(postDataPorts, postServiceOpts...)
	postService := postapp.BindFacades(postServiceCore)
	var reportFacades *reportapp.Facades
	if reportStore != nil {
		reportServiceCore := reportapp.NewReportService(reportapp.BindDataPorts(reportStore))
		reportFacades = reportapp.BindFacades(reportServiceCore)
	}
	// 低风险实时推荐 patch（阶段七 §G）：复用 realtime redis scene 的 per-user pub/sub
	// 在安全边界发射 negative_feedback_removal / new_candidate_hint / refresh_suggestion。
	feedPatchEmitter := rtrec.NewFeedPatchEmitter(
		router.Scene("realtime"),
		rtrec.WithFeedPatchLogger(logger),
	)
	behaviorOpts := []behaviorapp.BehaviorServiceOption{
		behaviorapp.WithBehaviorEventPublisher(behaviorEventPub),
		behaviorapp.WithBehaviorFeedbackRecorder(recFeedback),
		behaviorapp.WithSessionCacheInvalidator(sessionCache.Invalidate),
		behaviorapp.WithBehaviorEventStore(behaviorEventStore),
		behaviorapp.WithWishlistEventStore(wishlistEventStore),
		behaviorapp.WithDailyMetricsStore(dailyMetricsStore),
		behaviorapp.WithAuthorImpactStore(authorImpactStore),
		behaviorapp.WithAuthorImpactEvidenceStore(authorImpactEvidenceStore),
		behaviorapp.WithFeedPatchEmitter(feedPatchEmitter),
	}
	// 交集负反馈冷却下沉（F 推荐差异化）：intersection_feedback 事件经 behavior 批处理
	// 调 IntersectionService.ReportNegativeFeedback 写 rec:ineg。仅在交集服务启用时注入，
	// 避免 typed-nil interface 陷阱（nil 指针包成非 nil 接口会导致方法调用 panic）。
	if intersectionService != nil {
		behaviorOpts = append(behaviorOpts, behaviorapp.WithIntersectionFeedbackSink(intersectionService))
	}
	behaviorService := behaviorapp.NewBehaviorService(bufferedWriter, store, behaviorOpts...)

	var handlerOpts []httpadapter.ContentHandlerOption
	handlerOpts = append(handlerOpts, httpadapter.WithHealthChecker(healthChecker))
	if outboundShareFacades == nil {
		log.Fatal("content-service OutboundShareFact object composition is not configured")
	}
	handlerOpts = append(handlerOpts, httpadapter.WithOutboundShareService(outboundShareFacades))
	handlerOpts = append(handlerOpts, httpadapter.WithMediaService(mediaService))
	if bulkImportService != nil {
		handlerOpts = append(handlerOpts, httpadapter.WithBulkImportService(bulkImportService))
	}

	// 交集统一体验服务：跨会话冷却窗口（rec:icool ZSET）+ per-dimension 已读水位
	// （ix:watermark HASH）+ 事实/概率合并排序。
	if intersectionService != nil {
		handlerOpts = append(handlerOpts, httpadapter.WithIntersectionService(intersectionService))
	}
	if authorImpactStore != nil {
		handlerOpts = append(handlerOpts, httpadapter.WithAuthorImpactStore(authorImpactStore))
	}
	if authorImpactEvidenceStore != nil {
		handlerOpts = append(handlerOpts, httpadapter.WithAuthorImpactEvidenceStore(authorImpactEvidenceStore))
	}

	handler := httpadapter.NewContentHandler(
		feedService,
		postService,
		postQueryService,
		commentService,
		reactionService,
		reportFacades,
		behaviorService,
		handlerOpts...,
	).Routes()
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("access token config invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("access token verifier invalid: %v", err)
	}
	deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("device ticket config invalid: %v", err)
	}
	deviceTicketVerifier, err := rtauth.NewHS256Verifier(deviceTicketConfig)
	if err != nil {
		log.Fatalf("device ticket verifier invalid: %v", err)
	}
	sensitiveOperationGuard := httpadapter.RequireSensitiveOperationPrincipal(handler)
	generatedOperationGuard := rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("content"),
	)(sensitiveOperationGuard)

	outerMux := http.NewServeMux()
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.HandleFunc("/livez", healthChecker.Handler())
	outerMux.HandleFunc("/startupz", healthChecker.Handler())
	outerMux.Handle("/", generatedOperationGuard)

	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "content-service",
		ServiceName:       "content-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "content-service",
		Src:               "content-service",
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())

	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(corsHandler)

	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:  accessVerifier,
			DeviceTicketVerifier: deviceTicketVerifier,
		})(rateLimited),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("content-service listening on %s (rate_limit=1000/s)", addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("content-service: %v", err)
	}
}
