package main

import (
	"context"
	"log"
	"log/slog"
	"net/http"
	"time"

	rthealth "quwoquan_service/runtime/health"
	rtrec "quwoquan_service/runtime/recommendation"
	rtrecpolicy "quwoquan_service/runtime/recpolicy"
	rtredis "quwoquan_service/runtime/redis"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliverymessaging "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/messaging"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
	outboundshareapp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/application/command"
	httpadapter "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	importerapp "quwoquan_service/services/content-service/internal/content/post/application/importer"
	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	mediainfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/content/media"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/feedmetrics"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	taxonomyvalidationinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/taxonomyvalidation"
	profileinteractionapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	filtercataloghttp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/adapters/inbound/http"
	filtercatalogapp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/application"
	uploadsessionhttp "quwoquan_service/services/content-service/internal/media/media_upload_session/adapters/inbound/http"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	"quwoquan_service/services/content-service/internal/trust_safety/report/infrastructure/reportmetrics"
)

type contentHTTPHandlerInput struct {
	ctx                       context.Context
	logger                    *slog.Logger
	healthChecker             *rthealth.Checker
	router                    *rtredis.Router
	bufferedWriter            *rtrec.BufferedHotPath
	sessionCache              *rtrec.SessionCache
	candidateSources          []rtrec.CandidateSource
	recommendationOptions     []rtrec.EngineOption
	policyStore               *rtrecpolicy.Store
	postStore                 *persistence.MongoPostStore
	postQueryReader           *persistence.MongoPostQueryReader
	activeSupplyReader        feedapp.ActiveSupplyReader
	feedCursorCodec           *feedapp.FeedCursorCodec
	feedRuntimeConfig         feedRuntimeConfig
	rankedRecommendation      deliveryapp.RankedRecommendationGateway
	viewerBlockReader         *recinfra.PersonaBlockReader
	reactionStore             *persistence.MongoContentReactionStore
	reactionService           *reactionapp.Service
	commentStore              *persistence.MongoCommentDataAdapter
	commentService            *commentapp.CommentService
	reportStore               *persistence.PGReportStore
	mediaStore                *persistence.MongoMediaStore
	mediaRuntime              mediaRuntimeComposition
	postServiceOptions        []postapp.PostServiceOption
	moderationStore           *persistence.MongoPostModerationCaseStore
	moderationFacades         *moderationapp.Facades
	feedbackRecorder          *rtrec.FeedbackRecorder
	onboardingTaxonomy        behaviorapp.OnboardingInterestTaxonomyValidator
	behaviorEventStore        ports.BehaviorEventStore
	wishlistEventStore        ports.WishlistEventStore
	wishlistStateReader       ports.WishlistStateReader
	dailyMetricsStore         *persistence.DailyMetricsStore
	authorImpactStore         *persistence.AuthorImpactStore
	authorImpactEvidenceStore *persistence.AuthorImpactEvidenceStore
	intersectionService       *intersectionapp.IntersectionService
	entityCardProvider        feedapp.ObjectCardProvider
	bulkImportService         *importerapp.BulkImportService
	outboundShareFacades      *outboundshareapp.Facades
	profileInteractionFacades *profileinteractionapp.Facades
	filterCatalogFacades      *filtercatalogapp.Facades
}

func buildContentHTTPHandler(input contentHTTPHandlerInput) http.Handler {
	ctx := input.ctx
	logger := input.logger
	healthChecker := input.healthChecker
	router := input.router
	bufferedWriter := input.bufferedWriter
	sessionCache := input.sessionCache
	candidateSources := input.candidateSources
	recOpts := input.recommendationOptions
	policyStore := input.policyStore
	store := input.postStore
	postQueryReader := input.postQueryReader
	activeSupplyReader := input.activeSupplyReader
	feedCursorCodec := input.feedCursorCodec
	rankedRecommendation := input.rankedRecommendation
	viewerBlockReader := input.viewerBlockReader
	reactionStore := input.reactionStore
	reactionServiceCore := input.reactionService
	commentDataAdapter := input.commentStore
	commentServiceCore := input.commentService
	reportStore := input.reportStore
	mediaStore := input.mediaStore
	mediaObjectGateway := input.mediaRuntime.mediaObjectGateway
	mediaService := input.mediaRuntime.mediaService
	mediaImageReprocessService := input.mediaRuntime.mediaImageReprocessService
	postServiceOpts := input.postServiceOptions
	moderationStore := input.moderationStore
	moderationFacades := input.moderationFacades
	recFeedback := input.feedbackRecorder
	onboardingTaxonomy := input.onboardingTaxonomy
	behaviorEventStore := input.behaviorEventStore
	wishlistEventStore := input.wishlistEventStore
	wishlistStateReader := input.wishlistStateReader
	dailyMetricsStore := input.dailyMetricsStore
	authorImpactStore := input.authorImpactStore
	authorImpactEvidenceStore := input.authorImpactEvidenceStore
	intersectionService := input.intersectionService
	entityCardProvider := input.entityCardProvider
	bulkImportService := input.bulkImportService
	outboundShareFacades := input.outboundShareFacades
	profileInteractionFacades := input.profileInteractionFacades
	filterCatalogFacades := input.filterCatalogFacades

	engine := rtrec.NewEngine(sessionCache, candidateSources, recOpts...)
	feedServiceOpts := []feedapp.FeedServiceOption{
		feedapp.WithFeedFilterObserver(feedmetrics.Observer{}),
	}
	if intersectionService != nil {
		feedServiceOpts = append(feedServiceOpts, feedapp.WithFeedIntersectionProvider(intersectionService))
	}
	if entityCardProvider != nil {
		// 混合对象卡（B4 插卡模式，S0 实体主页卡）：策略经热加载 policy 读取，
		// enabled=false 即零成本关闭；召回器只读既有物化集合（fail-open 到无卡）。
		feedServiceOpts = append(feedServiceOpts, feedapp.WithObjectCardProvider(
			entityCardProvider,
			func() rtrecpolicy.ObjectCardConfig { return policyStore.Current().ObjectCards },
		))
	}
	if activeSupplyReader == nil {
		log.Fatal("content-service active supply reader is not configured")
	}
	if feedCursorCodec == nil {
		log.Fatal("content-service feed cursor codec is not configured")
	}
	if rankedRecommendation == nil {
		log.Fatal("content-service ranked recommendation gateway is not configured")
	}
	feedServiceOpts = append(
		feedServiceOpts,
		feedapp.WithActiveSupplyReader(activeSupplyReader),
		feedapp.WithFeedCursorCodec(feedCursorCodec),
		feedapp.WithRankedRecommendationGateway(rankedRecommendation),
		feedapp.WithFeedDeliveryPageStore(
			deliveryredis.NewStore(
				router.Scene("rec"),
				deliveryredis.WithQuotaPolicy(
					input.feedRuntimeConfig.deliveryPageQuotaPolicy(),
				),
			),
		),
		feedapp.WithFeedPageDeliveredPublisher(
			deliverymessaging.NewFeedPageDeliveredPublisher(
				router.Scene("general"),
			),
		),
	)
	if postQueryReader == nil {
		log.Fatal("content-service Post query reader is not configured")
	}
	if viewerBlockReader == nil {
		log.Fatal("content-service viewer block reader is not configured")
	}
	feedServiceOpts = append(
		feedServiceOpts,
		feedapp.WithFeedViewerBlockReader(viewerBlockReader),
	)
	feedService := feedapp.NewFeedService(engine, postQueryReader, feedServiceOpts...)
	postQueryService := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail:       postQueryReader,
		Author:       postQueryReader,
		Tombstones:   store,
		ViewerBlocks: viewerBlockReader,
	})
	if reactionStore == nil || reactionServiceCore == nil || commentDataAdapter == nil || commentServiceCore == nil {
		log.Fatal("content-service Comment/ContentReaction object composition is not configured")
	}
	reactionService := reactionapp.BindFacades(reactionServiceCore)
	commentService := commentapp.BindFacades(commentServiceCore)
	startCommentReportModerationProjection(
		ctx,
		reportStore,
		commentService,
		healthChecker,
		logger,
	)
	postDataPorts := postapp.WithMediaAssetBindingReader(
		postapp.BindDataPorts(store),
		mediainfra.NewPostBindingReader(mediaStore, mediaObjectGateway),
	)
	postServiceCore := postapp.NewPostService(postDataPorts, postServiceOpts...)
	postService := postapp.BindFacades(postServiceCore)
	if moderationStore == nil {
		log.Fatal("content-service PostModerationCase store is not configured")
	}
	// 审核决定 → Post lifecycle：独立 moderation outbox checkpoint，
	// 仅 exact post revision 可执行内部三次 CAS；无公开 If-Match/Saga。
	startModerationOutboxRelay(
		ctx,
		moderationStore,
		moderationStore,
		postapp.NewPostModerationDecisionConsumer(postService),
		"content-moderation-post-lifecycle",
		"content_moderation_post_lifecycle",
		healthChecker,
		logger,
	)
	var reportFacades *reportapp.Facades
	if reportStore != nil {
		reportServiceCore := reportapp.NewReportService(
			reportapp.BindDataPorts(reportStore),
			reportapp.WithLifecycleObserver(reportmetrics.Observer{}),
		)
		reportFacades = reportapp.BindFacades(reportServiceCore)
	}
	// 低风险实时推荐 patch（阶段七 §G）：复用 realtime redis scene 的 per-user pub/sub
	// 在安全边界发射 negative_feedback_removal / new_candidate_hint / refresh_suggestion。
	feedPatchEmitter := rtrec.NewFeedPatchEmitter(
		router.Scene("realtime"),
		rtrec.WithFeedPatchLogger(logger),
	)
	behaviorOpts := []behaviorapp.BehaviorServiceOption{
		behaviorapp.WithBehaviorFeedbackRecorder(recFeedback),
		// N1-3 experiment_bucket 归因：与 engine 的 scoring 分桶同源
		//（同一 policy 确定性 hash），行为漏斗指标可按分桶切分。
		behaviorapp.WithExperimentBucketResolver(func(userID string) string {
			policy := policyStore.Current()
			return policy.ResolveBucketOr(rtrecpolicy.ExpScoringWeights, userID, nil, policy.DefaultPreset)
		}),
		behaviorapp.WithSessionCacheInvalidator(sessionCache.Invalidate),
		behaviorapp.WithBehaviorEventStore(behaviorEventStore),
		behaviorapp.WithWishlistEventStore(wishlistEventStore),
		behaviorapp.WithWishlistStateReader(wishlistStateReader),
		behaviorapp.WithDailyMetricsStore(dailyMetricsStore),
		behaviorapp.WithAuthorImpactStore(authorImpactStore),
		behaviorapp.WithAuthorImpactEvidenceStore(authorImpactEvidenceStore),
		behaviorapp.WithFeedPatchEmitter(feedPatchEmitter),
	}
	if onboardingTaxonomy == nil {
		log.Fatal("content-service onboarding interest taxonomy validator is not configured")
	}
	behaviorOpts = append(
		behaviorOpts,
		behaviorapp.WithOnboardingInterestTaxonomyValidator(onboardingTaxonomy),
	)
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
	if profileInteractionFacades == nil {
		log.Fatal("content-service ProfileInteraction object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithProfileInteractionService(profileInteractionFacades),
	)
	if filterCatalogFacades == nil {
		log.Fatal("content-service FilterCatalogRelease object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithFilterCatalogReleaseHandler(
			filtercataloghttp.NewHandler(filterCatalogFacades),
		),
	)
	if moderationFacades == nil {
		log.Fatal("content-service PostModerationCase object composition is not configured")
	}
	handlerOpts = append(handlerOpts, httpadapter.WithModerationService(moderationFacades))
	handlerOpts = append(handlerOpts, httpadapter.WithMediaService(mediaService))
	if input.mediaRuntime.mediaUploadSessionService == nil {
		log.Fatal("content-service MediaUploadSession object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithMediaUploadSessionHandler(
			uploadsessionhttp.NewHandler(input.mediaRuntime.mediaUploadSessionService),
		),
	)
	if mediaImageReprocessService == nil {
		log.Fatal("content-service MediaImageReprocessRun object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithMediaImageReprocessService(mediaImageReprocessService),
	)
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

	contentHandler := httpadapter.NewContentHandler(
		feedService,
		postService,
		postQueryService,
		commentService,
		reactionService,
		reportFacades,
		behaviorService,
		handlerOpts...,
	).Routes()

	return contentHandler
}

func buildOnboardingInterestTaxonomyValidator(
	cfg config,
) (behaviorapp.OnboardingInterestTaxonomyValidator, error) {
	activeLeafValidator, err := taxonomyvalidationinfra.NewHTTPActiveTaxonomyLeafValidator(
		cfg.TagService.URL,
		time.Duration(cfg.TagService.TimeoutMs)*time.Millisecond,
	)
	if err != nil {
		return nil, err
	}
	policy := contentgenerated.DefaultOnboardingInterestCatalogPolicy()
	return behaviorapp.CatalogBackedOnboardingInterestTaxonomy{
		DimensionRoots:           policy.DimensionRoots,
		MinSelections:            policy.MinSelectionCount,
		MaxSelections:            policy.MaxSelectionCount,
		DimensionMinSelections:   policy.DimensionMinSelections,
		DimensionMaxSelections:   policy.DimensionMaxSelections,
		ActiveLeafValidationPort: activeLeafValidator,
	}, nil
}
