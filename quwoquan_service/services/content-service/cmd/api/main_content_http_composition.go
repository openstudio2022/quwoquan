package bootstrap

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	rthealth "quwoquan_service/runtime/health"
	rtrec "quwoquan_service/runtime/recommendation"
	rtrecpolicy "quwoquan_service/runtime/recpolicy"
	rtredis "quwoquan_service/runtime/redis"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	commenthttp "quwoquan_service/services/content-service/internal/content/comment/adapters/inbound/http"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	commentpersistence "quwoquan_service/services/content-service/internal/content/comment/infrastructure/persistence"
	behaviorhttp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/adapters/inbound/http"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	behaviorpersistence "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/persistence"
	reactionhttp "quwoquan_service/services/content-service/internal/content/content_reaction/adapters/inbound/http"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionpersistence "quwoquan_service/services/content-service/internal/content/content_reaction/infrastructure/persistence"
	deliverypost "quwoquan_service/services/content-service/internal/content/feed_delivery_page/adapters/inbound/post"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliverymessaging "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/messaging"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
	intersectionvisithttp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/adapters/inbound/http"
	intersectionvisitapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application"
	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	outboundsharehttp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/adapters/inbound/http"
	outboundshareapp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/application/command"
	postgraphql "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/graphql"
	httpadapter "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	contentpublicweb "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/publicweb"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	accessinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/accesscontrol"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/feedmetrics"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	taxonomyvalidationinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/taxonomyvalidation"
	profileactivityhttp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/adapters/inbound/http"
	profileinteractionapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	profilereadfacthttp "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/adapters/inbound/http"
	filtercataloghttp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/adapters/inbound/http"
	filtercatalogapp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/application"
	mediaassethttp "quwoquan_service/services/content-service/internal/media/media_asset/adapters/inbound/http"
	mediainfra "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/media"
	mediaassetpersistence "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/persistence"
	mediareprocesshttp "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/adapters/inbound/http"
	uploadsessionhttp "quwoquan_service/services/content-service/internal/media/media_upload_session/adapters/inbound/http"
	originalaccessquotahttp "quwoquan_service/services/content-service/internal/media/original_access_quota/adapters/inbound/http"
	moderationhttp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/adapters/inbound/http"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationpersistence "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/infrastructure/persistence"
	reporthttp "quwoquan_service/services/content-service/internal/trust_safety/report/adapters/inbound/http"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportpersistence "quwoquan_service/services/content-service/internal/trust_safety/report/infrastructure/persistence"
	"quwoquan_service/services/content-service/internal/trust_safety/report/infrastructure/reportmetrics"
)

type contentHTTPHandlerInput struct {
	ctx                          context.Context
	workers                      *workerRegistry
	logger                       *slog.Logger
	healthChecker                *rthealth.Checker
	router                       *rtredis.Router
	bufferedWriter               *rtrec.BufferedHotPath
	sessionCache                 *rtrec.SessionCache
	policyStore                  *rtrecpolicy.Store
	postStore                    *persistence.MongoPostStore
	postQueryReader              *persistence.MongoPostQueryReader
	activeSupplyReader           feedapp.ActiveSupplyReader
	researchReleaseReadback      *postapp.ResearchReleaseReadbackQueryFacet
	feedCursorCodec              *feedapp.FeedCursorCodec
	feedRuntimeConfig            feedRuntimeConfig
	rankedRecommendation         deliveryapp.RankedRecommendationGateway
	viewerBlockReader            *accessinfra.PersonaBlockReader
	reactionStore                *reactionpersistence.MongoContentReactionStore
	reactionService              *reactionapp.Service
	commentStore                 *commentpersistence.MongoCommentDataAdapter
	commentService               *commentapp.CommentService
	reportStore                  *reportpersistence.PGReportStore
	mediaStore                   *mediaassetpersistence.MongoMediaStore
	mediaRuntime                 mediaRuntimeComposition
	postServiceOptions           []postapp.PostServiceOption
	moderationStore              *moderationpersistence.MongoPostModerationCaseStore
	moderationFacades            *moderationapp.Facades
	onboardingTaxonomy           behaviorapp.OnboardingInterestTaxonomyValidator
	behaviorEventStore           ports.BehaviorEventStore
	wishlistEventStore           ports.WishlistEventStore
	wishlistStateReader          ports.WishlistStateReader
	dailyMetricsStore            *behaviorpersistence.DailyMetricsStore
	authorImpactProjectionReader ports.AuthorImpactProjectionReader
	gatheringSocialProofReader   ports.GatheringSocialProofProjectionReader
	intersectionService          *intersectionapp.IntersectionService
	outboundShareFacades         *outboundshareapp.Facades
	profileInteractionFacades    *profileinteractionapp.Facades
	filterCatalogFacades         *filtercatalogapp.Facades
	contractGraphSHA256          string
}

type contentHTTPHandlers struct {
	business        http.Handler
	internalGraphQL http.Handler
	// publicWeb 是 post 对象的公开 SEO HTML 读面（public-content-web-entry
	// 第一段）；未配置 CONTENT_PUBLIC_WEB_ORIGIN 时为 nil，不暴露该面。
	publicWeb http.Handler
}

func buildContentHTTPHandler(input contentHTTPHandlerInput) (contentHTTPHandlers, error) {
	ctx := input.ctx
	workers := input.workers
	logger := input.logger
	healthChecker := input.healthChecker
	router := input.router
	bufferedWriter := input.bufferedWriter
	sessionCache := input.sessionCache
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
	originalAccessQuotaService := input.mediaRuntime.originalAccessQuotaService
	postServiceOpts := input.postServiceOptions
	moderationStore := input.moderationStore
	moderationFacades := input.moderationFacades
	onboardingTaxonomy := input.onboardingTaxonomy
	behaviorEventStore := input.behaviorEventStore
	wishlistEventStore := input.wishlistEventStore
	wishlistStateReader := input.wishlistStateReader
	dailyMetricsStore := input.dailyMetricsStore
	authorImpactProjectionReader := input.authorImpactProjectionReader
	intersectionService := input.intersectionService
	outboundShareFacades := input.outboundShareFacades
	profileInteractionFacades := input.profileInteractionFacades
	filterCatalogFacades := input.filterCatalogFacades

	feedServiceOpts := []feedapp.FeedServiceOption{
		feedapp.WithFeedFilterObserver(feedmetrics.Observer{}),
		feedapp.WithObjectCardPolicy(
			func() rtrecpolicy.ObjectCardConfig {
				return policyStore.Current().ObjectCards
			},
		),
	}
	if intersectionService != nil {
		feedServiceOpts = append(feedServiceOpts, feedapp.WithFeedIntersectionProvider(intersectionService))
	}
	if activeSupplyReader == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service active supply reader is not configured")
	}
	if feedCursorCodec == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service feed cursor codec is not configured")
	}
	if rankedRecommendation == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service ranked recommendation gateway is not configured")
	}
	feedServiceOpts = append(
		feedServiceOpts,
		feedapp.WithActiveSupplyReader(activeSupplyReader),
		feedapp.WithFeedCursorCodec(feedCursorCodec),
		feedapp.WithRankedRecommendationGateway(rankedRecommendation),
		feedapp.WithFeedDeliveryPageStore(
			deliverypost.NewDeliveryPort(deliveryredis.NewStore(
				router.Scene("rec"),
				deliveryredis.WithQuotaPolicy(
					input.feedRuntimeConfig.deliveryPageQuotaPolicy(),
				),
			)),
		),
		feedapp.WithFeedPageDeliveredPublisher(
			deliverymessaging.NewFeedPageDeliveredPublisher(
				router.Scene("general"),
			),
		),
	)
	if postQueryReader == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service Post query reader is not configured")
	}
	if viewerBlockReader == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service viewer block reader is not configured")
	}
	if input.reactionStore == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service reaction store is not configured")
	}
	viewerReactionReader := viewerPostReactionReader{store: input.reactionStore}
	feedServiceOpts = append(
		feedServiceOpts,
		feedapp.WithFeedViewerBlockReader(viewerBlockReader),
		feedapp.WithFeedViewerReactionReader(viewerReactionReader),
	)
	feedService := feedapp.NewFeedService(postQueryReader, feedServiceOpts...)
	postQueryService := postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
		Detail:       postQueryReader,
		Author:       postQueryReader,
		Gathering:    postQueryReader,
		SocialProof:  input.gatheringSocialProofReader,
		Tombstones:   store,
		ViewerBlocks: viewerBlockReader,
		ActiveSupply: activeSupplyReader,
	})
	if reactionStore == nil || reactionServiceCore == nil || commentDataAdapter == nil || commentServiceCore == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service Comment/ContentReaction object composition is not configured")
	}
	reactionService := reactionapp.BindFacades(reactionServiceCore)
	commentService := commentapp.BindFacades(commentServiceCore)
	startCommentReportModerationProjection(
		ctx,
		workers,
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
		return contentHTTPHandlers{}, fmt.Errorf("content-service PostModerationCase store is not configured")
	}
	// 审核决定 → Post lifecycle：独立 moderation outbox checkpoint，
	// 仅 exact post revision 可执行内部三次 CAS；无公开 If-Match/Saga。
	startModerationOutboxRelay(
		ctx,
		workers,
		moderationStore,
		moderationStore,
		postapp.NewPostModerationDecisionHandler(postService),
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
	var reportHandler httpadapter.ReportHTTPHandler
	if reportFacades != nil {
		reportHandler = reporthttp.NewHandler(reportFacades)
	}
	// 低风险实时推荐 patch（阶段七 §G）：复用 realtime redis scene 的 per-user pub/sub
	// 在安全边界发射 negative_feedback_removal / new_candidate_hint / refresh_suggestion。
	feedPatchEmitter := rtrec.NewFeedPatchEmitter(
		router.Scene("realtime"),
		rtrec.WithFeedPatchLogger(logger),
	)
	behaviorOpts := []behaviorapp.BehaviorServiceOption{
		behaviorapp.WithSessionCacheInvalidator(sessionCache.Invalidate),
		behaviorapp.WithBehaviorEventStore(behaviorEventStore),
		behaviorapp.WithWishlistEventStore(wishlistEventStore),
		behaviorapp.WithWishlistStateReader(wishlistStateReader),
		behaviorapp.WithDailyMetricsStore(dailyMetricsStore),
		behaviorapp.WithFeedPatchEmitter(feedPatchEmitter),
	}
	if onboardingTaxonomy == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service onboarding interest taxonomy validator is not configured")
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
	if input.researchReleaseReadback != nil {
		handlerOpts = append(
			handlerOpts,
			httpadapter.WithResearchReleaseReadback(input.researchReleaseReadback),
		)
	}
	if intersectionService == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service IntersectionVisitState object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithIntersectionVisitStateHandler(
			intersectionvisithttp.NewHandler(
				intersectionvisitapp.NewCommands(intersectionService),
				intersectionService,
			),
		),
	)
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithContentBehaviorHandler(behaviorhttp.NewHandler(behaviorService)),
	)
	if outboundShareFacades == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service OutboundShareFact object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithOutboundShareHandler(outboundsharehttp.NewHandler(outboundShareFacades)),
	)
	if profileInteractionFacades == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service ProfileInteraction object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithProfileInteractionHandlers(
			profileactivityhttp.NewHandler(profileInteractionFacades.ActivityQueryFacade),
			profilereadfacthttp.NewHandler(profileInteractionFacades.ReadFactAppendFacade),
		),
	)
	if filterCatalogFacades == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service FilterCatalogRelease object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithFilterCatalogReleaseHandler(
			filtercataloghttp.NewHandler(filterCatalogFacades),
		),
	)
	if moderationFacades == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service PostModerationCase object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithPostModerationCaseHandler(
			moderationhttp.NewHandler(moderationFacades),
		),
	)
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithMediaAssetHandler(mediaassethttp.NewHandler(mediaService)),
	)
	if originalAccessQuotaService == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service OriginalAccessQuota object composition is not configured")
	}
	if input.mediaRuntime.originalAccessAuditQuery == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service OriginalAccessQuota audit readback composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithOriginalAccessQuotaHandler(
			originalaccessquotahttp.NewHandler(
				originalAccessQuotaService,
				originalaccessquotahttp.WithAuditQuery(
					input.mediaRuntime.originalAccessAuditQuery,
				),
			),
		),
	)
	if input.mediaRuntime.mediaUploadSessionService == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service MediaUploadSession object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithMediaUploadSessionHandler(
			uploadsessionhttp.NewHandler(input.mediaRuntime.mediaUploadSessionService),
		),
	)
	if mediaImageReprocessService == nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service MediaImageReprocessRun object composition is not configured")
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithMediaImageReprocessHandler(
			mediareprocesshttp.NewHandler(mediaImageReprocessService),
		),
	)
	if authorImpactProjectionReader != nil {
		handlerOpts = append(handlerOpts, httpadapter.WithAuthorImpactProjectionReader(authorImpactProjectionReader))
	}
	handlerOpts = append(
		handlerOpts,
		httpadapter.WithViewerReactionReader(viewerReactionReader),
	)

	contentHandler := httpadapter.NewContentHandler(
		feedService,
		postService,
		postQueryService,
		commenthttp.NewHandler(commentService),
		reactionhttp.NewHandler(reactionService),
		reportHandler,
		behaviorService,
		handlerOpts...,
	).Routes()

	internalGraphQLHandler, err := postgraphql.NewInternalPersistedHandler(
		postQueryService,
		input.contractGraphSHA256,
	)
	if err != nil {
		return contentHTTPHandlers{}, fmt.Errorf("content-service internal GraphQL handler invalid: %w", err)
	}
	// 公开 SEO HTML 读面（public-content-web-entry 第一段）：只在部署层
	// 配置公开 Web origin 时暴露；可见性复用 GetPost 公开读语义。正文图片
	// 的公网地址由 CONTENT_PUBLIC_WEB_CDN_ORIGIN + PublicSliceKey 派生。
	var publicWebHandler http.Handler
	if origin := strings.TrimSpace(
		os.Getenv("CONTENT_PUBLIC_WEB_ORIGIN"),
	); origin != "" {
		publicWebHandler = contentpublicweb.NewHandler(
			origin,
			os.Getenv("CONTENT_PUBLIC_WEB_CDN_ORIGIN"),
			postQueryService,
			publicWebSitemapLister{
				facade: postQueryService,
				reader: postQueryReader,
			},
		).Routes()
	}
	return contentHTTPHandlers{
		business:        contentHandler,
		internalGraphQL: internalGraphQLHandler,
		publicWeb:       publicWebHandler,
	}, nil
}

type publicWebSitemapLister struct {
	facade *postapp.PostQueryFacade
	reader postapp.PublicPostIDLister
}

func (lister publicWebSitemapLister) ListPublicPostIDs(
	ctx context.Context,
	limit int,
) ([]string, error) {
	return lister.facade.ListPublicPostIDs(ctx, lister.reader, limit, false)
}

// viewerPostReactionReader 把 content_reaction 聚合的批量点赞读适配为 post
// feed/详情的 FeedViewerReactionReader 端口；跨对象 adapter 只在 cmd 组合。
type viewerPostReactionReader struct {
	store *reactionpersistence.MongoContentReactionStore
}

func (r viewerPostReactionReader) ReadPostLikedFlags(
	ctx context.Context,
	viewerPersonaID string,
	postIDs []string,
) (map[string]bool, error) {
	actor, err := reactiondomain.NewActor(
		reactiondomain.ActorDimensionPersona,
		viewerPersonaID,
	)
	if err != nil {
		return nil, err
	}
	return r.store.ReadPostReactionLikedFlags(ctx, actor, postIDs)
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
