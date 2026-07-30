package http

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	rthealth "quwoquan_service/runtime/health"
	"quwoquan_service/runtime/operation"
	rtrec "quwoquan_service/runtime/recommendation"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	mediaasseterrors "quwoquan_service/services/content-service/generated/media/media_asset"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	outboundshareapp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/application/command"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	"quwoquan_service/services/content-service/internal/content/post/application/commandmeta"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	importerapp "quwoquan_service/services/content-service/internal/content/post/application/importer"
	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
	mediaapp "quwoquan_service/services/content-service/internal/content/post/application/media"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	postsemantic "quwoquan_service/services/content-service/internal/content/post/domain/semantic"
	profileinteractionapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	mediareprocessapp "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/application"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
)

type ContentHandler struct {
	feedService                 *feedapp.FeedService
	postService                 *postapp.Facades
	postQueryService            *postapp.PostQueryFacade
	commentService              *commentapp.Facades
	reactionService             *reactionapp.Facades
	reportService               *reportapp.Facades
	moderationService           *moderationapp.Facades
	outboundShareService        *outboundshareapp.Facades
	profileInteractionService   *profileinteractionapp.Facades
	mediaService                *mediaapp.Facades
	mediaUploadSessionHandler   mediaUploadSessionHTTPHandler
	filterCatalogReleaseHandler filterCatalogReleaseHTTPHandler
	mediaImageReprocessService  *mediareprocessapp.Service
	behaviorService             *behaviorapp.BehaviorService
	importService               *importerapp.BulkImportService
	intersectionService         *intersectionapp.IntersectionService
	authorImpactStore           ports.AuthorImpactStore
	authorImpactEvidenceStore   ports.AuthorImpactEvidenceStore
	healthChecker               *rthealth.Checker
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
	Status                  postports.PostStatus                     `json:"status"`
	Visibility              postports.PostVisibility                 `json:"visibility"`
	LikeCount               int64                                    `json:"likeCount"`
	CommentCount            int64                                    `json:"commentCount"`
	ShareCount              int64                                    `json:"shareCount"`
	ViewCount               int64                                    `json:"viewCount"`
	CreatedAt               time.Time                                `json:"createdAt"`
	UpdatedAt               time.Time                                `json:"updatedAt"`
	PublishedAt             time.Time                                `json:"publishedAt,omitempty"`
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
	commentService *commentapp.Facades,
	reactionService *reactionapp.Facades,
	reportService *reportapp.Facades,
	behaviorService *behaviorapp.BehaviorService,
	opts ...ContentHandlerOption,
) *ContentHandler {
	h := &ContentHandler{
		feedService:      feedService,
		postService:      postService,
		postQueryService: postQueryService,
		commentService:   commentService,
		reactionService:  reactionService,
		reportService:    reportService,
		behaviorService:  behaviorService,
	}
	for _, opt := range opts {
		opt(h)
	}
	return h
}

// ContentHandlerOption configures the ContentHandler.
type ContentHandlerOption func(*ContentHandler)

// mediaUploadSessionHTTPHandler is an application-shell dispatch contract.
// Request parsing and response projection remain owned by the
// MediaUploadSession inbound adapter.
type mediaUploadSessionHTTPHandler interface {
	Init(http.ResponseWriter, *http.Request)
	Complete(http.ResponseWriter, *http.Request)
	Abort(http.ResponseWriter, *http.Request)
	Get(http.ResponseWriter, *http.Request)
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

func WithBulkImportService(svc *importerapp.BulkImportService) ContentHandlerOption {
	return func(h *ContentHandler) { h.importService = svc }
}

func WithHealthChecker(c *rthealth.Checker) ContentHandlerOption {
	return func(h *ContentHandler) { h.healthChecker = c }
}

func WithOutboundShareService(service *outboundshareapp.Facades) ContentHandlerOption {
	return func(handler *ContentHandler) { handler.outboundShareService = service }
}

func WithProfileInteractionService(
	service *profileinteractionapp.Facades,
) ContentHandlerOption {
	return func(handler *ContentHandler) { handler.profileInteractionService = service }
}

func WithModerationService(service *moderationapp.Facades) ContentHandlerOption {
	return func(handler *ContentHandler) { handler.moderationService = service }
}

func WithMediaService(service *mediaapp.Facades) ContentHandlerOption {
	return func(handler *ContentHandler) { handler.mediaService = service }
}

func WithMediaUploadSessionHandler(
	handler mediaUploadSessionHTTPHandler,
) ContentHandlerOption {
	return func(contentHandler *ContentHandler) {
		contentHandler.mediaUploadSessionHandler = handler
	}
}

func WithFilterCatalogReleaseHandler(
	handler filterCatalogReleaseHTTPHandler,
) ContentHandlerOption {
	return func(contentHandler *ContentHandler) {
		contentHandler.filterCatalogReleaseHandler = handler
	}
}

func WithMediaImageReprocessService(
	service *mediareprocessapp.Service,
) ContentHandlerOption {
	return func(handler *ContentHandler) { handler.mediaImageReprocessService = service }
}

// WithIntersectionService 注入交集统一体验服务（事实/概率合并、冷却窗口、已读水位）。
func WithIntersectionService(svc *intersectionapp.IntersectionService) ContentHandlerOption {
	return func(h *ContentHandler) { h.intersectionService = svc }
}

func WithAuthorImpactStore(store ports.AuthorImpactStore) ContentHandlerOption {
	return func(h *ContentHandler) { h.authorImpactStore = store }
}

func WithAuthorImpactEvidenceStore(store ports.AuthorImpactEvidenceStore) ContentHandlerOption {
	return func(h *ContentHandler) { h.authorImpactEvidenceStore = store }
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
	mux.HandleFunc("/admin/import", h.handleBulkImport)
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
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "metrics_unavailable"),
			"推荐指标暂不可用",
			err.Error(),
		))
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

func (h *ContentHandler) handleBulkImport(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only POST"))
		return
	}
	if h.importService == nil {
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "unavailable"),
			"导入服务未启用",
			"bulk import not configured (no MongoDB)",
		))
		return
	}
	defer r.Body.Close()
	result, err := h.importService.ImportNDJSON(r.Context(), r.Body)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"total":    result.Total,
		"success":  result.Success,
		"failed":   result.Failed,
		"duration": result.Duration.String(),
	})
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
		FeedRequestID:   params.FeedRequestId,
		BlockedKeywords: ResolveBlockedKeywords(r),
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
	detail, err := h.postQueryService.GetPost(
		r.Context(),
		postports.NewPostDetailQuery(
			postports.NewPostID(postID),
			postports.NewViewerContext(postports.NewPersonaID(ResolvePersonaID(r))),
		),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, ProjectPostDetailForClient(detail))
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
	encodedContent, err := json.Marshal(payload)
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"发布内容格式不合法",
			err.Error(),
		))
		return
	}
	var content postmodel.Post
	if err := json.Unmarshal(encodedContent, &content); err != nil {
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

func (h *ContentHandler) handleCreateReport(w http.ResponseWriter, r *http.Request) {
	if h.reportService == nil {
		h.handleNotImplemented(w, r, "CreateReport")
		return
	}
	var body struct {
		TargetType  reportmodel.TargetType `json:"targetType"`
		TargetID    string                 `json:"targetId"`
		Reason      reportmodel.Reason     `json:"reason"`
		Description string                 `json:"description"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	currentOperation, ok := operation.FromContext(r.Context())
	reporterID := strings.TrimSpace(currentOperation.Actor.PersonaID)
	reporterAccountID := strings.TrimSpace(currentOperation.Actor.AccountID)
	if !ok || reporterID == "" || reporterAccountID == "" {
		writeHTTPError(
			w,
			r,
			rterr.NewAppError(
				rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "unauthorized"),
				"请先登录",
				"trusted persona actor missing for CreateReport",
			),
		)
		return
	}
	_, err := h.reportService.CreateReport(
		r.Context(),
		reportapp.CreateReportCommand{
			ReporterID:        reporterID,
			ReporterAccountID: reporterAccountID,
			TargetType:        body.TargetType,
			TargetID:          body.TargetID,
			Reason:            body.Reason,
			Description:       body.Description,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
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
	if err := h.postService.DeletePost(r.Context(), postID, ResolvePersonaID(r)); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"postId": postID, "status": "deleted"})
}

func (h *ContentHandler) handleLikePost(w http.ResponseWriter, r *http.Request, postID string) {
	if h.reactionService == nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable("ContentReaction facades are not configured"))
		return
	}
	actor, err := resolveReactionActor(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := h.reactionService.LikePost(
		r.Context(),
		reactionapp.LikePostCommand{PostID: strings.TrimSpace(postID), Actor: actor},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"reactionId": result.ReactionID,
		"postId":     postID,
		"version":    result.Version,
		"liked":      result.Liked,
		"changed":    result.Changed,
		"replayed":   result.Replayed,
	})
}

func (h *ContentHandler) handleUnlikePost(w http.ResponseWriter, r *http.Request, postID string) {
	if h.reactionService == nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable("ContentReaction facades are not configured"))
		return
	}
	actor, err := resolveReactionActor(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := h.reactionService.UnlikePost(
		r.Context(),
		reactionapp.UnlikePostCommand{PostID: strings.TrimSpace(postID), Actor: actor},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"reactionId": result.ReactionID,
		"postId":     postID,
		"version":    result.Version,
		"liked":      result.Liked,
		"changed":    result.Changed,
		"replayed":   result.Replayed,
	})
}

func (h *ContentHandler) handleGetReactionState(w http.ResponseWriter, r *http.Request, postID string) {
	if h.reactionService == nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable("ContentReaction facades are not configured"))
		return
	}
	actor, err := resolveReactionActor(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	slice, err := h.reactionService.GetContentReactionState(
		r.Context(),
		reactionapp.GetContentReactionStateQuery{PostID: strings.TrimSpace(postID), Actor: actor},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	payload := map[string]any{
		"found":   slice.Found,
		"postId":  slice.PostID,
		"liked":   slice.Liked,
		"version": slice.Version,
	}
	if !slice.UpdatedAt.IsZero() {
		payload["updatedAt"] = slice.UpdatedAt.UTC().Format(time.RFC3339Nano)
	}
	writeJSON(w, http.StatusOK, payload)
}

func resolveReactionActor(r *http.Request) (reactiondomain.Actor, error) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return reactiondomain.Actor{}, contentgenerated.AppErrorFromUnauthorized(
			"ContentReaction requires a verified persona or device principal",
		)
	}
	if personaID := strings.TrimSpace(principal.Actor.PersonaID); personaID != "" {
		return reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, personaID)
	}
	if deviceActorID := strings.TrimSpace(principal.Actor.DeviceActorID); deviceActorID != "" {
		return reactiondomain.NewActor(reactiondomain.ActorDimensionDevice, deviceActorID)
	}
	return reactiondomain.Actor{}, contentgenerated.AppErrorFromUnauthorized(
		"ContentReaction principal has no persona or device actor",
	)
}

func (h *ContentHandler) handleGetAppConfig(w http.ResponseWriter, r *http.Request) {
	payload := h.postService.GetAppConfig()
	hash, _ := payload["configHash"].(string)
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

func commentIDFromPath(path string) string {
	parts := strings.Split(strings.Trim(strings.TrimSpace(path), "/"), "/")
	for i, p := range parts {
		if p == "comments" && i+1 < len(parts) {
			return strings.TrimSpace(parts[i+1])
		}
	}
	return ""
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
	result, err := h.postQueryService.GetHelperRead(r.Context(), contentID)
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
