package http

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus/promhttp"

	rterr "quwoquan_service/runtime/errors"
	rthealth "quwoquan_service/runtime/health"
	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/services/content-service/internal/application"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postsemantic "quwoquan_service/services/content-service/internal/domain/post/semantic"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

type ContentHandler struct {
	feedService               *application.FeedService
	postService               *application.PostService
	reportService             *application.ReportService
	behaviorService           *application.BehaviorService
	importService             *application.BulkImportService
	intersectionService       *application.IntersectionService
	authorImpactStore         *persistence.AuthorImpactStore
	authorImpactEvidenceStore *persistence.AuthorImpactEvidenceStore
	healthChecker             *rthealth.Checker
}

func NewContentHandler(
	feedService *application.FeedService,
	postService *application.PostService,
	reportService *application.ReportService,
	behaviorService *application.BehaviorService,
	opts ...ContentHandlerOption,
) *ContentHandler {
	h := &ContentHandler{
		feedService:     feedService,
		postService:     postService,
		reportService:   reportService,
		behaviorService: behaviorService,
	}
	for _, opt := range opts {
		opt(h)
	}
	return h
}

// ContentHandlerOption configures the ContentHandler.
type ContentHandlerOption func(*ContentHandler)

func WithBulkImportService(svc *application.BulkImportService) ContentHandlerOption {
	return func(h *ContentHandler) { h.importService = svc }
}

func WithHealthChecker(c *rthealth.Checker) ContentHandlerOption {
	return func(h *ContentHandler) { h.healthChecker = c }
}

// WithIntersectionService 注入交集统一体验服务（事实/概率合并、冷却窗口、已读水位）。
func WithIntersectionService(svc *application.IntersectionService) ContentHandlerOption {
	return func(h *ContentHandler) { h.intersectionService = svc }
}

func WithAuthorImpactStore(store *persistence.AuthorImpactStore) ContentHandlerOption {
	return func(h *ContentHandler) { h.authorImpactStore = store }
}

func WithAuthorImpactEvidenceStore(store *persistence.AuthorImpactEvidenceStore) ContentHandlerOption {
	return func(h *ContentHandler) { h.authorImpactEvidenceStore = store }
}

func (h *ContentHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", h.handleHealthz)
	mux.HandleFunc("/livez", h.handleHealthz)
	mux.HandleFunc("/startupz", h.handleHealthz)
	mux.HandleFunc("/metrics/rec", h.handleRecMetrics)
	mux.HandleFunc("/metrics/rec/engagement", h.handleEngagementMetrics)
	mux.HandleFunc("/metrics/rec/prometheus", h.handlePrometheusMetrics)
	mux.HandleFunc("/admin/import", h.handleBulkImport)
	mux.HandleFunc("/admin/content/semantic-mentions:apply", h.handleApplySemanticMentionGovernanceEvent)
	mux.HandleFunc("GET /v1/config/app", h.handleGetAppConfig)
	mux.HandleFunc("GET /v1/content/sub-accounts/{subAccountId}/author-impact", h.handleGetAuthorImpact)
	mux.HandleFunc("/v1/content/users/posts", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET"))
			return
		}
		h.handleListUserPosts(w, r)
	})
	mux.HandleFunc("/v1/content/reports", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			h.handleListReports(w, r)
		case http.MethodPost:
			h.handleCreateReport(w, r)
		default:
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET/POST"))
		}
	})
	mux.HandleFunc("/v1/content/reports/", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet:
			h.handleGetReport(w, r)
		case http.MethodPatch:
			h.handleResolveReport(w, r)
		default:
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET/PATCH"))
		}
	})
	mux.HandleFunc("GET /v1/content/sub-accounts/{subAccountId}/interactions/received", h.handleListProfileInteractionActivitiesReceived)
	mux.HandleFunc("GET /v1/content/sub-accounts/{subAccountId}/interactions/sent", h.handleListProfileInteractionActivitiesSent)
	mux.HandleFunc("GET /v1/content/posts/search", h.handleSearchPosts)
	RegisterGeneratedRoutes(mux, h)
	return mux
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
	resp, err := h.feedService.ListFeed(r.Context(), application.ListFeedRequest{
		UserID:          resolveUserID(r),
		SessionID:       resolveSessionID(r),
		Identity:        params.Identity,
		Type:            params.Type,
		Sort:            params.Sort,
		SubCategory:     params.SubCategory,
		Cursor:          params.Cursor,
		Limit:           params.Limit,
		FeedRequestID:   params.FeedRequestId,
		BlockedUserIDs:  resolveBlockedUserIDs(r),
		BlockedKeywords: resolveBlockedKeywords(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleSearchPosts(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET is supported"))
		return
	}
	q := r.URL.Query()
	limit, err := strconv.Atoi(q.Get("limit"))
	if err != nil || limit <= 0 {
		limit = 20
	}
	items, nextCursor, err := h.postService.SearchPosts(r.Context(), application.SearchPostsRequest{
		Query:         q.Get("query"),
		Identity:      q.Get("identity"),
		RequestedType: q.Get("type"),
		CategoryID:    q.Get("categoryId"),
		SubCategory:   q.Get("subCategory"),
		Cursor:        q.Get("cursor"),
		Limit:         limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":  items,
		"cursor": nextCursor,
	})
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
	summary = application.DecorateAuthorImpact(summary, viewerID != "" && viewerID == authorID)
	writeJSON(w, http.StatusOK, summary)
}

func authorImpactPathSubAccountID(path string) string {
	const prefix = "/v1/content/sub-accounts/"
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
		writeJSON(w, http.StatusOK, application.BuildAuthorImpactEvidencePage(nil, nil, nil, impactID, snapshotID, "", 0, false, viewerIsAuthor))
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
	page := application.BuildAuthorImpactEvidencePage(
		raws, posts, nil,
		impactID, snapshotID, nextCursor, total, hasMore, viewerIsAuthor,
	)
	writeJSON(w, http.StatusOK, page)
}

func authorImpactEvidencePathSubAccountID(path string) string {
	const prefix = "/v1/content/sub-accounts/"
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
	postID := strings.TrimPrefix(r.URL.Path, "/v1/content/posts/")
	if postID == "" || strings.Contains(postID, "/") {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid post id", "missing postId path segment"))
		return
	}
	post, ok, deleted, forbidden := h.postService.GetPostForViewer(
		r.Context(),
		postID,
		resolveUserID(r),
		resolveViewerCircleIDs(r),
	)
	if !ok {
		if deleted {
			writeHTTPError(w, r, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
				"内容已删除",
				"post deleted",
			))
			return
		}
		if forbidden {
			writeHTTPError(w, r, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "forbidden"),
				"无权查看该内容",
				"post visibility blocked",
			))
			return
		}
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "post_not_found"),
			"内容不存在",
			"post not found",
		))
		return
	}
	writeJSON(w, http.StatusOK, projectPostForClient(post))
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
	return m
}

func (h *ContentHandler) handleCreatePost(w http.ResponseWriter, r *http.Request) {
	if shouldHonorTestErrorInject(r, "CONTENT.USER.media_not_ready") {
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_ready"),
			"媒体文件正在处理中，请稍后发布",
			"test injected media_not_ready",
		))
		return
	}
	payload, err := BindGeneratedWritableBodyFromRequest(r, "CreatePost")
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体字段不合法",
			err.Error(),
		))
		return
	}
	subAccountID := strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Id"))
	if subAccountID == "" {
		subAccountID = resolveUserID(r)
	}
	if subAccountID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"缺少 X-Client-Sub-Account-Id",
			"missing X-Client-Sub-Account-Id",
		))
		return
	}
	payload["authorId"] = subAccountID
	post, err := h.postService.CreatePost(r.Context(), payload)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, post)
}

func shouldHonorTestErrorInject(r *http.Request, code string) bool {
	appEnv := strings.ToLower(strings.TrimSpace(os.Getenv("APP_ENV")))
	if appEnv == "prod" {
		return false
	}
	return strings.TrimSpace(r.Header.Get("X-Test-Error-Inject")) == code
}

func (h *ContentHandler) handleUpdatePost(w http.ResponseWriter, r *http.Request) {
	payload, err := BindGeneratedWritableBodyFromRequest(r, "UpdatePost")
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体字段不合法",
			err.Error(),
		))
		return
	}
	postID := strings.TrimPrefix(r.URL.Path, "/v1/content/posts/")
	post, err := h.postService.UpdatePost(r.Context(), strings.TrimSpace(postID), payload)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, post)
}

func (h *ContentHandler) handleCreateReport(w http.ResponseWriter, r *http.Request) {
	if h.reportService == nil {
		h.handleNotImplemented(w, r, "CreateReport")
		return
	}
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	reporterID := resolveUserID(r)
	if strings.TrimSpace(reporterID) == "" {
		reporterID = application.AnonymousFallbackSubAccountID
	}
	report, err := h.reportService.CreateReport(r.Context(), reporterID, body)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, report)
}

func (h *ContentHandler) handleListReports(w http.ResponseWriter, r *http.Request) {
	if h.reportService == nil {
		h.handleNotImplemented(w, r, "ListReports")
		return
	}
	limit := 20
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	items, err := h.reportService.ListReports(r.Context(), limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": items,
		"total": len(items),
	})
}

func (h *ContentHandler) handleGetReport(w http.ResponseWriter, r *http.Request) {
	if h.reportService == nil {
		h.handleNotImplemented(w, r, "GetReport")
		return
	}
	reportID := pathParamAfter(r.URL.Path, "/v1/content/reports/", "")
	report, err := h.reportService.GetReport(r.Context(), reportID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, report)
}

func (h *ContentHandler) handleResolveReport(w http.ResponseWriter, r *http.Request) {
	if h.reportService == nil {
		h.handleNotImplemented(w, r, "ResolveReport")
		return
	}
	reportID := pathParamAfter(r.URL.Path, "/v1/content/reports/", "")
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	report, err := h.reportService.ResolveReport(r.Context(), reportID, resolveUserID(r), body)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, report)
}

func (h *ContentHandler) handlePublishPost(w http.ResponseWriter, r *http.Request) {
	postID := postIDFromPath(r.URL.Path)
	payload, err := BindGeneratedWritableBodyFromRequest(r, "PublishPost")
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体字段不合法",
			err.Error(),
		))
		return
	}
	post, err := h.postService.PublishPost(r.Context(), postID, payload)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, post)
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
	post, err := h.postService.UpdatePostSettings(r.Context(), postID, resolveUserID(r), payload)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, post)
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
	post, err := h.postService.PromotePostToWork(r.Context(), postID, resolveUserID(r), payload)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, post)
}

func (h *ContentHandler) handleDeletePost(w http.ResponseWriter, r *http.Request) {
	postID := postIDFromPath(r.URL.Path)
	if err := h.postService.DeletePost(r.Context(), postID, resolveUserID(r)); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"postId": postID, "status": "deleted"})
}

func (h *ContentHandler) handleUpdatePostCircles(w http.ResponseWriter, r *http.Request) {
	postID := postIDFromPath(r.URL.Path)
	var body struct {
		Add    []string `json:"add"`
		Remove []string `json:"remove"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	resp, err := h.postService.UpdatePostCircles(r.Context(), postID, resolveUserID(r), body.Add, body.Remove)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleRepostToCircle(w http.ResponseWriter, r *http.Request) {
	postID := postIDFromPath(r.URL.Path)
	var body struct {
		CircleID string `json:"circleId"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	resp, err := h.postService.RepostToCircle(r.Context(), postID, resolveUserID(r), body.CircleID, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleQuoteToCircle(w http.ResponseWriter, r *http.Request) {
	postID := postIDFromPath(r.URL.Path)
	var body struct {
		CircleID string `json:"circleId"`
		Quote    string `json:"quoteText"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	resp, err := h.postService.RepostToCircle(r.Context(), postID, resolveUserID(r), body.CircleID, body.Quote)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	resp["sourceType"] = "quote"
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleInitMediaUpload(w http.ResponseWriter, r *http.Request) {
	var body struct {
		MediaType  string `json:"mediaType"`
		AssetScope string `json:"assetScope"`
		SourceKind string `json:"sourceKind"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	resp := h.postService.InitMediaUpload(r.Context(), resolveUserID(r), body.MediaType, body.AssetScope, body.SourceKind)
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleCompleteMediaUpload(w http.ResponseWriter, r *http.Request) {
	sessionID := pathParamAfter(r.URL.Path, "/v1/content/media/uploads/", ":complete")
	asset, err := h.postService.CompleteMediaUpload(r.Context(), sessionID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, videoCoverSelectionWire(asset))
}

func (h *ContentHandler) handleAbortMediaUpload(w http.ResponseWriter, r *http.Request) {
	sessionID := pathParamAfter(r.URL.Path, "/v1/content/media/uploads/", ":abort")
	if err := h.postService.AbortMediaUpload(r.Context(), sessionID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"sessionId": sessionID, "status": "aborted"})
}

func (h *ContentHandler) handleGetMediaAsset(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/v1/content/media/", "")
	if idx := strings.Index(mediaID, "/"); idx > 0 {
		mediaID = mediaID[:idx]
	}
	asset, ok := h.postService.GetMediaAsset(mediaID)
	if !ok {
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"媒体不存在",
			"media not found",
		))
		return
	}
	writeJSON(w, http.StatusOK, asset)
}

func (h *ContentHandler) handleBindMediaAssetsToPost(w http.ResponseWriter, r *http.Request) {
	var body struct {
		AssetIDs []string `json:"assetIds"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	resp, err := h.postService.BindMediaAssetsToPost(r.Context(), postIDFromPath(r.URL.Path), body.AssetIDs)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleRequestOriginalImageAccess(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/v1/content/media/", "/original:access")
	if strings.TrimSpace(mediaID) == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "mediaId 不能为空", "missing mediaId"))
		return
	}
	var body struct {
		Purpose string `json:"purpose"`
	}
	if r.Body != nil {
		defer r.Body.Close()
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
			return
		}
	}
	purpose := strings.TrimSpace(body.Purpose)
	if purpose == "" {
		purpose = "view"
	}
	resp, err := h.postService.RequestOriginalImageAccess(r.Context(), application.RequestOriginalImageAccessInput{
		MediaID:   mediaID,
		Purpose:   purpose,
		ViewerID:  resolveUserID(r),
		SessionID: resolveSessionID(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleSelectAutoVideoCover(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/v1/content/media/", "/cover:auto")
	asset, err := h.postService.SelectAutoVideoCover(r.Context(), mediaID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, videoCoverSelectionWire(asset))
}

func (h *ContentHandler) handleSelectManualVideoCover(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/v1/content/media/", "/cover:manual")
	var body struct {
		CoverAssetID     string `json:"coverAssetId"`
		CoverFrameTimeMs int64  `json:"coverFrameTimeMs"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	asset, err := h.postService.SelectManualVideoCover(r.Context(), mediaID, body.CoverAssetID, body.CoverFrameTimeMs)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, videoCoverSelectionWire(asset))
}

func videoCoverSelectionWire(asset *postmodel.MediaAsset) map[string]any {
	if asset == nil {
		return map[string]any{}
	}
	thumbnailURL := strings.TrimSpace(asset.ThumbnailUrl)
	coverURL := thumbnailURL
	if coverURL == "" {
		coverURL = strings.TrimSpace(asset.CdnUrl)
	}
	if coverURL == "" {
		coverURL = strings.TrimSpace(asset.OriginUrl)
	}
	if thumbnailURL == "" {
		thumbnailURL = coverURL
	}
	return map[string]any{
		"mediaId":            asset.ID,
		"coverStrategy":      asset.CoverStrategy,
		"manualCoverAssetId": asset.ManualCoverAssetId,
		"thumbnailUrl":       thumbnailURL,
		"coverUrl":           coverURL,
		"coverFrameTimeMs":   asset.CoverFrameTimeMs,
	}
}

func (h *ContentHandler) handleGenerateArticleSummary(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Title string `json:"title"`
		Body  string `json:"body"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	summary := h.postService.GenerateArticleSummary(body.Title, body.Body)
	writeJSON(w, http.StatusOK, map[string]any{"summary": summary})
}

func (h *ContentHandler) handleReportBehaviors(w http.ResponseWriter, r *http.Request) {
	raw, err := io.ReadAll(r.Body)
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体读取失败", err.Error()))
		return
	}
	var batch struct {
		UserID        string                           `json:"userId"`
		SessionID     string                           `json:"sessionId"`
		FeedSessionID string                           `json:"feedSessionId"`
		Events        []application.BehaviorEventInput `json:"events"`
	}
	if err := json.Unmarshal(raw, &batch); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	if len(batch.Events) == 0 {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "events 不能为空", "empty events"))
		return
	}
	// Fallback: body-level → header-level for userId/sessionId
	if strings.TrimSpace(batch.UserID) == "" {
		batch.UserID = resolveUserID(r)
	}
	if strings.TrimSpace(batch.SessionID) == "" {
		batch.SessionID = resolveSessionID(r)
	}
	for i := range batch.Events {
		if strings.TrimSpace(batch.Events[i].UserID) == "" {
			batch.Events[i].UserID = batch.UserID
		}
		if strings.TrimSpace(batch.Events[i].SessionID) == "" {
			batch.Events[i].SessionID = batch.SessionID
		}
		if strings.TrimSpace(batch.Events[i].FeedSessionID) == "" {
			batch.Events[i].FeedSessionID = strings.TrimSpace(batch.FeedSessionID)
		}
		if strings.EqualFold(strings.TrimSpace(batch.Events[i].Type), "like") {
			writeHTTPError(
				w,
				r,
				rterr.NewInvalidArgument(
					rterr.ModuleContent,
					"like 需走专属点赞路由",
					"like must use dedicated route",
				),
			)
			return
		}
	}
	if err := h.behaviorService.ProcessBatch(r.Context(), batch.Events); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// handleGetMyFootprint 我的足迹只读列表：仅本人可见，复用既有行为边，
// 不产生交集与影响事实。type 枚举与展示语义由云侧统一定义，端侧仅透传与展示。
func (h *ContentHandler) handleGetMyFootprint(w http.ResponseWriter, r *http.Request) {
	userID := resolveUserID(r)
	if strings.TrimSpace(userID) == "" {
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "unauthorized"),
			"需要登录后查看我的足迹",
			"footprint requires authenticated user",
		))
		return
	}
	query := r.URL.Query()
	limit := 20
	if rawLimit := strings.TrimSpace(query.Get("limit")); rawLimit != "" {
		if parsed, err := strconv.Atoi(rawLimit); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	entries, nextCursor, err := h.behaviorService.GetMyFootprint(
		r.Context(),
		userID,
		query.Get("type"),
		query.Get("cursor"),
		limit,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items := make([]map[string]any, 0, len(entries))
	for _, entry := range entries {
		item := map[string]any{
			"postId":     entry.PostID,
			"action":     entry.Action,
			"occurredAt": entry.OccurredAt.UTC().Format(time.RFC3339),
		}
		if entry.Post != nil {
			item["post"] = projectPostForClient(entry.Post)
		}
		items = append(items, item)
	}
	resp := map[string]any{"items": items}
	if nextCursor != "" {
		resp["nextCursor"] = nextCursor
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleLikePost(w http.ResponseWriter, r *http.Request, postID string) {
	likeCount, changed, err := h.postService.LikePost(r.Context(), postID, resolveUserID(r), resolveDeviceActorID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"postId":    postID,
		"liked":     true,
		"changed":   changed,
		"likeCount": likeCount,
	})
}

func (h *ContentHandler) handleUnlikePost(w http.ResponseWriter, r *http.Request, postID string) {
	likeCount, changed, err := h.postService.UnlikePost(r.Context(), postID, resolveUserID(r), resolveDeviceActorID(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"postId":    postID,
		"liked":     false,
		"changed":   changed,
		"likeCount": likeCount,
	})
}

func (h *ContentHandler) handleSharePost(w http.ResponseWriter, r *http.Request, postID string) {
	shareCount, changed, shared, err := h.postService.SharePost(
		r.Context(),
		postID,
		resolveUserID(r),
		resolveDeviceActorID(r),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"postId":     postID,
		"shared":     shared,
		"changed":    changed,
		"shareCount": shareCount,
	})
}

func (h *ContentHandler) handleUnsharePost(w http.ResponseWriter, r *http.Request, postID string) {
	shareCount, changed, shared, err := h.postService.UnsharePost(
		r.Context(),
		postID,
		resolveUserID(r),
		resolveDeviceActorID(r),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"postId":     postID,
		"shared":     shared,
		"changed":    changed,
		"shareCount": shareCount,
	})
}

func (h *ContentHandler) handleGetReactionState(w http.ResponseWriter, r *http.Request, postID string) {
	liked, shared := h.postService.GetReactionState(
		postID,
		resolveUserID(r),
		resolveDeviceActorID(r),
	)
	writeJSON(w, http.StatusOK, map[string]any{
		"postId":    postID,
		"liked":     liked,
		"shared":    shared,
		"reported":  false,
		"updatedAt": time.Now().UTC().Format(time.RFC3339),
	})
}

func (h *ContentHandler) handleCreateComment(w http.ResponseWriter, r *http.Request, postID string) {
	var body struct {
		Content               string           `json:"content"`
		ReplyToCommentID      string           `json:"replyToCommentId"`
		PersonaContextVersion string           `json:"personaContextVersion"`
		AttachmentMediaIDs    []string         `json:"attachmentMediaIds"`
		Mentions              []map[string]any `json:"mentions"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	subAccountID := strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Id"))
	if subAccountID == "" {
		subAccountID = resolveUserID(r)
	}
	if subAccountID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"缺少 X-Client-Sub-Account-Id",
			"missing X-Client-Sub-Account-Id",
		))
		return
	}
	// 受信代理头解析客户端 IP，注入 context 供评论属地解析（创建时落库快照）。
	clientIP := application.ParseTrustedClientIP(
		r.Header.Get("X-Forwarded-For"),
		r.Header.Get("X-Real-IP"),
		r.RemoteAddr,
	)
	ctx := application.WithClientIP(r.Context(), clientIP)
	comment, commentCount, err := h.postService.AddComment(
		ctx,
		postID,
		resolveUserID(r),
		body.Content,
		body.ReplyToCommentID,
		subAccountID,
		body.PersonaContextVersion,
		body.AttachmentMediaIDs,
		body.Mentions,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"comment":      comment,
		"commentCount": commentCount,
	})
}

func (h *ContentHandler) handleListComments(w http.ResponseWriter, r *http.Request, postID string) {
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	sort := strings.TrimSpace(r.URL.Query().Get("sort"))
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	comments, nextCursor, totalCount, err := h.postService.ListComments(r.Context(), postID, resolveUserID(r), cursor, sort, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	resp := map[string]any{"items": comments, "totalCount": totalCount}
	if nextCursor != "" {
		resp["nextCursor"] = nextCursor
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleListCommentReplies(w http.ResponseWriter, r *http.Request) {
	path := strings.Trim(r.URL.Path, "/")
	parts := strings.Split(path, "/")
	// /v1/content/posts/{postId}/comments/{commentId}/replies
	if len(parts) < 7 {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid path", "missing postId/commentId"))
		return
	}
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	limit := 10
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	comments, nextCursor, totalCount, err := h.postService.ListCommentReplies(
		r.Context(),
		parts[3],
		parts[5],
		resolveUserID(r),
		cursor,
		limit,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	resp := map[string]any{"items": comments, "totalCount": totalCount}
	if nextCursor != "" {
		resp["nextCursor"] = nextCursor
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleDeleteComment(w http.ResponseWriter, r *http.Request) {
	path := strings.Trim(r.URL.Path, "/")
	parts := strings.Split(path, "/")
	// /v1/content/posts/{postId}/comments/{commentId}
	if len(parts) < 6 {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid path", "missing commentId"))
		return
	}
	postID := parts[3]
	commentID := parts[5]
	if err := h.postService.DeleteComment(r.Context(), postID, commentID, resolveUserID(r)); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *ContentHandler) handleSetCommentPinned(w http.ResponseWriter, r *http.Request, pinned bool) {
	path := strings.Trim(r.URL.Path, "/")
	parts := strings.Split(path, "/")
	// /v1/content/posts/{postId}/comments/{commentId}/pin
	if len(parts) < 7 {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid path", "missing commentId for pin"))
		return
	}
	postID := parts[3]
	commentID := parts[5]
	comment, err := h.postService.SetCommentPinned(r.Context(), postID, commentID, resolveUserID(r), pinned)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"comment": comment})
}

func (h *ContentHandler) handleReactToComment(w http.ResponseWriter, r *http.Request, commentID string) {
	var body struct {
		Reaction       string `json:"reaction"`
		ViewerReaction string `json:"viewerReaction"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	reaction := strings.TrimSpace(body.Reaction)
	if reaction == "" {
		reaction = strings.TrimSpace(body.ViewerReaction)
	}
	comment, err := h.postService.ReactToComment(r.Context(), commentID, resolveUserID(r), reaction)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"comment": comment})
}

func (h *ContentHandler) handleBindMediaAssetsToComment(w http.ResponseWriter, r *http.Request, commentID string) {
	var body struct {
		AssetIDs []string `json:"assetIds"`
		MediaIDs []string `json:"mediaIds"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	assetIDs := body.AssetIDs
	if len(assetIDs) == 0 {
		assetIDs = body.MediaIDs
	}
	result, err := h.postService.BindMediaAssetsToComment(r.Context(), commentID, resolveUserID(r), assetIDs)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleListCommentsByAuthor(w http.ResponseWriter, r *http.Request) {
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	comments, nextCursor, err := h.postService.ListCommentsByAuthor(r.Context(), resolveUserID(r), cursor, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	resp := map[string]any{"items": comments}
	if nextCursor != "" {
		resp["nextCursor"] = nextCursor
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleListCommentsForPostAuthor(w http.ResponseWriter, r *http.Request) {
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	comments, nextCursor, err := h.postService.ListCommentsForPostAuthor(r.Context(), resolveUserID(r), cursor, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	resp := map[string]any{"items": comments}
	if nextCursor != "" {
		resp["nextCursor"] = nextCursor
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleListProfileInteractionActivitiesReceived(w http.ResponseWriter, r *http.Request) {
	h.handleListProfileInteractionActivities(w, r, "received")
}

func (h *ContentHandler) handleListProfileInteractionActivitiesSent(w http.ResponseWriter, r *http.Request) {
	h.handleListProfileInteractionActivities(w, r, "sent")
}

func (h *ContentHandler) handleListProfileInteractionActivities(w http.ResponseWriter, r *http.Request, direction string) {
	subAccountID := r.PathValue("subAccountId")
	if strings.TrimSpace(subAccountID) == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "subAccountId 不能为空", "missing subAccountId"))
		return
	}
	limit := 20
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	items, nextCursor, hasMore, err := h.postService.ListProfileInteractionActivities(
		r.Context(), subAccountID, resolveUserID(r), direction, cursor, limit,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":      items,
		"nextCursor": nextCursor,
		"hasMore":    hasMore,
	})
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

// handleGetCommentCountsDelta serves the explainable incremental comment-count
// contract. The `since` watermark is parsed as RFC3339(/Nano); an empty value
// seeds the baseline (unbounded-below). A malformed value is a client error.
func (h *ContentHandler) handleGetCommentCountsDelta(w http.ResponseWriter, r *http.Request, postID string) {
	var since time.Time
	if raw := strings.TrimSpace(r.URL.Query().Get("since")); raw != "" {
		parsed, err := parseSinceWatermark(raw)
		if err != nil {
			writeHTTPError(w, r, rterr.NewInvalidArgument(
				rterr.ModuleContent, "since 参数必须为 RFC3339 时间戳", "invalid since watermark: "+raw,
			))
			return
		}
		since = parsed
	}
	delta, err := h.postService.GetCommentCountsDelta(r.Context(), postID, since)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, delta)
}

// parseSinceWatermark accepts the RFC3339Nano watermark emitted by a prior
// response, falling back to plain RFC3339 for client-supplied baselines.
func parseSinceWatermark(raw string) (time.Time, error) {
	if t, err := time.Parse(time.RFC3339Nano, raw); err == nil {
		return t.UTC(), nil
	}
	t, err := time.Parse(time.RFC3339, raw)
	if err != nil {
		return time.Time{}, err
	}
	return t.UTC(), nil
}

func (h *ContentHandler) handleGetHelperRead(w http.ResponseWriter, r *http.Request) {
	contentID := pathParamAfter(r.URL.Path, "/v1/content/helper-read/", "")
	result, err := h.postService.GetHelperRead(r.Context(), contentID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleListUserPosts(w http.ResponseWriter, r *http.Request) {
	viewerID := resolveViewerUserID(r)
	userID := viewerID
	if raw := strings.TrimPrefix(r.URL.Path, "/v1/users/"); raw != r.URL.Path {
		if idx := strings.Index(raw, "/posts"); idx > 0 {
			userID = strings.TrimSpace(raw[:idx])
		}
	}
	if raw := strings.TrimPrefix(r.URL.Path, "/v1/content/sub-accounts/"); raw != r.URL.Path {
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
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	posts, nextCursor, err := h.postService.ListUserPosts(
		r.Context(),
		userID,
		viewerID,
		resolveViewerCircleIDs(r),
		identity,
		postType,
		cursor,
		limit,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items := make([]map[string]any, 0, len(posts))
	for i := range posts {
		items = append(items, projectPostForClient(&posts[i]))
	}
	resp := map[string]any{"items": items}
	if nextCursor != "" {
		resp["nextCursor"] = nextCursor
	}
	writeJSON(w, http.StatusOK, resp)
}

func postIDFromPath(path string) string {
	p := strings.TrimSpace(path)
	if p == "" {
		return ""
	}
	parts := strings.Split(strings.Trim(p, "/"), "/")
	// /v1/content/posts/{postId}/...
	if len(parts) < 4 {
		return ""
	}
	if parts[0] != "v1" || parts[1] != "content" || parts[2] != "posts" {
		return ""
	}
	return strings.TrimSpace(strings.SplitN(parts[3], ":", 2)[0])
}
