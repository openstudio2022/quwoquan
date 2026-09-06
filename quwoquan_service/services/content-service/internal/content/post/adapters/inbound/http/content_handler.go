package http

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	rthealth "quwoquan_service/runtime/health"
	rtrec "quwoquan_service/runtime/recommendation"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	mediaasseterrors "quwoquan_service/services/content-service/generated/media/media_asset"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	postsemantic "quwoquan_service/services/content-service/internal/content/post/domain/semantic"
)

type ContentHandler struct {
	feedService                  *feedapp.FeedService
	postService                  *postapp.Facades
	postQueryService             *postapp.PostQueryFacade
	researchReleaseReadback      *postapp.ResearchReleaseReadbackQueryFacet
	commentHandler               commentHTTPHandler
	reactionHandler              contentReactionHTTPHandler
	reportHandler                ReportHTTPHandler
	moderationHandler            postModerationCaseHTTPHandler
	outboundShareHandler         outboundShareHTTPHandler
	profileInteractionHandler    profileInteractionActivityHTTPHandler
	profileReadFactHandler       profileInteractionReadFactHTTPHandler
	mediaAssetHandler            mediaAssetHTTPHandler
	mediaUploadSessionHandler    mediaUploadSessionHTTPHandler
	originalAccessQuotaHandler   originalAccessQuotaHTTPHandler
	filterCatalogReleaseHandler  filterCatalogReleaseHTTPHandler
	mediaImageReprocessHandler   mediaImageReprocessHTTPHandler
	behaviorService              *behaviorapp.BehaviorService
	behaviorHandler              contentBehaviorHTTPHandler
	intersectionVisitHandler     intersectionVisitStateHTTPHandler
	authorImpactProjectionReader ports.AuthorImpactProjectionReader
	viewerReactionReader         feedapp.FeedViewerReactionReader
	healthChecker                *rthealth.Checker
}

// postDetailClientWire is the explicit GET /content/content/posts/{postId} contract.
// Storage/read-model names such as _id and authorDisplayNameSnapshot must not
// leak across this adapter boundary because generated clients consume the
// projection field names below.
type postDetailClientWire struct {
	PostID                  postports.PostID                         `json:"postId"`
	ContentType             postports.ContentType                    `json:"contentType"`
	ContentIdentity         postports.ContentIdentity                `json:"contentIdentity,omitempty"`
	AssistantUsePolicy      string                                   `json:"assistantUsePolicy,omitempty"`
	AuthorID                postports.PersonaID                      `json:"authorId,omitempty"`
	AuthorDisplayName       string                                   `json:"authorDisplayName,omitempty"`
	AuthorAvatarURL         string                                   `json:"authorAvatarUrl,omitempty"`
	Title                   string                                   `json:"title,omitempty"`
	Body                    string                                   `json:"body,omitempty"`
	Summary                 string                                   `json:"summary,omitempty"`
	TagRefs                 []string                                 `json:"tagRefs,omitempty"`
	EntityRefs              []string                                 `json:"entityRefs,omitempty"`
	SemanticMentions        []postports.PostSemanticMentionSlice     `json:"semanticMentions,omitempty"`
	MediaAssetIDs           []string                                 `json:"mediaAssetIds,omitempty"`
	MediaURLs               []string                                 `json:"mediaUrls,omitempty"`
	MediaItems              []postports.PostMediaItemSlice           `json:"mediaItems,omitempty"`
	CoverURL                string                                   `json:"coverUrl,omitempty"`
	ThumbnailURL            string                                   `json:"thumbnailUrl,omitempty"`
	VideoURL                string                                   `json:"videoUrl,omitempty"`
	SourceAttribution       *postports.PostSourceAttributionSlice    `json:"sourceAttribution,omitempty"`
	Width                   int64                                    `json:"width,omitempty"`
	Height                  int64                                    `json:"height,omitempty"`
	DurationMS              int64                                    `json:"durationMs,omitempty"`
	ArticleMarkdown         string                                   `json:"articleMarkdown,omitempty"`
	MarkdownDialect         string                                   `json:"markdownDialect,omitempty"`
	ArticleMarkdownDigest   string                                   `json:"articleMarkdownDigest,omitempty"`
	ArticleAssetManifest    *postports.PostArticleAssetManifestSlice `json:"articleAssetManifest,omitempty"`
	ArticleRenderProfile    *postports.PostArticleRenderProfileSlice `json:"articleRenderProfile,omitempty"`
	ContentVertical         string                                   `json:"contentVertical,omitempty"`
	EntityMentions          []postports.PostEntityMentionSlice       `json:"entityMentions,omitempty"`
	ArticleTemplate         string                                   `json:"articleTemplate,omitempty"`
	ArticleFontPreset       string                                   `json:"articleFontPreset,omitempty"`
	CoverStrategy           string                                   `json:"coverStrategy,omitempty"`
	CoverFrameTimeMS        int64                                    `json:"coverFrameTimeMs,omitempty"`
	Location                *postports.PostLocationSlice             `json:"location,omitempty"`
	LocationName            string                                   `json:"locationName,omitempty"`
	GeoTagRef               string                                   `json:"geoTagRef,omitempty"`
	VisitedAt               time.Time                                `json:"visitedAt,omitempty"`
	PrimaryHomepageID       string                                   `json:"primaryHomepageId,omitempty"`
	CanonicalEntityID       string                                   `json:"canonicalEntityId,omitempty"`
	PrimaryHomepageType     string                                   `json:"primaryHomepageType,omitempty"`
	PrimaryHomepageSnapshot *postports.PostHomepageSnapshotSlice     `json:"primaryHomepageSnapshot,omitempty"`
	// GatheringRef 共同经历回流引用：详情态溯源标锚点。
	GatheringRef string               `json:"gatheringRef,omitempty"`
	Status       postports.PostStatus `json:"status"`
	Visibility              postports.PostVisibility                 `json:"visibility"`
	LikeCount               int64                                    `json:"likeCount"`
	CommentCount            int64                                    `json:"commentCount"`
	ShareCount              int64                                    `json:"shareCount"`
	ViewCount               int64                                    `json:"viewCount"`
	// ViewerLiked viewer 维度点赞态：nil（wire 省略）表示未附着（匿名请求
	// 或附着降级），端侧不得据此回滚本地状态。
	ViewerLiked *bool     `json:"viewerLiked,omitempty"`
	CreatedAt   time.Time `json:"createdAt"`
	UpdatedAt   time.Time `json:"updatedAt"`
	PublishedAt time.Time `json:"publishedAt,omitempty"`
}

func ProjectPostDetailForClient(
	detail postports.PostDetailSlice,
) postDetailClientWire {
	return postDetailClientWire{
		PostID:                  detail.PostID,
		ContentType:             detail.ContentType,
		ContentIdentity:         detail.ContentIdentity,
		AssistantUsePolicy:      detail.AssistantUsePolicy,
		AuthorID:                detail.AuthorPersonaID,
		AuthorDisplayName:       detail.AuthorDisplayName,
		AuthorAvatarURL:         detail.AuthorAvatarURL,
		Title:                   detail.Title,
		Body:                    detail.Body,
		Summary:                 detail.Summary,
		TagRefs:                 detail.TagRefs,
		EntityRefs:              detail.EntityRefs,
		SemanticMentions:        detail.SemanticMentions,
		MediaAssetIDs:           detail.MediaAssetIDs,
		MediaURLs:               detail.MediaURLs,
		MediaItems:              detail.MediaItems,
		CoverURL:                detail.CoverURL,
		ThumbnailURL:            detail.ThumbnailURL,
		VideoURL:                detail.VideoURL,
		SourceAttribution:       detail.SourceAttribution,
		Width:                   detail.Width,
		Height:                  detail.Height,
		DurationMS:              detail.DurationMS,
		ArticleMarkdown:         detail.ArticleMarkdown,
		MarkdownDialect:         detail.MarkdownDialect,
		ArticleMarkdownDigest:   detail.ArticleMarkdownDigest,
		ArticleAssetManifest:    detail.ArticleAssetManifest,
		ArticleRenderProfile:    detail.ArticleRenderProfile,
		ContentVertical:         detail.ContentVertical,
		EntityMentions:          detail.EntityMentions,
		ArticleTemplate:         detail.ArticleTemplate,
		ArticleFontPreset:       detail.ArticleFontPreset,
		CoverStrategy:           detail.CoverStrategy,
		CoverFrameTimeMS:        detail.CoverFrameTimeMS,
		Location:                detail.Location,
		LocationName:            detail.LocationName,
		GeoTagRef:               detail.GeoTagRef,
		VisitedAt:               detail.VisitedAt,
		PrimaryHomepageID:       detail.PrimaryHomepageID,
		CanonicalEntityID:       detail.CanonicalEntityID,
		PrimaryHomepageType:     detail.PrimaryHomepageType,
		PrimaryHomepageSnapshot: detail.PrimaryHomepageSnapshot,
		GatheringRef:            detail.GatheringRef,
		Status:                  detail.Status,
		Visibility:              detail.Visibility,
		LikeCount:               detail.LikeCount,
		CommentCount:            detail.CommentCount,
		ShareCount:              detail.ShareCount,
		ViewCount:               detail.ViewCount,
		CreatedAt:               detail.CreatedAt,
		UpdatedAt:               detail.UpdatedAt,
		PublishedAt:             detail.PublishedAt,
	}
}

func NewContentHandler(
	feedService *feedapp.FeedService,
	postService *postapp.Facades,
	postQueryService *postapp.PostQueryFacade,
	commentHandler commentHTTPHandler,
	reactionHandler contentReactionHTTPHandler,
	reportHandler ReportHTTPHandler,
	behaviorService *behaviorapp.BehaviorService,
	opts ...ContentHandlerOption,
) *ContentHandler {
	h := &ContentHandler{
		feedService:      feedService,
		postService:      postService,
		postQueryService: postQueryService,
		commentHandler:   commentHandler,
		reactionHandler:  reactionHandler,
		reportHandler:    reportHandler,
		behaviorService:  behaviorService,
	}
	for _, opt := range opts {
		opt(h)
	}
	return h
}

// ContentHandlerOption configures the ContentHandler.
type ContentHandlerOption func(*ContentHandler)

// commentHTTPHandler is the narrow route-dispatch contract implemented by the
// Comment object's inbound adapter. Post does not parse Comment wire payloads.
type commentHTTPHandler interface {
	CreateComment(http.ResponseWriter, *http.Request, string)
	ListComments(http.ResponseWriter, *http.Request, string)
	ListCommentReplies(http.ResponseWriter, *http.Request, string, string)
	DeleteComment(http.ResponseWriter, *http.Request, string, string)
	SetCommentPinned(http.ResponseWriter, *http.Request, string, string, bool)
	BindMediaAssetsToComment(http.ResponseWriter, *http.Request, string)
	ListCommentsByAuthor(http.ResponseWriter, *http.Request)
	ListCommentsForPostAuthor(http.ResponseWriter, *http.Request)
	HideComment(http.ResponseWriter, *http.Request, string)
	RestoreComment(http.ResponseWriter, *http.Request, string)
}

// contentReactionHTTPHandler is implemented by ContentReaction's inbound
// adapter. Generated routes remain composed once, while object wire ownership
// remains local to ContentReaction.
type contentReactionHTTPHandler interface {
	LikePost(http.ResponseWriter, *http.Request, string)
	UnlikePost(http.ResponseWriter, *http.Request, string)
	GetContentReactionState(http.ResponseWriter, *http.Request, string)
	ReactToComment(http.ResponseWriter, *http.Request, string)
}

// ReportHTTPHandler is implemented only by Report's object-local inbound
// adapter. Post owns the shared generated router, not Report wire semantics.
type ReportHTTPHandler interface {
	Create(http.ResponseWriter, *http.Request)
	List(http.ResponseWriter, *http.Request)
	ListMine(http.ResponseWriter, *http.Request)
	Get(http.ResponseWriter, *http.Request)
	BeginReview(http.ResponseWriter, *http.Request)
	Dismiss(http.ResponseWriter, *http.Request)
	Resolve(http.ResponseWriter, *http.Request)
	GrantGatheringSafetyTermination(http.ResponseWriter, *http.Request)
	RevokeGatheringSafetyTermination(http.ResponseWriter, *http.Request)
	AuthorizeGatheringSafetyTermination(http.ResponseWriter, *http.Request)
}

type outboundShareHTTPHandler interface {
	AppendOutboundShareFact(http.ResponseWriter, *http.Request)
}

type contentBehaviorHTTPHandler interface {
	Report(http.ResponseWriter, *http.Request)
}

type intersectionVisitStateHTTPHandler interface {
	MarkVisited(http.ResponseWriter, *http.Request)
	GetMyIntersectionSummary(http.ResponseWriter, *http.Request)
	ListMyIntersections(http.ResponseWriter, *http.Request)
	GetObjectIntersections(http.ResponseWriter, *http.Request)
}

type profileInteractionActivityHTTPHandler interface {
	ListReceived(http.ResponseWriter, *http.Request)
	ListSent(http.ResponseWriter, *http.Request)
}

type profileInteractionReadFactHTTPHandler interface {
	Append(http.ResponseWriter, *http.Request)
}

// mediaUploadSessionHTTPHandler is an application-shell dispatch contract.
// Request parsing and response projection remain owned by the
// MediaUploadSession inbound adapter.
type mediaUploadSessionHTTPHandler interface {
	Init(http.ResponseWriter, *http.Request)
	Complete(http.ResponseWriter, *http.Request)
	Abort(http.ResponseWriter, *http.Request)
	Get(http.ResponseWriter, *http.Request)
}

type originalAccessQuotaHTTPHandler interface {
	Reserve(http.ResponseWriter, *http.Request)
	GetAudit(http.ResponseWriter, *http.Request)
}

type mediaImageReprocessHTTPHandler interface {
	Start(http.ResponseWriter, *http.Request)
	Pause(http.ResponseWriter, *http.Request)
	Resume(http.ResponseWriter, *http.Request)
	Rollback(http.ResponseWriter, *http.Request)
	Get(http.ResponseWriter, *http.Request)
}

type mediaAssetHTTPHandler interface {
	GetPublic(http.ResponseWriter, *http.Request)
	GetOwned(http.ResponseWriter, *http.Request)
	GetReference(http.ResponseWriter, *http.Request)
	GetDeliveryReference(http.ResponseWriter, *http.Request)
	RecordProcessingResult(http.ResponseWriter, *http.Request)
	UpdateAccessPolicy(http.ResponseWriter, *http.Request)
	Discard(http.ResponseWriter, *http.Request)
	SelectAutoCover(http.ResponseWriter, *http.Request)
	SelectManualCover(http.ResponseWriter, *http.Request)
}

type postModerationCaseHTTPHandler interface {
	Open(http.ResponseWriter, *http.Request)
	Review(http.ResponseWriter, *http.Request)
	Decide(http.ResponseWriter, *http.Request)
	Supersede(http.ResponseWriter, *http.Request)
	GetCurrent(http.ResponseWriter, *http.Request)
	GetPublicationEligibility(http.ResponseWriter, *http.Request)
}

// filterCatalogReleaseHTTPHandler keeps FilterCatalogRelease wire parsing and
// response projection in its object-owned inbound adapter while the service
// composition root owns the single generated route table.
type filterCatalogReleaseHTTPHandler interface {
	Stage(http.ResponseWriter, *http.Request)
	Activate(http.ResponseWriter, *http.Request)
	Rollback(http.ResponseWriter, *http.Request)
	GetActive(http.ResponseWriter, *http.Request)
}

func WithHealthChecker(c *rthealth.Checker) ContentHandlerOption {
	return func(h *ContentHandler) { h.healthChecker = c }
}

func WithResearchReleaseReadback(
	facet *postapp.ResearchReleaseReadbackQueryFacet,
) ContentHandlerOption {
	return func(handler *ContentHandler) {
		handler.researchReleaseReadback = facet
	}
}

func WithOutboundShareHandler(service outboundShareHTTPHandler) ContentHandlerOption {
	return func(handler *ContentHandler) { handler.outboundShareHandler = service }
}

// WithViewerReactionReader 注入 viewer 点赞事实批量读（详情 viewerLiked 附着）。
func WithViewerReactionReader(
	reader feedapp.FeedViewerReactionReader,
) ContentHandlerOption {
	return func(handler *ContentHandler) { handler.viewerReactionReader = reader }
}

func WithContentBehaviorHandler(handler contentBehaviorHTTPHandler) ContentHandlerOption {
	return func(contentHandler *ContentHandler) { contentHandler.behaviorHandler = handler }
}

func WithIntersectionVisitStateHandler(
	handler intersectionVisitStateHTTPHandler,
) ContentHandlerOption {
	return func(contentHandler *ContentHandler) {
		contentHandler.intersectionVisitHandler = handler
	}
}

func WithProfileInteractionHandlers(
	activity profileInteractionActivityHTTPHandler,
	readFact profileInteractionReadFactHTTPHandler,
) ContentHandlerOption {
	return func(handler *ContentHandler) {
		handler.profileInteractionHandler = activity
		handler.profileReadFactHandler = readFact
	}
}

func WithPostModerationCaseHandler(handler postModerationCaseHTTPHandler) ContentHandlerOption {
	return func(contentHandler *ContentHandler) { contentHandler.moderationHandler = handler }
}

func WithMediaAssetHandler(handler mediaAssetHTTPHandler) ContentHandlerOption {
	return func(contentHandler *ContentHandler) { contentHandler.mediaAssetHandler = handler }
}

func WithMediaUploadSessionHandler(
	handler mediaUploadSessionHTTPHandler,
) ContentHandlerOption {
	return func(contentHandler *ContentHandler) {
		contentHandler.mediaUploadSessionHandler = handler
	}
}

func WithOriginalAccessQuotaHandler(
	handler originalAccessQuotaHTTPHandler,
) ContentHandlerOption {
	return func(contentHandler *ContentHandler) {
		contentHandler.originalAccessQuotaHandler = handler
	}
}

func WithFilterCatalogReleaseHandler(
	handler filterCatalogReleaseHTTPHandler,
) ContentHandlerOption {
	return func(contentHandler *ContentHandler) {
		contentHandler.filterCatalogReleaseHandler = handler
	}
}

func WithMediaImageReprocessHandler(
	handler mediaImageReprocessHTTPHandler,
) ContentHandlerOption {
	return func(contentHandler *ContentHandler) {
		contentHandler.mediaImageReprocessHandler = handler
	}
}

func WithAuthorImpactProjectionReader(reader ports.AuthorImpactProjectionReader) ContentHandlerOption {
	return func(h *ContentHandler) { h.authorImpactProjectionReader = reader }
}

func (h *ContentHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", h.handleHealthz)
	mux.HandleFunc("/livez", h.handleHealthz)
	mux.HandleFunc("/startupz", h.handleHealthz)
	mux.HandleFunc("/metrics/rec", h.handleRecMetrics)
	mux.HandleFunc("/metrics/rec/engagement", h.handleEngagementMetrics)
	mux.HandleFunc("/metrics/rec/behavior-attribution", h.handleBehaviorAttributionMetrics)
	mux.HandleFunc("/metrics/rec/prometheus", h.handlePrometheusMetrics)
	mux.HandleFunc("/admin/content/semantic-mentions:apply", h.handleApplySemanticMentionGovernanceEvent)
	RegisterGeneratedRoutes(mux, h)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
		ctx := commandmeta.WithIdempotencyKey(r.Context(), idempotencyKey)
		mux.ServeHTTP(w, r.WithContext(ctx))
	})
}

func (h *ContentHandler) handleApplySemanticMentionGovernanceEvent(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only POST"))
		return
	}
	var event postsemantic.GovernanceEvent
	if err := json.NewDecoder(r.Body).Decode(&event); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"治理事件解析失败",
			err.Error(),
		))
		return
	}
	report, err := h.postService.ApplySemanticMentionGovernanceEvent(r.Context(), event)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, report)
}

func (h *ContentHandler) handleHealthz(w http.ResponseWriter, r *http.Request) {
	if h.healthChecker != nil {
		h.healthChecker.Handler()(w, r)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ContentHandler) handleRecMetrics(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, rtrec.SnapshotEngagementMetrics())
}

func (h *ContentHandler) handleEngagementMetrics(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, rtrec.SnapshotEngagementMetrics())
}

type behaviorAttributionMetricSeries struct {
	Labels map[string]string `json:"labels"`
	Value  float64           `json:"value"`
}

func (h *ContentHandler) handleBehaviorAttributionMetrics(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET is supported"))
		return
	}
	families, err := prometheus.DefaultGatherer.Gather()
	if err != nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable("behavior attribution metrics gather: "+err.Error()))
		return
	}
	series := make([]behaviorAttributionMetricSeries, 0)
	for _, family := range families {
		if family.GetName() != "recommendation_behavior_by_attribution_total" {
			continue
		}
		for _, metric := range family.GetMetric() {
			labels := make(map[string]string, len(metric.GetLabel()))
			for _, label := range metric.GetLabel() {
				labels[label.GetName()] = label.GetValue()
			}
			series = append(series, behaviorAttributionMetricSeries{
				Labels: labels,
				Value:  metric.GetCounter().GetValue(),
			})
		}
		break
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"source":    "recommendation_behavior_by_attribution_total",
		"freshness": "process_realtime",
		"series":    series,
	})
}

func (h *ContentHandler) handlePrometheusMetrics(w http.ResponseWriter, r *http.Request) {
	promhttp.Handler().ServeHTTP(w, r)
}

func (h *ContentHandler) handleGetFeed(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET is supported"))
		return
	}
	params, err := BindGeneratedGetFeedParams(r)
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"invalid feed pagination",
			err.Error(),
		))
		return
	}
	recommendationActorID := ResolveRecommendationActorID(r)
	resp, err := h.feedService.ListFeed(r.Context(), feedapp.ListFeedRequest{
		UserID:          recommendationActorID,
		ViewerPersonaID: ResolvePersonaID(r),
		SessionID:       resolveSessionID(r),
		Identity:        params.Identity,
		Type:            params.Type,
		Sort:            params.Sort,
		ChannelID:       params.ChannelId,
		SubCategory:     params.SubCategory,
		Cursor:          params.Cursor,
		Limit:           params.Limit,
		FeedRequestID:     params.FeedRequestId,
		BlockedKeywords:   ResolveBlockedKeywords(r),
		ResearchPrincipal: requestHasResearchRole(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleGetPost(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET is supported"))
		return
	}
	postID := strings.TrimSpace(r.PathValue("postId"))
	if postID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid post id", "missing postId path segment"))
		return
	}
	viewerPersonaID := ResolvePersonaID(r)
	detail, err := h.postQueryService.GetPost(
		r.Context(),
		postports.NewPostDetailQuery(
			postports.NewPostID(postID),
			postports.NewViewerContext(postports.NewPersonaID(viewerPersonaID)),
			requestHasResearchRole(r),
		),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	wire := ProjectPostDetailForClient(detail)
	// viewerLiked 附着与 feed 同一纪律：匿名/未装配保持 null，读失败静默降级。
	if h.viewerReactionReader != nil && strings.TrimSpace(viewerPersonaID) != "" {
		if flags, likedErr := h.viewerReactionReader.ReadPostLikedFlags(
			r.Context(),
			viewerPersonaID,
			[]string{postID},
		); likedErr == nil {
			liked := flags[postID]
			wire.ViewerLiked = &liked
		}
	}
	writeJSON(w, http.StatusOK, wire)
}

// projectPostForClient strips fields that must never be client-visible:
//   - embedding: privacy=never_expose (fields.yaml)
//   - moderationStatus: visibility=platform-ops (fields.yaml)
func projectPostForClient(post any) map[string]any {
	b, err := json.Marshal(post)
	if err != nil {
		return map[string]any{}
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		return map[string]any{}
	}
	delete(m, "embedding")
	delete(m, "moderationStatus")
	delete(m, "_id")
	if postID, ok := m["postId"].(string); ok && strings.TrimSpace(postID) != "" {
		return m
	}
	if id, ok := m["id"].(string); ok && strings.TrimSpace(id) != "" {
		m["postId"] = id
		delete(m, "id")
	}
	return m
}

func (h *ContentHandler) handleSubmitPostPublication(
	w http.ResponseWriter,
	r *http.Request,
) {
	if shouldHonorTestErrorInject(r, "CONTENT.USER.media_not_ready") {
		writeHTTPError(
			w,
			r,
			mediaasseterrors.AppErrorFromMediaNotReady(
				"test injected media_not_ready",
			),
		)
		return
	}
	payload, err := BindGeneratedRequestBodyFromRequest(
		r,
		"SubmitPostPublication",
	)
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体字段不合法",
			err.Error(),
		))
		return
	}
	personaID := ResolvePersonaID(r)
	if personaID == "" {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromUnauthorized(
				"verified persona actor missing for SubmitPostPublication",
			),
		)
		return
	}
	content, err := postapp.DecodeSubmitPostPublicationContent(payload)
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布内容格式不合法",
			err.Error(),
		))
		return
	}
	publishIntentID, _ := payload["publishIntentId"].(string)
	localDraftID, _ := payload["localDraftId"].(string)
	receipt, err := h.postService.SubmitPostPublication(
		r.Context(),
		postapp.SubmitPostPublicationCommand{
			PublishIntentID: strings.TrimSpace(publishIntentID),
			LocalDraftID:    strings.TrimSpace(localDraftID),
			AuthorID:        personaID,
			Content:         content,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusAccepted, receipt)
}

func shouldHonorTestErrorInject(r *http.Request, code string) bool {
	appEnv := strings.ToLower(strings.TrimSpace(os.Getenv("APP_ENV")))
	if appEnv == "prod" {
		return false
	}
	return strings.TrimSpace(r.Header.Get("X-Test-Error-Inject")) == code
}

func (h *ContentHandler) handleUpdatePostSettings(w http.ResponseWriter, r *http.Request) {
	payload, err := BindGeneratedRequestBodyFromRequest(r, "UpdatePostSettings")
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体字段不合法",
			err.Error(),
		))
		return
	}
	postID := postIDFromPath(r.URL.Path)
	post, err := h.postService.UpdatePostSettings(
		r.Context(),
		postID,
		ResolvePersonaID(r),
		payload,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, projectPostForClient(post))
}

func (h *ContentHandler) handlePromotePostToWork(w http.ResponseWriter, r *http.Request) {
	payload, err := BindGeneratedRequestBodyFromRequest(r, "PromotePostToWork")
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体字段不合法",
			err.Error(),
		))
		return
	}
	postID := postIDFromPath(r.URL.Path)
	post, err := h.postService.PromotePostToWork(
		r.Context(),
		postID,
		ResolvePersonaID(r),
		payload,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, projectPostForClient(post))
}

func (h *ContentHandler) handleDeletePost(w http.ResponseWriter, r *http.Request) {
	postID := postIDFromPath(r.URL.Path)
	receipt, err := h.postService.DeletePost(r.Context(), postID, ResolvePersonaID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, receipt)
}

func (h *ContentHandler) handleGetAppConfig(w http.ResponseWriter, r *http.Request) {
	payload := h.postService.GetAppConfig()
	hash := payload.ConfigHash
	if hash != "" {
		etag := `"` + hash + `"`
		w.Header().Set("ETag", etag)
		if strings.TrimSpace(r.Header.Get("If-None-Match")) == etag {
			w.WriteHeader(http.StatusNotModified)
			return
		}
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *ContentHandler) handleGetCounters(w http.ResponseWriter, r *http.Request, postID string) {
	counters, err := h.postService.GetCounters(r.Context(), postID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, counters)
}

func (h *ContentHandler) handleGetHelperRead(w http.ResponseWriter, r *http.Request) {
	contentID := pathParamAfter(r.URL.Path, "/content/helper-read/", "")
	result, err := h.postQueryService.GetHelperRead(
		r.Context(),
		contentID,
		requestHasResearchRole(r),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleListUserPosts(w http.ResponseWriter, r *http.Request) {
	viewerID := ResolvePersonaID(r)
	userID := viewerID
	if raw := strings.TrimPrefix(r.URL.Path, "/users/"); raw != r.URL.Path {
		if idx := strings.Index(raw, "/posts"); idx > 0 {
			userID = strings.TrimSpace(raw[:idx])
		}
	}
	if raw := strings.TrimPrefix(r.URL.Path, "/content/personas/"); raw != r.URL.Path {
		if idx := strings.Index(raw, "/posts"); idx > 0 {
			userID = strings.TrimSpace(raw[:idx])
		}
	}
	if queryUserID := strings.TrimSpace(r.URL.Query().Get("userId")); queryUserID != "" {
		userID = queryUserID
	}
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	identity := strings.TrimSpace(r.URL.Query().Get("identity"))
	postType := strings.TrimSpace(r.URL.Query().Get("type"))
	visibility := strings.TrimSpace(r.URL.Query().Get("visibility"))
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	page, err := h.postQueryService.ListUserPosts(
		r.Context(),
		postports.NewAuthorPostPageQuery(
			postports.NewPersonaID(userID),
			postports.NewViewerContext(postports.NewPersonaID(viewerID)),
			postports.ContentIdentity(identity),
			postports.ContentType(postType),
			postports.PostVisibility(visibility),
			cursor,
			limit,
			requestHasResearchRole(r),
		),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func (h *ContentHandler) handleGetGatheringSocialProof(
	w http.ResponseWriter,
	r *http.Request,
) {
	anchorKind := ""
	objectID := ""
	if raw := strings.TrimPrefix(r.URL.Path, "/content/social-proof/"); raw != r.URL.Path {
		parts := strings.SplitN(raw, "/", 2)
		if len(parts) == 2 {
			anchorKind = strings.TrimSpace(parts[0])
			objectID = strings.TrimSpace(parts[1])
		}
	}
	summary, err := h.postQueryService.GetGatheringSocialProof(
		r.Context(),
		anchorKind,
		objectID,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"anchorKind":       summary.AnchorKind,
		"objectId":         summary.ObjectID,
		"publishedCount":   summary.PublishedCount,
		"formedCount":      summary.FormedCount,
		"experiencedCount": summary.ExperiencedCount,
	})
}

func (h *ContentHandler) handleListPostsByGathering(
	w http.ResponseWriter,
	r *http.Request,
) {
	gatheringID := ""
	if raw := strings.TrimPrefix(r.URL.Path, "/content/gatherings/"); raw != r.URL.Path {
		if idx := strings.Index(raw, "/posts"); idx > 0 {
			gatheringID = strings.TrimSpace(raw[:idx])
		}
	}
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	page, err := h.postQueryService.ListPostsByGathering(
		r.Context(),
		postports.NewGatheringPostPageQuery(
			gatheringID,
			cursor,
			limit,
			requestHasResearchRole(r),
		),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func postIDFromPath(path string) string {
	p := strings.TrimSpace(path)
	if p == "" {
		return ""
	}
	parts := strings.Split(strings.Trim(p, "/"), "/")
	// /content/content/posts/{postId}/...
	if len(parts) < 3 {
		return ""
	}
	if parts[0] != "content" || parts[1] != "posts" {
		return ""
	}
	return strings.TrimSpace(strings.SplitN(parts[2], ":", 2)[0])
}
