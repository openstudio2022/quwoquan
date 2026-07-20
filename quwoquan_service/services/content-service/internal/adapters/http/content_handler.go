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
	"quwoquan_service/services/content-service/internal/application/authorimpact"
	behaviorapp "quwoquan_service/services/content-service/internal/application/behavior"
	"quwoquan_service/services/content-service/internal/application/commandmeta"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	filtercatalogapp "quwoquan_service/services/content-service/internal/application/content/filter_catalog_release"
	outboundshareapp "quwoquan_service/services/content-service/internal/application/content/outbound_share_fact/command"
	profileinteractionapp "quwoquan_service/services/content-service/internal/application/content/profile_interaction"
	feedapp "quwoquan_service/services/content-service/internal/application/feed"
	importerapp "quwoquan_service/services/content-service/internal/application/importer"
	intersectionapp "quwoquan_service/services/content-service/internal/application/intersection"
	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	moderationapp "quwoquan_service/services/content-service/internal/application/moderation"
	"quwoquan_service/services/content-service/internal/application/ports"
	postapp "quwoquan_service/services/content-service/internal/application/post"
	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
	reportapp "quwoquan_service/services/content-service/internal/application/report"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	postsemantic "quwoquan_service/services/content-service/internal/domain/post/semantic"
	reactiondomain "quwoquan_service/services/content-service/internal/domain/reaction"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type ContentHandler struct {
	feedService               *feedapp.FeedService
	postService               *postapp.Facades
	postQueryService          *postapp.PostQueryFacade
	commentService            *commentapp.Facades
	reactionService           *reactionapp.Facades
	reportService             *reportapp.Facades
	moderationService         *moderationapp.Facades
	outboundShareService      *outboundshareapp.Facades
	profileInteractionService *profileinteractionapp.Facades
	filterCatalogService      *filtercatalogapp.Facades
	mediaService              *mediaapp.Facades
	behaviorService           *behaviorapp.BehaviorService
	importService             *importerapp.BulkImportService
	intersectionService       *intersectionapp.IntersectionService
	authorImpactStore         ports.AuthorImpactStore
	authorImpactEvidenceStore ports.AuthorImpactEvidenceStore
	healthChecker             *rthealth.Checker
}

// postDetailClientWire is the explicit GET /content/posts/{postId} contract.
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

func projectPostDetailForClient(
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

func WithFilterCatalogReleaseService(
	service *filtercatalogapp.Facades,
) ContentHandlerOption {
	return func(handler *ContentHandler) { handler.filterCatalogService = service }
}

func WithModerationService(service *moderationapp.Facades) ContentHandlerOption {
	return func(handler *ContentHandler) { handler.moderationService = service }
}

func WithMediaService(service *mediaapp.Facades) ContentHandlerOption {
	return func(handler *ContentHandler) { handler.mediaService = service }
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
	params := BindGeneratedGetFeedParams(r, 20)
	resp, err := h.feedService.ListFeed(r.Context(), feedapp.ListFeedRequest{
		UserID:          resolveUserID(r),
		ViewerPersonaID: resolvePersonaID(r),
		SessionID:       resolveSessionID(r),
		Identity:        params.Identity,
		Type:            params.Type,
		Sort:            params.Sort,
		ChannelID:       params.ChannelId,
		SubCategory:     params.SubCategory,
		Cursor:          params.Cursor,
		Limit:           params.Limit,
		FeedRequestID:   params.FeedRequestId,
		BlockedKeywords: resolveBlockedKeywords(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleGetAuthorImpact(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET is supported"))
		return
	}
	if h.authorImpactStore == nil {
		writeJSON(w, http.StatusOK, map[string]any{
			"authorId": "",
			"total":    0,
			"items":    []any{},
		})
		return
	}
	authorID := strings.TrimSpace(r.PathValue("subAccountId"))
	if authorID == "" {
		authorID = authorImpactPathSubAccountID(r.URL.Path)
	}
	if authorID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid author id", "missing subAccountId path segment"))
		return
	}
	limit := int64(12)
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		if parsed, err := strconv.ParseInt(raw, 10, 64); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	summary, err := h.authorImpactStore.GetSummary(r.Context(), authorID, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	viewerID := strings.TrimSpace(resolveUserID(r))
	summary = authorimpact.DecorateAuthorImpact(summary, viewerID != "" && viewerID == authorID)
	writeJSON(w, http.StatusOK, summary)
}

func authorImpactPathSubAccountID(path string) string {
	const prefix = "/content/sub-accounts/"
	const suffix = "/author-impact"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	return strings.TrimSpace(strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix))
}

// handleListAuthorImpactEvidence pages the underlying facts behind one author
// impact count (drill-down; R-ID03). Content-anchored, privacy-safe (no actor
// identity surfaced), read-path hydrates content title/cover for the view.
func (h *ContentHandler) handleListAuthorImpactEvidence(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET is supported"))
		return
	}
	authorID := authorImpactEvidencePathSubAccountID(r.URL.Path)
	if authorID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid author id", "missing subAccountId path segment"))
		return
	}
	q := r.URL.Query()
	impactID := strings.TrimSpace(q.Get("impactId"))
	if impactID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "缺少 impactId", "impactId query param is required"))
		return
	}
	snapshotID := strings.TrimSpace(q.Get("evidenceSnapshotId"))
	cursor := strings.TrimSpace(q.Get("cursor"))
	limit := int64(20)
	if raw := strings.TrimSpace(q.Get("limit")); raw != "" {
		if parsed, err := strconv.ParseInt(raw, 10, 64); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	viewerID := strings.TrimSpace(resolveUserID(r))
	viewerIsAuthor := viewerID != "" && viewerID == authorID
	if h.authorImpactEvidenceStore == nil {
		writeJSON(w, http.StatusOK, authorimpact.BuildAuthorImpactEvidencePage(nil, nil, nil, impactID, snapshotID, "", 0, false, viewerIsAuthor))
		return
	}
	raws, nextCursor, hasMore, total, err := h.authorImpactEvidenceStore.ListPageWithTotal(r.Context(), authorID, impactID, cursor, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	posts := make(map[string]*postmodel.Post, len(raws))
	if h.postService != nil {
		for _, raw := range raws {
			cid := strings.TrimSpace(raw.ContentID)
			if cid == "" {
				continue
			}
			if _, exists := posts[cid]; exists {
				continue
			}
			if post, ok, _ := h.postService.GetPostOrTombstone(r.Context(), cid); ok {
				posts[cid] = post
			}
		}
	}
	page := authorimpact.BuildAuthorImpactEvidencePage(
		raws, posts, nil,
		impactID, snapshotID, nextCursor, total, hasMore, viewerIsAuthor,
	)
	writeJSON(w, http.StatusOK, page)
}

func authorImpactEvidencePathSubAccountID(path string) string {
	const prefix = "/content/sub-accounts/"
	const suffix = "/author-impact/evidence"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	return strings.TrimSpace(strings.TrimSuffix(strings.TrimPrefix(path, prefix), suffix))
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
			postports.NewViewerContext(postports.NewPersonaID(resolvePersonaID(r))),
		),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, projectPostDetailForClient(detail))
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
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_ready"),
			"媒体文件正在处理中，请稍后发布",
			"test injected media_not_ready",
		))
		return
	}
	payload, err := BindGeneratedWritableBodyFromRequest(
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
	personaID := resolvePersonaID(r)
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
	if !ok || reporterID == "" {
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
			ReporterID:  reporterID,
			TargetType:  body.TargetType,
			TargetID:    body.TargetID,
			Reason:      body.Reason,
			Description: body.Description,
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *ContentHandler) handleUpdatePostSettings(w http.ResponseWriter, r *http.Request) {
	payload, err := BindGeneratedWritableBodyFromRequest(r, "UpdatePostSettings")
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
		resolvePersonaID(r),
		payload,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, projectPostForClient(post))
}

func (h *ContentHandler) handlePromotePostToWork(w http.ResponseWriter, r *http.Request) {
	payload, err := BindGeneratedWritableBodyFromRequest(r, "PromotePostToWork")
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
		resolvePersonaID(r),
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
	if err := h.postService.DeletePost(r.Context(), postID, resolvePersonaID(r)); err != nil {
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
		w.Header().Set("ETag", hash)
		if strings.TrimSpace(r.Header.Get("If-None-Match")) == hash {
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
	result, err := h.postService.GetHelperRead(r.Context(), contentID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleListUserPosts(w http.ResponseWriter, r *http.Request) {
	viewerID := resolvePersonaID(r)
	userID := viewerID
	if raw := strings.TrimPrefix(r.URL.Path, "/users/"); raw != r.URL.Path {
		if idx := strings.Index(raw, "/posts"); idx > 0 {
			userID = strings.TrimSpace(raw[:idx])
		}
	}
	if raw := strings.TrimPrefix(r.URL.Path, "/content/sub-accounts/"); raw != r.URL.Path {
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
	// /content/posts/{postId}/...
	if len(parts) < 3 {
		return ""
	}
	if parts[0] != "content" || parts[1] != "posts" {
		return ""
	}
	return strings.TrimSpace(strings.SplitN(parts[2], ":", 2)[0])
}
