package main

import (
	"context"
	"log"
	"log/slog"
	"os"
	"os/signal"
	rtmongo "quwoquan_service/internal/platform/mongodb"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	runtimelearning "quwoquan_service/runtime/learning"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtotel "quwoquan_service/runtime/otel"
	rtrec "quwoquan_service/runtime/recommendation"
	rtrecpolicy "quwoquan_service/runtime/recpolicy"
	rtredis "quwoquan_service/runtime/redis"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	outboundshareapp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/application/command"
	outboundshareinfra "quwoquan_service/services/content-service/internal/content/outbound_share_fact/infrastructure/persistence"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	importerapp "quwoquan_service/services/content-service/internal/content/post/application/importer"
	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/accountclosure"
	accountsecurity "quwoquan_service/services/content-service/internal/content/post/infrastructure/accountsecurity"
	profileinteractioninfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/profile_interaction/persistence"
	postgovernance "quwoquan_service/services/content-service/internal/content/post/infrastructure/governance"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/intersectionmetrics"
	learninginfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/learning"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/placeindex"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/searchindex"
	profileinteractionapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	profileinteractionreadapp "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/application"
	filtercatalogapp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/application"
	filtercatalogcache "quwoquan_service/services/content-service/internal/media/filter_catalog_release/infrastructure/cache"
	filtercatalogmetrics "quwoquan_service/services/content-service/internal/media/filter_catalog_release/infrastructure/observability"
	filtercatalogpersistence "quwoquan_service/services/content-service/internal/media/filter_catalog_release/infrastructure/persistence"
	uploadsessionpersistence "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/persistence"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	"syscall"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
)

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
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("content-service access token config invalid: %v", err)
	}
	accountSecurityAuthority, err := accountsecurity.NewAuthority(
		accessTokenConfig,
		accountsecurity.Config{
			BaseURL:   cfg.AccountSecurityAuthority.BaseURL,
			TimeoutMS: cfg.AccountSecurityAuthority.TimeoutMS,
		},
	)
	if err != nil {
		log.Fatalf("content-service account security authority config invalid: %v", err)
	}
	onboardingTaxonomy, err := buildOnboardingInterestTaxonomyValidator(cfg)
	if err != nil {
		log.Fatalf("content-service onboarding taxonomy validation config failed: %v", err)
	}
	accountClosureSubjectDigestor, err := resolveAccountClosureSubjectDigestor(
		appEnv,
		serviceName,
	)
	if err != nil {
		log.Fatalf("content-service account-closure privacy config failed: %v", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "content-service", SamplingRatio: 0.1})
	defer otelShutdown()

	addr := getenvOrDefault("CONTENT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18080"
	}

	logger := slog.Default()
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())

	runtimeLogging := mustBuildContentRuntimeLogging()
	defer runtimeLogging.Close()

	router := buildRedisRouter(cfg)
	defer router.Close()
	if err := router.PingAll(ctx); err != nil {
		log.Printf("WARN: content-service redis ping: %v", err)
	}
	messageTransport, err := requireContentMessageTransport(
		ctx,
		appEnv,
		router,
		map[string]string{
			"general":  cfg.Redis.General.Mode,
			"realtime": cfg.Redis.Realtime.Mode,
		},
	)
	if err != nil {
		log.Fatalf("content-service message transport preflight failed: %v", err)
	}
	subjectClosureGuard := newDeferredSubjectClosureGuard()
	eventPub := messaging.NewRedisEventPublisherWithTransport(messageTransport, "content-service", logger)
	sessionCache, bufferedWriter := buildRecommendationSignalRuntime(
		router,
		subjectClosureGuard,
		logger,
	)
	defer bufferedWriter.Stop()

	// SIT6 商用装配：Mongo/PostgreSQL/OSS 均为启动必需依赖，不存在内存降级。
	var store *persistence.MongoPostStore
	var postQueryReader *persistence.MongoPostQueryReader
	var activeSupplyReader feedapp.ActiveSupplyReader
	var reactionStore *persistence.MongoContentReactionStore
	var reactionServiceCore *reactionapp.Service
	var commentDataAdapter *persistence.MongoCommentDataAdapter
	var commentServiceCore *commentapp.CommentService
	var outboundShareFacades *outboundshareapp.Facades
	var profileInteractionFacades *profileinteractionapp.Facades
	var filterCatalogFacades *filtercatalogapp.Facades
	var moderationStore *persistence.MongoPostModerationCaseStore
	var moderationFacades *moderationapp.Facades
	var reportStore *persistence.PGReportStore
	var closeReportStore func()
	var postServiceOpts []postapp.PostServiceOption
	var mediaStore *persistence.MongoMediaStore
	var mediaUploadSessionStore *uploadsessionpersistence.MongoStore
	var mongoCandidateSources []rtrec.CandidateSource
	var bulkImportService *importerapp.BulkImportService
	var behaviorEventStore ports.BehaviorEventStore
	var wishlistEventStore ports.WishlistEventStore
	var wishlistStateReader ports.WishlistStateReader
	var dailyMetricsStore *persistence.DailyMetricsStore
	var authorImpactStore *persistence.AuthorImpactStore
	var authorImpactEvidenceStore *persistence.AuthorImpactEvidenceStore
	var intersectionService *intersectionapp.IntersectionService
	var entityCardProvider feedapp.ObjectCardProvider
	var authoritativeSignalSink *recinfra.AuthoritativeSignalSink
	var viewerBlockReader *recinfra.PersonaBlockReader
	var accountClosureStore *accountclosure.MongoStore
	var accountClosureSearch *accountclosure.SearchIndexerDeleter
	var accountClosureCache *accountclosure.RedisPersonalDataCacheCleaner
	var recDB *mongo.Database
	recOpts := []rtrec.EngineOption{
		rtrec.WithRecallTimeout(150 * time.Millisecond),
		rtrec.WithLogger(logger),
	}
	var learningSink runtimelearning.Sink
	postServiceOpts = append(postServiceOpts, postapp.WithSignalProcessor(bufferedWriter))
	postServiceOpts = append(postServiceOpts, postapp.WithLogger(logger))
	postServiceOpts = append(postServiceOpts, postapp.WithStoryRuntimeConfig(resolveStoryRuntimeConfig()))
	postServiceOpts = append(
		postServiceOpts,
		postapp.WithPublicationAdmission(
			postgovernance.NewRedisPublicationRateGate(router.Scene("general")),
			postgovernance.NewManualReviewPublicationSafetyGate(),
		),
	)

	healthChecker := rthealth.NewChecker()
	healthChecker.Register(
		"account-security-authority",
		accountSecurityAuthority.CheckAccountSecurityAuthority,
	)
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
		recDB = db
		filterCatalogStore := filtercatalogpersistence.NewMongoStore(db)
		if err := filterCatalogStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service FilterCatalogRelease indexes init failed: %v", err)
		}
		filterCatalogReader := filtercatalogcache.NewActiveReader(
			filterCatalogStore,
			router.Scene("general"),
			logger,
		)
		filterCatalogService, err := filtercatalogapp.NewService(
			filterCatalogStore,
			filterCatalogReader,
			filtercatalogapp.WithObserver(filtercatalogmetrics.Observer{}),
			filtercatalogapp.WithActiveFilterCatalogInvalidator(filterCatalogReader),
		)
		if err != nil {
			log.Fatalf("content-service FilterCatalogRelease composition failed: %v", err)
		}
		filterCatalogFacades = filtercatalogapp.BindFacades(filterCatalogService)
		mongoStore := persistence.NewMongoPostStore(db.Collection(collName))
		if err := mongoStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service post indexes init failed: %v", err)
		}
		store = mongoStore
		postQueryReader = persistence.NewMongoPostQueryReader(db.Collection(collName))
		activeSupplyReader = persistence.NewMongoActiveSupplyReader(db, appEnv)
		outboundShareSink := outboundshareinfra.NewMongoAppendSink(db)
		if err := outboundShareSink.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service OutboundShareFact indexes init failed: %v", err)
		}
		outboundShareFacades = outboundshareapp.BindFacades(outboundshareapp.NewService(
			outboundShareSink,
			outboundshareinfra.NewShareablePostReader(postQueryReader),
		))
		profileActivityStore := profileinteractioninfra.NewMongoActivityStore(db)
		if err := profileActivityStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service ProfileInteractionActivity indexes init failed: %v", err)
		}
		profileReadFactStore := profileinteractioninfra.NewMongoReadFactStore(db)
		if err := profileReadFactStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service ProfileInteractionReadFact indexes init failed: %v", err)
		}
		profileProjector := profileinteractionapp.NewProjector(
			profileinteractioninfra.NewMongoProjectionSourceReader(db),
			profileActivityStore,
		)
		profileInteractionFacades = profileinteractionapp.BindFacades(
			profileinteractionapp.NewActivityQueryService(profileActivityStore),
			profileinteractionreadapp.NewReadFactService(
				profileActivityStore,
				profileReadFactStore,
			),
		)
		startOutboundShareOutboxRelay(
			ctx, outboundShareSink, outboundShareSink,
			messaging.NewOutboundShareOutboxPublisher(eventPub),
			"content-outbound-share-runtime-events",
			"content_outbound_share_outbox_events",
			healthChecker, logger,
		)
		startOutboundShareOutboxRelay(
			ctx, outboundShareSink, outboundShareSink,
			profileinteractionapp.NewOutboundShareProjector(profileProjector),
			"content-outbound-share-profile-interaction",
			"content_outbound_share_profile_interaction",
			healthChecker, logger,
		)
		startOutboundShareOutboxRelay(
			ctx, outboundShareSink, outboundShareSink,
			outboundshareapp.NewShareCountProjector(outboundShareSink, mongoStore),
			"content-outbound-share-post-count",
			"content_outbound_share_post_count",
			healthChecker, logger,
		)
		startOutboundShareOutboxRelay(
			ctx, outboundShareSink, outboundShareSink,
			outboundshareapp.NewShareCountProjector(
				outboundShareSink,
				persistence.NewMongoDiscoveryFeedShareCountWriter(db),
			),
			"content-outbound-share-discovery-count",
			"content_outbound_share_discovery_count",
			healthChecker, logger,
		)
		startProfileInteractionReadFactRelay(
			ctx, profileReadFactStore, profileReadFactStore,
			profileinteractionapp.NewReadFactProjector(profileActivityStore),
			"content-profile-interaction-read-projection",
			"content_profile_interaction_read_projection",
			healthChecker, logger,
		)
		startPostOutboxRelay(
			ctx, store, store,
			profileinteractionapp.NewPostTargetProjector(profileActivityStore),
			"content-post-profile-interaction-target",
			"content_post_profile_interaction_target",
			healthChecker, logger,
		)
		mediaStore = persistence.NewMongoMediaStore(db)
		if err := mediaStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service media runtime indexes init failed: %v", err)
		}
		mediaUploadSessionStore = uploadsessionpersistence.NewMongoStore(
			db.Collection("media_upload_sessions"),
			mediaStore,
		)
		if err := mediaUploadSessionStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service MediaUploadSession indexes init failed: %v", err)
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
			messaging.NewCommentLifecycleStreamPublisher(router.Scene("general")),
			"content-comment-lifecycle-stream", "content_comment_lifecycle_stream",
			healthChecker, logger,
		)
		startCommentOutboxRelay(
			ctx, commentDataAdapter, commentDataAdapter,
			commentapp.NewCommentCountProjector(commentDataAdapter, mongoStore),
			"content-comment-post-count", "content_comment_post_count",
			healthChecker, logger,
		)
		startCommentOutboxRelay(
			ctx, commentDataAdapter, commentDataAdapter,
			profileinteractionapp.NewCommentProjector(profileProjector),
			"content-comment-profile-interaction",
			"content_comment_profile_interaction",
			healthChecker, logger,
		)
		// N3-3 计数保鲜：comment 权威计数同步投影到召回读模型
		// rm_discovery_feed（此前只刷 posts，召回候选 commentCount 长期陈旧）。
		startCommentOutboxRelay(
			ctx, commentDataAdapter, commentDataAdapter,
			commentapp.NewCommentCountProjector(
				commentDataAdapter,
				persistence.NewMongoDiscoveryFeedCommentCountWriter(db),
			),
			"content-comment-discovery-count", "content_comment_discovery_count",
			healthChecker, logger,
		)
		moderationStore = persistence.NewMongoPostModerationCaseStore(
			db.Collection("post_moderation_cases"),
		)
		if err := moderationStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service PostModerationCase indexes init failed: %v", err)
		}
		moderationFacades = moderationapp.BindFacades(moderationapp.NewModerationService(
			moderationapp.DataPorts{
				Aggregate:   moderationStore,
				Eligibility: moderationStore,
				CurrentCase: moderationStore,
			},
		))
		startModerationOutboxRelay(
			ctx, moderationStore, moderationStore,
			messaging.NewModerationOutboxPublisher(eventPub),
			"content-moderation-runtime-events", "content_moderation_outbox_events",
			healthChecker, logger,
		)
		startPostOutboxRelay(
			ctx,
			store,
			store,
			moderationapp.NewSubmissionCaseOpener(moderationFacades),
			"content-post-submission-moderation",
			"content_post_submission_moderation",
			healthChecker,
			logger,
		)
		reactionStore = persistence.NewMongoContentReactionStore(db)
		if err := reactionStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service ContentReaction indexes init failed: %v", err)
		}
		reactionServiceCore = reactionapp.NewService(
			reactionapp.BindDataPorts(
				reactionStore,
				persistence.NewReactionTargetReader(commentDataAdapter, commentDataAdapter),
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
			profileinteractionapp.NewReactionProjector(profileProjector),
			"content-reaction-profile-interaction",
			"content_reaction_profile_interaction",
			healthChecker,
			logger,
		)
		startReactionOutboxRelay(
			ctx,
			reactionStore,
			reactionStore,
			messaging.NewReactionLifecycleStreamPublisher(router.Scene("general")),
			"content-reaction-lifecycle-stream",
			"content_reaction_lifecycle_stream",
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
		// hotScore 投影：评论赞踩与回复事实驱动的确定性排序分（sort=hot 真相源）。
		commentHotScoreProjector := commentapp.NewCommentHotScoreProjector(
			commentDataAdapter,
			reactionStore,
			commentDataAdapter,
		)
		startCommentOutboxRelay(
			ctx, commentDataAdapter, commentDataAdapter,
			commentHotScoreProjector,
			"content-comment-hot-score", "content_comment_hot_score",
			healthChecker, logger,
		)
		startReactionOutboxRelay(
			ctx,
			reactionStore,
			reactionStore,
			commentapp.NewReactionHotScorePublisher(commentHotScoreProjector),
			"content-reaction-comment-hot-score",
			"content_reaction_comment_hot_score",
			healthChecker,
			logger,
		)
		// PostDeleted 级联：宿主内容删除后全部评论批量 tombstoned。
		startPostOutboxRelay(
			ctx, store, store,
			commentapp.NewCommentTombstoneProjector(commentDataAdapter),
			"content-post-comment-tombstone",
			"content_post_comment_tombstone",
			healthChecker, logger,
		)
		log.Printf("content-service storage=mongodb db=%s collection=%s", dbName, collName)

		learningSink = learninginfra.NewMongoSink(db, logger)

		log.Printf("content-service interaction storage=mongodb (durable source outboxes + profile_interaction_activity_views)")

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
			segmentsPath = "services/content-service/resources/policies/content/post/recommendation_segments.yaml"
		}
		segDefs, segErr := recinfra.LoadSegments(segmentsPath)
		if segErr != nil {
			log.Printf("WARN: load segment definitions from %s: %v (segment membership disabled)", segmentsPath, segErr)
		}
		interestAgg := recinfra.NewInterestProfileAggregator(db, recinfra.DefaultInterestProfileConfig(), eventPub, recinfra.WithSegments(segDefs))
		recommendProjector := recinfra.NewRecommendFeatureProjector(db, recinfra.WithEntityPropagation(entityPropagation), recinfra.WithSignalProcessor(bufferedWriter), recinfra.WithInterestAggregator(interestAgg))
		if err := recommendProjector.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service recommend feature projection startup failed: %v", err)
		}
		featureStore := recinfra.NewFeatureStore(db)
		tagFeedbackProjector, err := recinfra.NewTagFeedbackFeatureProjector(
			db,
			featureStore.Invalidate,
		)
		if err != nil {
			log.Fatalf("content-service TagFeedbackRecorded projector assembly failed: %v", err)
		}
		if err := tagFeedbackProjector.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service TagFeedbackRecorded inbox indexes init failed: %v", err)
		}
		tagFeedbackConsumer, err := recinfra.NewTagFeedbackConsumer(
			messageTransport,
			tagFeedbackProjector,
			instanceID,
			logger,
		)
		if err != nil {
			log.Fatalf("content-service TagFeedbackRecorded consumer assembly failed: %v", err)
		}
		if err := tagFeedbackConsumer.EnsureGroup(ctx); err != nil {
			log.Fatalf("content-service TagFeedbackRecorded consumer startup failed: %v", err)
		}
		go tagFeedbackConsumer.Run(ctx)
		healthChecker.Register("tag-feedback-consumer", func(hctx context.Context) error {
			return tagFeedbackConsumer.Healthy(30 * time.Second)
		})
		relationshipProjection := recinfra.NewPersonaRelationshipProjection(db)
		if err := relationshipProjection.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service persona relationship projection startup failed: %v", err)
		}
		relationshipProjectionConsumer := recinfra.NewPersonaRelationshipProjectionConsumer(
			router.Scene("general"), relationshipProjection, instanceID, logger,
		)
		if err := relationshipProjectionConsumer.EnsureGroup(ctx); err != nil {
			log.Fatalf(
				"content-service persona relationship projection consumer startup failed: %v",
				err,
			)
		}
		go relationshipProjectionConsumer.Run(ctx, 500*time.Millisecond)
		viewerBlockReader = recinfra.NewPersonaBlockReader(db)
		premiumPoolProjector := recinfra.NewPremiumPoolProjector(db)
		go recinfra.NewPremiumPoolEventConsumer(router.Scene("general"), premiumPoolProjector, logger).Run(ctx)
		searchSignalConsumer := recinfra.NewSearchSignalConsumer(router.Scene("general"), recommendProjector, instanceID, logger)
		go searchSignalConsumer.Run(ctx, 500*time.Millisecond)

		// N0-2 行为→特征投影持久轨：游标增量扫 rm_behavior_events 驱动
		// RecommendFeatureProjector（tagInteraction/亲和度/交集 kindCounts）与
		// DiscoveryFeedProjector（viewCount），替换无订阅者的 BehaviorBatchReported
		// Pub/Sub。断点续传 + at-least-once；readiness 经 healthChecker 暴露。
		behaviorProjectionRelay := recinfra.NewBehaviorProjectionRelay(db, recommendProjector, discoveryProjector)
		go func() {
			if err := behaviorProjectionRelay.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
				log.Printf("WARN: content-service behavior projection relay stopped: %v", err)
			}
		}()
		healthChecker.Register("behavior-projection-relay", func(hctx context.Context) error {
			return behaviorProjectionRelay.Healthy(30 * time.Second)
		})

		// Write-time search index projector (content.search_index_worker). Disabled
		// when ES is off (alpha): Built is empty and the projector is nil, so the
		// write path is unaffected. When enabled we ensure the shared index exists
		// up front so increments have somewhere to land, and register a liveness ping.
		searchBuilt, searchErr := searchindex.Build(cfg.ES, store, searchindex.WithLogger(logger))
		if searchErr != nil {
			log.Fatalf("content-service search index assembly failed: %v", searchErr)
		}
		// First-party place projector (R-S05e): location.place objects reuse the
		// SAME ES indexer (one geo mechanism, one client) and a derived
		// place_snapshots store. Built only when ES is enabled, so alpha is
		// unaffected.
		var placeProjector *placeindex.PlaceProjector
		if searchBuilt.Client != nil {
			healthChecker.Register("elasticsearch", searchBuilt.HealthPing())
			if err := searchBuilt.EnsureIndex(ctx); err != nil {
				log.Fatalf("content-service ensure ES search index failed: %v", err)
			}
			placeStore := placeindex.NewMongoPlaceStore(db.Collection(placeindex.PlaceSnapshotCollection), logger)
			placeProjector = placeindex.NewProjector(searchBuilt.Indexer, store, placeStore, placeindex.WithLogger(logger))
			log.Printf("content-service search index projector enabled (es endpoints=%d index=%s, place objects on)", len(cfg.ES.Endpoints), searchBuilt.Client.IndexName())
		}
		accountClosureStore, err = accountclosure.NewMongoStore(
			db,
			accountClosureSubjectDigestor,
		)
		if err != nil {
			log.Fatalf("content-service UserAccountClosed store assembly failed: %v", err)
		}
		if err := accountClosureStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service UserAccountClosed indexes init failed: %v", err)
		}
		accountClosureSearch, err = accountclosure.NewSearchIndexerDeleter(
			searchBuilt.Indexer,
			cfg.ES.Enabled,
		)
		if err != nil {
			log.Fatalf("content-service UserAccountClosed search assembly failed: %v", err)
		}
		accountClosureCache, err = accountclosure.NewRedisPersonalDataCacheCleaner(
			router,
			accountClosureSubjectDigestor,
		)
		if err != nil {
			log.Fatalf("content-service UserAccountClosed cache assembly failed: %v", err)
		}
		guard, err := accountclosure.NewSubjectClosureGuard(
			accountClosureStore,
			accountClosureCache,
		)
		if err != nil {
			log.Fatalf("content-service subject-closure guard assembly failed: %v", err)
		}
		if err := subjectClosureGuard.Bind(guard); err != nil {
			log.Fatalf("content-service subject-closure guard binding failed: %v", err)
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

		// Periodic raw-affinity decay so $inc growth never permanently
		// fossilizes stale interests. A per-day Redis single-flight lock
		// (SET NX) ensures only one replica runs the non-idempotent $multiply
		// decay each day. Read-time freshness decay (ComputeInterestProfile) is
		// separate; this decays the stored affinity counters themselves.
		startDailyAffinityDecay(ctx, interestAgg, router.Scene("general"), logger)
		recOpts = append(recOpts, rtrec.WithFeatureProvider(featureStore))

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
		log.Printf("content-service multi-channel recall enabled: tag/hot/author/explore/mongo (posts fallback disabled)")

		// Embedding pipeline (W8/B5, S0 基建)：写入侧（PostPublished → Embedding
		// API → posts.embedding，独立 outbox relay checkpoint + 每日成本护栏）随
		// cfg.Embedding.Enabled 开启；向量召回读通道另由 VectorRecallEnabled 控制
		// （S0 flag-off，S1 内容池阈值达标后开启，开启不需要重构）。
		if cfg.Embedding.Enabled {
			embedder, err := resolveContentEmbeddingGateway(appEnv)
			if err != nil {
				log.Fatalf("content-service embedding binding invalid: %v", err)
			}
			embeddingProjector := recinfra.NewEmbeddingProjector(
				db, embedder, router.Scene("rec"), logger,
			)
			startPostOutboxRelay(ctx, store, store,
				messaging.NewPostOutboxPublisher(messaging.NewInProcessProjectorPublisher(
					&projectorAdapter{embedding: embeddingProjector},
				)),
				"content-embedding-projection", "post_outbox_embedding", healthChecker, logger)
			log.Printf("content-service embedding write pipeline enabled adapter=binding budget=%d/day", recinfra.EmbeddingDailyBudgetDefault)
			if cfg.Embedding.VectorRecallEnabled {
				vectorSource := recinfra.NewVectorRecallWithEmbedding(db, embedder)
				mongoCandidateSources = append(mongoCandidateSources, vectorSource)
				log.Printf("content-service vector recall enabled adapter=binding")
			} else {
				log.Printf("content-service vector recall flag-off (S0); write pipeline keeps materializing embeddings")
			}
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
		entityCardProvider = recinfra.NewMongoEntityCardProvider(db)
		// W10 关系图谱自动物化：内容侧三边（语义共现/标签共现/地理邻近）周期
		// 全量重算 + TTL 退场，无人值守；行为共现边 S1 触发（schema 已就绪）。
		// 消费方（对象页/推荐/交集）只读 rm_object_relation_edges，请求期零图计算。
		edgeMaterializer := recinfra.NewObjectRelationEdgeMaterializer(db, logger)
		if err := edgeMaterializer.EnsureIndexes(ctx); err != nil {
			log.Printf("WARN: content-service object relation edge indexes init failed: %v", err)
		}
		go edgeMaterializer.Run(ctx, 6*time.Hour)
		log.Printf("content-service object relation edge materializer enabled interval=6h edges=semantic_co_mention,tag_overlap,geo_proximity")
		behaviorEventStore = persistence.NewMongoBehaviorEventStore(db, logger)
		// N0-3 服务端权威信号 sink：like/comment/report 事实 → HotPath +
		// rm_behavior_events + learning。relay 在 FeedbackRecorder 注入后启动。
		authoritativeSignalSink = recinfra.NewAuthoritativeSignalSink(db, bufferedWriter, behaviorEventStore)
		mongoWishlistStore := persistence.NewMongoWishlistEventStore(db, logger)
		wishlistEventStore = mongoWishlistStore
		wishlistStateReader = mongoWishlistStore
		dailyMetricsStore = persistence.NewDailyMetricsStore(db, logger)
		authorImpactStore = persistence.NewAuthorImpactStore(db, logger)
		authorImpactEvidenceStore = persistence.NewAuthorImpactEvidenceStore(db, logger)
	}

	learningRecorder := runtimelearning.NewBufferedRecorder(learningSink, logger, runtimelearning.WithFlushSize(32), runtimelearning.WithFlushInterval(2*time.Second))
	defer learningRecorder.Stop()
	recFeedback := rtrec.NewFeedbackRecorder(learningRecorder, rtrec.WithScoreCache(rtredis.NewRecAdapter(router.Scene("rec"))))
	recOpts = append(recOpts, rtrec.WithFeedbackRecorder(recFeedback))

	// N0-3 like/comment 权威信号 relay：sink 完整（含 learning）后启动，
	// 独立 checkpoint 消费对象 outbox 的服务端确认事实。report 信号 relay
	// 在 report 存储分支内同构启动。
	if authoritativeSignalSink != nil {
		authoritativeSignalSink.AttachFeedback(recFeedback)
		if reactionStore != nil {
			startReactionOutboxRelay(
				ctx,
				reactionStore,
				reactionStore,
				recinfra.NewReactionSignalProjector(authoritativeSignalSink),
				"content-reaction-recommend-signal",
				"content_reaction_recommend_signal",
				healthChecker,
				logger,
			)
		}
		if commentDataAdapter != nil {
			startCommentOutboxRelay(
				ctx, commentDataAdapter, commentDataAdapter,
				recinfra.NewCommentSignalProjector(authoritativeSignalSink),
				"content-comment-recommend-signal", "content_comment_recommend_signal",
				healthChecker, logger,
			)
		}
	}

	reportStore, closeReportStore = buildReportRuntime(
		ctx, cfg, router, eventPub, healthChecker, logger,
		moderationFacades, postQueryReader, authoritativeSignalSink,
	)
	if closeReportStore != nil {
		defer closeReportStore()
	}

	mediaRuntime, closeMediaRuntime := buildMediaRuntime(
		ctx,
		cfg,
		appEnv,
		instanceID,
		logger,
		healthChecker,
		mediaStore,
		mediaUploadSessionStore,
		commentDataAdapter,
		reactionStore,
		recDB,
		postQueryReader,
		viewerBlockReader,
	)
	defer closeMediaRuntime()
	commentServiceCore = mediaRuntime.commentServiceCore

	accountClosureConsumer, err := startAccountClosureRuntime(
		ctx,
		router.Scene("general"),
		logger,
		healthChecker,
		instanceID,
		accountClosureStore,
		accountClosureCache,
		accountClosureSearch,
		mediaRuntime.mediaObjectGateway,
	)
	if err != nil {
		log.Fatalf("content-service UserAccountClosed runtime assembly failed: %v", err)
	}

	source := recinfra.NewPostProjectionSource(store, store)
	rawCandidateSources := recommendationCandidateSources(mongoCandidateSources, source)
	candidateSources := applyRecommendationCandidateGates(rawCandidateSources)

	recOpts = composeRecommendationModelScorer(cfg, appEnv, logger, recOpts)

	// 推荐策略 Store 的具体实现仍在 composition root 显式选择。
	policyStore := rtrecpolicy.NewStoreFromBaseline()
	startRecommendationPolicyHotReload(ctx, policyStore, logger)
	if recDB != nil {
		go recinfra.NewABAdmissionRunner(recDB, policyStore, logger).Run(ctx, time.Hour)
	}
	recOpts = append(recOpts, rtrec.WithPolicyStore(policyStore))
	recOpts = append(recOpts, rtrec.WithExposureGovernance(sessionCache, sessionCache))

	handler := buildContentHTTPHandler(contentHTTPHandlerInput{
		ctx:                       ctx,
		logger:                    logger,
		healthChecker:             healthChecker,
		router:                    router,
		bufferedWriter:            bufferedWriter,
		sessionCache:              sessionCache,
		candidateSources:          candidateSources,
		recommendationOptions:     recOpts,
		policyStore:               policyStore,
		postStore:                 store,
		postQueryReader:           postQueryReader,
		activeSupplyReader:        activeSupplyReader,
		viewerBlockReader:         viewerBlockReader,
		reactionStore:             reactionStore,
		reactionService:           reactionServiceCore,
		commentStore:              commentDataAdapter,
		commentService:            commentServiceCore,
		reportStore:               reportStore,
		mediaStore:                mediaStore,
		mediaRuntime:              mediaRuntime,
		postServiceOptions:        postServiceOpts,
		moderationStore:           moderationStore,
		moderationFacades:         moderationFacades,
		feedbackRecorder:          recFeedback,
		onboardingTaxonomy:        onboardingTaxonomy,
		behaviorEventStore:        behaviorEventStore,
		wishlistEventStore:        wishlistEventStore,
		wishlistStateReader:       wishlistStateReader,
		dailyMetricsStore:         dailyMetricsStore,
		authorImpactStore:         authorImpactStore,
		authorImpactEvidenceStore: authorImpactEvidenceStore,
		intersectionService:       intersectionService,
		entityCardProvider:        entityCardProvider,
		bulkImportService:         bulkImportService,
		outboundShareFacades:      outboundShareFacades,
		profileInteractionFacades: profileInteractionFacades,
		filterCatalogFacades:      filterCatalogFacades,
	})
	handler, err = runtimemessaging.WithDeadLetterRecoveryRoute(
		handler,
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/content/account-closure/dead-letters:recover",
			Module:   rterr.ModuleContent,
			Releaser: accountClosureConsumer,
		},
	)
	if err != nil {
		log.Fatalf("content-service account-closure recovery route failed: %v", err)
	}
	server := buildContentHTTPServer(
		addr,
		instanceID,
		handler,
		healthChecker,
		accessTokenConfig,
		accountSecurityAuthority,
		runtimeLogging.ioLogger,
		runtimeLogging.processLogger,
		runtimeLogging.exceptionLogger,
	)
	log.Printf("content-service listening on %s (rate_limit=1000/s)", addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("content-service: %v", err)
	}
}
