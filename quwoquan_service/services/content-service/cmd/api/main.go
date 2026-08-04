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
	rterr "quwoquan_service/runtime/errors"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtotel "quwoquan_service/runtime/otel"
	rtrecpolicy "quwoquan_service/runtime/recpolicy"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentmessaging "quwoquan_service/services/content-service/internal/content/comment/infrastructure/messaging"
	commentpersistence "quwoquan_service/services/content-service/internal/content/comment/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/infrastructure/accountclosure"
	behaviorstream "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/messaging"
	behaviorpersistence "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/persistence"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactionmessaging "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/messaging"
	reactionpersistence "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
	tombstonepost "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/adapters/inbound/post"
	tombstonepersistence "quwoquan_service/services/content-service/internal/content/deleted_post_tombstone/infrastructure/persistence"
	intersectionvisitpersistence "quwoquan_service/services/content-service/internal/content/intersection_visit_state/infrastructure/persistence"
	outboundshareapp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/application/command"
	outboundsharemessaging "quwoquan_service/services/content-service/internal/content/outbound_share_fact/infrastructure/messaging"
	outboundshareinfra "quwoquan_service/services/content-service/internal/content/outbound_share_fact/infrastructure/persistence"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	accessinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/accesscontrol"
	accountsecurity "quwoquan_service/services/content-service/internal/content/post/infrastructure/accountsecurity"
	postgovernance "quwoquan_service/services/content-service/internal/content/post/infrastructure/governance"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/intersectionmetrics"
	postmessaging "quwoquan_service/services/content-service/internal/content/post/infrastructure/messaging"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/placeindex"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/searchindex"
	profileinteractionapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	profileinteractioninfra "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/infrastructure/persistence"
	profileinteractionreadapp "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/application"
	profilereadfactinfra "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/infrastructure/persistence"
	filtercatalogapp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/application"
	filtercatalogcache "quwoquan_service/services/content-service/internal/media/filter_catalog_release/infrastructure/cache"
	filtercatalogmetrics "quwoquan_service/services/content-service/internal/media/filter_catalog_release/infrastructure/observability"
	filtercatalogpersistence "quwoquan_service/services/content-service/internal/media/filter_catalog_release/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/mediaobjectfence"
	"quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/mediareferencefence"
	mediaassetpersistence "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/persistence"
	mediareprocesspersistence "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/infrastructure/persistence"
	originalaccesspersistence "quwoquan_service/services/content-service/internal/media/media_original_access_fact/infrastructure/persistence"
	uploadsessionpersistence "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/persistence"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationmessaging "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/infrastructure/messaging"
	moderationpersistence "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/infrastructure/persistence"
	reportpersistence "quwoquan_service/services/content-service/internal/trust_safety/report/infrastructure/persistence"
	"syscall"
	"time"
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
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion); err != nil {
		log.Fatalf("content-service config identity failed: %v", err)
	}
	if err := preflightConfig(cfg, appEnv); err != nil {
		log.Fatalf("content-service config preflight failed: %v", err)
	}
	logFeedQuotaPolicies(cfg.Feed)
	startConfigSyncLoop(serviceName, appEnv, configRoot, configVersion, imageVersion)
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("content-service access token config invalid: %v", err)
	}
	feedCursorCodec, err := feedapp.NewFeedCursorCodec(accessTokenConfig.Secret)
	if err != nil {
		log.Fatalf("content-service feed cursor codec init failed: %v", err)
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
	eventPub := postmessaging.NewRedisEventPublisherWithTransport(messageTransport, "content-service", logger)
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
	var reactionStore *reactionpersistence.MongoContentReactionStore
	var reactionServiceCore *reactionapp.Service
	var commentDataAdapter *commentpersistence.MongoCommentDataAdapter
	var commentViewerRelationships *commentpersistence.CommentViewerRelationshipMongoProjection
	var commentServiceCore *commentapp.CommentService
	var outboundShareFacades *outboundshareapp.Facades
	var profileInteractionFacades *profileinteractionapp.Facades
	var filterCatalogFacades *filtercatalogapp.Facades
	var moderationStore *moderationpersistence.MongoPostModerationCaseStore
	var moderationFacades *moderationapp.Facades
	var reportStore *reportpersistence.PGReportStore
	var closeReportStore func()
	var postServiceOpts []postapp.PostServiceOption
	var mediaStore *mediaassetpersistence.MongoMediaStore
	var mediaOriginalAccessStore *originalaccesspersistence.MongoStore
	var mediaImageReprocessStore *mediareprocesspersistence.MongoStore
	var mediaUploadSessionStore *uploadsessionpersistence.MongoStore
	var behaviorEventStore ports.BehaviorEventStore
	var wishlistEventStore ports.WishlistEventStore
	var wishlistStateReader ports.WishlistStateReader
	var dailyMetricsStore *behaviorpersistence.DailyMetricsStore
	var intersectionService *intersectionapp.IntersectionService
	var authoritativeSignalSink *recinfra.AuthoritativeSignalSink
	var viewerBlockReader *accessinfra.PersonaBlockReader
	var accountClosureStore *accountclosure.MongoStore
	var accountClosureSearch *accountclosure.SearchIndexerDeleter
	var accountClosureCache *accountclosure.RedisPersonalDataCacheCleaner
	var accountRestrictionProjection contentAccountRestrictionProjection
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
		mediaReferenceFence, err := mediareferencefence.New(db)
		if err != nil {
			log.Fatalf("content-service MediaAsset reference fence init failed: %v", err)
		}
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
		mongoStore := persistence.NewMongoPostStore(
			db.Collection(collName),
			tombstonepost.NewStorePort(tombstonepersistence.NewMongoStore(db)),
			mediaReferenceFence,
		)
		if err := mongoStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service post indexes init failed: %v", err)
		}
		store = mongoStore
		postQueryReader = persistence.NewMongoPostQueryReader(db.Collection(collName))
		activeSupplyReader = persistence.NewMongoActiveSupplyReader(
			db,
			appEnv,
			persistence.WithActiveSupplyCachePolicy(
				time.Duration(cfg.Feed.ActiveSupplyCacheTTLMS)*time.Millisecond,
				time.Duration(cfg.Feed.ActiveSupplyCacheJitterMS)*time.Millisecond,
			),
		)
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
		profileReadFactStore := profilereadfactinfra.NewMongoReadFactStore(db)
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
			outboundsharemessaging.NewOutboundShareOutboxPublisher(eventPub),
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
		mediaStore = mediaassetpersistence.NewMongoMediaStore(db)
		if err := mediaStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service media runtime indexes init failed: %v", err)
		}
		mediaOriginalAccessStore = originalaccesspersistence.NewMongoStore(db)
		if err := mediaOriginalAccessStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service MediaOriginalAccessFact indexes init failed: %v", err)
		}
		mediaImageReprocessStore = mediareprocesspersistence.NewMongoStore(db)
		if err := mediaImageReprocessStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service MediaImageReprocessRun indexes init failed: %v", err)
		}
		mediaUploadSessionStore = uploadsessionpersistence.NewMongoStore(
			db.Collection("media_upload_sessions"),
			mediaStore,
		)
		if err := mediaUploadSessionStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service MediaUploadSession indexes init failed: %v", err)
		}
		commentDataAdapter = commentpersistence.NewMongoCommentDataAdapter(
			db,
			mediaReferenceFence,
		)
		if err := commentDataAdapter.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service Comment indexes init failed: %v", err)
		}
		commentViewerRelationships =
			commentpersistence.NewCommentViewerRelationshipMongoProjection(db)
		if err := commentViewerRelationships.EnsureIndexes(ctx); err != nil {
			log.Fatalf(
				"content-service Comment viewer relationship projection indexes init failed: %v",
				err,
			)
		}
		commentViewerRelationshipProjector :=
			commentapp.NewViewerRelationshipProjector(commentViewerRelationships)
		commentViewerRelationshipConsumer :=
			commentmessaging.NewViewerRelationshipConsumer(
				router.Scene("general"),
				commentViewerRelationshipProjector,
				instanceID,
				logger,
			)
		if err := commentViewerRelationshipConsumer.EnsureGroup(ctx); err != nil {
			log.Fatalf(
				"content-service Comment viewer relationship consumer startup failed: %v",
				err,
			)
		}
		go commentViewerRelationshipConsumer.Run(ctx, 500*time.Millisecond)
		postServiceOpts = append(postServiceOpts, postapp.WithCommentReaders(commentDataAdapter))
		startCommentOutboxRelay(
			ctx, commentDataAdapter, commentDataAdapter,
			commentmessaging.NewCommentOutboxPublisher(eventPub),
			"content-comment-runtime-events", "content_comment_outbox_events",
			healthChecker, logger,
		)
		startCommentOutboxRelay(
			ctx, commentDataAdapter, commentDataAdapter,
			commentmessaging.NewCommentLifecycleStreamPublisher(router.Scene("general")),
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
		moderationStore = moderationpersistence.NewMongoPostModerationCaseStore(
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
			moderationmessaging.NewModerationOutboxPublisher(eventPub),
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
		reactionStore = reactionpersistence.NewMongoContentReactionStore(db)
		if err := reactionStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service ContentReaction indexes init failed: %v", err)
		}
		reactionServiceCore = reactionapp.NewService(
			reactionapp.BindDataPorts(
				reactionStore,
				reactionpersistence.NewReactionTargetReader(commentDataAdapter, commentDataAdapter),
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
			reactionmessaging.NewContentReactionOutboxPublisher(eventPub),
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
			reactionmessaging.NewReactionLifecycleStreamPublisher(router.Scene("general")),
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

		log.Printf("content-service interaction storage=mongodb (durable source outboxes + profile_interaction_activity_views)")

		personaAccessProjection := accessinfra.NewPersonaAccessProjection(db)
		if err := personaAccessProjection.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service persona access projection startup failed: %v", err)
		}
		personaAccessProjectionConsumer := accessinfra.NewPersonaAccessProjectionConsumer(
			router.Scene("general"), personaAccessProjection, instanceID, logger,
		)
		if err := personaAccessProjectionConsumer.EnsureGroup(ctx); err != nil {
			log.Fatalf(
				"content-service persona access projection consumer startup failed: %v",
				err,
			)
		}
		go personaAccessProjectionConsumer.Run(ctx, 500*time.Millisecond)
		viewerBlockReader = accessinfra.NewPersonaBlockReader(db)
		behaviorStreamRelay := behaviorstream.NewStreamRelay(
			db,
			router.Scene("general"),
		).WithConsumer("recommendation-behavior-facts")
		go func() {
			if err := behaviorStreamRelay.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
				log.Printf("WARN: content-service behavior stream relay stopped: %v", err)
			}
		}()
		healthChecker.Register("behavior-fact-stream-relay", func(hctx context.Context) error {
			return behaviorStreamRelay.Healthy(30 * time.Second)
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
		accountClosureObjectFences, err := mediaobjectfence.New(db)
		if err != nil {
			log.Fatalf("content-service media object deletion fence assembly failed: %v", err)
		}
		accountClosureStore, err = accountclosure.NewMongoStore(
			db,
			accountClosureSubjectDigestor,
			accountClosureObjectFences,
		)
		if err != nil {
			log.Fatalf("content-service UserAccountClosed store assembly failed: %v", err)
		}
		if err := accountClosureStore.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service UserAccountClosed indexes init failed: %v", err)
		}
		accountRestrictionProjection, err = newContentAccountRestrictionProjection(
			db,
			accountClosureStore,
		)
		if err != nil {
			log.Fatalf("content-service account restriction projection assembly failed: %v", err)
		}
		if err := accountRestrictionProjection.EnsureIndexes(ctx); err != nil {
			log.Fatalf("content-service account restriction projection indexes failed: %v", err)
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
			postmessaging.NewPostOutboxPublisher(eventPub),
			"content-runtime-events", "post_outbox_events", healthChecker, logger)
		startPostOutboxRelay(ctx, store, store,
			postmessaging.NewPostLifecycleStreamPublisher(router.Scene("general")),
			"content-post-lifecycle-stream", "post_outbox_lifecycle_stream", healthChecker, logger)
		if searchBuilt.Projector != nil {
			startPostOutboxRelay(ctx, store, store,
				postmessaging.NewPostOutboxPublisher(postmessaging.NewInProcessProjectorPublisher(
					&projectorAdapter{search: searchBuilt.Projector},
				)),
				"content-search-projection", "post_outbox_search", healthChecker, logger)
		}
		if placeProjector != nil {
			startPostOutboxRelay(ctx, store, store,
				postmessaging.NewPostOutboxPublisher(postmessaging.NewInProcessProjectorPublisher(
					&projectorAdapter{place: placeProjector},
				)),
				"content-place-projection", "post_outbox_place", healthChecker, logger)
		}
		// Non-Post interaction facts still use the transport publisher.
		// Post lifecycle facts are emitted exclusively by the durable relays above.
		postServiceOpts = append(postServiceOpts, postapp.WithEventPublisher(eventPub))

		// Embedding pipeline (W8/B5, S0 基建)：写入侧（PostPublished → Embedding
		// API → posts.embedding，独立 outbox relay checkpoint + 每日成本护栏）随
		// cfg.Embedding.Enabled 开启；向量召回读通道另由 VectorRecallEnabled 控制
		// （S0 flag-off，S1 内容池阈值达标后开启，开启不需要重构）。
		if cfg.Embedding.Enabled && !contentSliceWorkload() {
			embedder, err := resolveContentEmbeddingGateway(appEnv)
			if err != nil {
				log.Fatalf("content-service embedding binding invalid: %v", err)
			}
			embeddingProjector := recinfra.NewEmbeddingProjector(
				db, embedder, router.Scene("rec"), logger,
			)
			startPostOutboxRelay(ctx, store, store,
				postmessaging.NewPostOutboxPublisher(postmessaging.NewInProcessProjectorPublisher(
					&projectorAdapter{embedding: embeddingProjector},
				)),
				"content-embedding-projection", "post_outbox_embedding", healthChecker, logger)
			log.Printf("content-service embedding write pipeline enabled adapter=binding budget=%d/day", recinfra.EmbeddingDailyBudgetDefault)
			log.Printf("content-service embedding write pipeline is enrichment-only; candidate recall is owned by recommendation-service")
		}

		// RecommendationFeatureProfileView owns every relationship, behavior,
		// candidate and supply projection used to explain intersections. Content
		// only consumes its typed Reader and performs current Post hydration.
		intersectionPolicy := rtrecpolicy.Baseline().Intersection
		intersectionReader := buildIntersectionProjectionReader(cfg)
		intersectionOpts := []intersectionapp.IntersectionServiceOption{
			intersectionapp.WithIntersectionSource(intersectionReader),
			intersectionapp.WithIntersectionSupplyProbe(intersectionReader),
			intersectionapp.WithIntersectionMetrics(intersectionmetrics.New()),
			// 已读水位耐久兜底：Redis 退化为加速缓存，Redis flush/宕机后读位不丢、写降级不阻断主请求。
			intersectionapp.WithIntersectionWatermarkStore(
				intersectionvisitpersistence.NewMongoWatermarkStore(db, logger),
			),
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
		log.Printf("content-service intersection projection reader enabled owner=recommendation-service")

		behaviorEventStore = behaviorpersistence.NewMongoBehaviorEventStore(db, logger)
		// N0-3 服务端权威信号 sink：like/comment/report 事实 → HotPath +
		// rm_behavior_events + learning。relay 在 FeedbackRecorder 注入后启动。
		authoritativeSignalSink = recinfra.NewAuthoritativeSignalSink(db, bufferedWriter, behaviorEventStore)
		mongoWishlistStore := behaviorpersistence.NewMongoWishlistEventStore(db, logger)
		wishlistEventStore = mongoWishlistStore
		wishlistStateReader = mongoWishlistStore
		dailyMetricsStore = behaviorpersistence.NewDailyMetricsStore(db, logger)
	}

	// like/comment 权威信号 relay 只追加 ContentBehaviorFact。Recommendation
	// 通过 typed stream 形成 RecommendationFeedbackFact；Content 不再保有第二套学习事实。
	if authoritativeSignalSink != nil {
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
		mediaOriginalAccessStore,
		mediaImageReprocessStore,
		mediaUploadSessionStore,
		commentDataAdapter,
		reactionStore,
		postQueryReader,
		viewerBlockReader,
		commentViewerRelationships,
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
		accountRestrictionProjection,
	)
	if err != nil {
		log.Fatalf("content-service UserAccountClosed runtime assembly failed: %v", err)
	}

	rankedRecommendation := buildRankedRecommendationGateway(cfg)
	authorImpactProjectionReader := buildAuthorImpactProjectionReader(cfg)

	// 推荐策略 Store 的具体实现仍在 composition root 显式选择。
	policyStore := rtrecpolicy.NewStoreFromBaseline()
	startRecommendationPolicyHotReload(ctx, policyStore, logger)
	handler := buildContentHTTPHandler(contentHTTPHandlerInput{
		ctx:                          ctx,
		logger:                       logger,
		healthChecker:                healthChecker,
		router:                       router,
		bufferedWriter:               bufferedWriter,
		sessionCache:                 sessionCache,
		policyStore:                  policyStore,
		postStore:                    store,
		postQueryReader:              postQueryReader,
		activeSupplyReader:           activeSupplyReader,
		feedCursorCodec:              feedCursorCodec,
		feedRuntimeConfig:            cfg.Feed,
		rankedRecommendation:         rankedRecommendation,
		viewerBlockReader:            viewerBlockReader,
		reactionStore:                reactionStore,
		reactionService:              reactionServiceCore,
		commentStore:                 commentDataAdapter,
		commentService:               commentServiceCore,
		reportStore:                  reportStore,
		mediaStore:                   mediaStore,
		mediaRuntime:                 mediaRuntime,
		postServiceOptions:           postServiceOpts,
		moderationStore:              moderationStore,
		moderationFacades:            moderationFacades,
		onboardingTaxonomy:           onboardingTaxonomy,
		behaviorEventStore:           behaviorEventStore,
		wishlistEventStore:           wishlistEventStore,
		wishlistStateReader:          wishlistStateReader,
		dailyMetricsStore:            dailyMetricsStore,
		authorImpactProjectionReader: authorImpactProjectionReader,
		intersectionService:          intersectionService,
		outboundShareFacades:         outboundShareFacades,
		profileInteractionFacades:    profileInteractionFacades,
		filterCatalogFacades:         filterCatalogFacades,
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
		cfg.Feed,
		healthChecker,
		accessTokenConfig,
		accountSecurityAuthority,
		runtimeLogging.ioLogger,
		runtimeLogging.processLogger,
		runtimeLogging.exceptionLogger,
	)
	log.Printf(
		"content-service listening on %s (feed_owner_max_inflight=%d recall_sources_maximum=%d recall_unterminated_per_source=%d)",
		addr,
		cfg.Feed.MaxInflight,
		cfg.Feed.MaximumRecallSources,
		cfg.Feed.MaximumUnterminatedCallsPerSource,
	)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("content-service: %v", err)
	}
}
