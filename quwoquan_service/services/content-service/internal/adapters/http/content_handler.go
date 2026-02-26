package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/content-service/internal/application"
)

type ContentHandler struct {
	feedService     *application.FeedService
	postService     *application.PostService
	behaviorService *application.BehaviorService
}

func NewContentHandler(
	feedService *application.FeedService,
	postService *application.PostService,
	behaviorService *application.BehaviorService,
) *ContentHandler {
	return &ContentHandler{
		feedService:     feedService,
		postService:     postService,
		behaviorService: behaviorService,
	}
}

func (h *ContentHandler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", h.handleHealthz)
	RegisterGeneratedRoutes(mux, h)
	return mux
}

func (h *ContentHandler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *ContentHandler) handleGetFeed(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET is supported"))
		return
	}
	params := BindGeneratedGetFeedParams(r, 20)
	resp, err := h.feedService.ListFeed(r.Context(), application.ListFeedRequest{
		UserID:      resolveUserID(r),
		SessionID:   resolveSessionID(r),
		Type:        params.Type,
		SubCategory: params.SubCategory,
		Cursor:      params.Cursor,
		Limit:       params.Limit,
	})
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleGetPost(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid method", "only GET is supported"))
		return
	}
	postID := strings.TrimPrefix(r.URL.Path, "/v1/content/posts/")
	if postID == "" || strings.Contains(postID, "/") {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid post id", "missing postId path segment"))
		return
	}
	post, ok := h.feedService.GetPost(r.Context(), postID)
	if !ok {
		writeHTTPError(w, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"内容不存在",
			"post not found",
			false,
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
	payload, err := BindGeneratedWritableBodyFromRequest(r, "CreatePost")
	if err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体字段不合法",
			err.Error(),
		))
		return
	}
	// Inject authorId from auth header if not in payload
	existingAuthor, _ := payload["authorId"].(string)
	if strings.TrimSpace(existingAuthor) == "" {
		if uid := resolveUserID(r); uid != "" {
			payload["authorId"] = uid
		}
	}
	post, err := h.postService.CreatePost(r.Context(), payload)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, post)
}

func (h *ContentHandler) handleUpdatePost(w http.ResponseWriter, r *http.Request) {
	payload, err := BindGeneratedWritableBodyFromRequest(r, "UpdatePost")
	if err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体字段不合法",
			err.Error(),
		))
		return
	}
	postID := strings.TrimPrefix(r.URL.Path, "/v1/content/posts/")
	post, err := h.postService.UpdatePost(r.Context(), strings.TrimSpace(postID), payload)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, post)
}

func (h *ContentHandler) handleReportBehaviors(w http.ResponseWriter, r *http.Request) {
	raw, err := io.ReadAll(r.Body)
	if err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体读取失败", err.Error()))
		return
	}
	var batch struct {
		UserID    string                           `json:"userId"`
		SessionID string                           `json:"sessionId"`
		Events    []application.BehaviorEventInput `json:"events"`
	}
	if err := json.Unmarshal(raw, &batch); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	if len(batch.Events) == 0 {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "events 不能为空", "empty events"))
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
	}
	if err := h.behaviorService.ProcessBatch(r.Context(), batch.Events); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"accepted": len(batch.Events),
		"status":   "ok",
	})
}

func (h *ContentHandler) handleGetRecommendation(w http.ResponseWriter, r *http.Request) {
	var req application.RecommendRequest
	if r.Body != nil {
		defer r.Body.Close()
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil && err != io.EOF {
			writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
			return
		}
	}
	// Fallback from headers if body didn't include userId/sessionId
	if strings.TrimSpace(req.UserID) == "" {
		req.UserID = resolveUserID(r)
	}
	if strings.TrimSpace(req.SessionID) == "" {
		req.SessionID = resolveSessionID(r)
	}
	resp, err := h.feedService.Recommend(r.Context(), req)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleNotImplemented(w http.ResponseWriter, r *http.Request, operation string) {
	writeHTTPError(w, rterr.NewAppError(
		rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "unavailable"),
		"接口暂未开放",
		"operation not implemented: "+operation+" "+r.Method+" "+r.URL.Path,
		true,
	))
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeHTTPError(w http.ResponseWriter, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptions{})
}

// resolveSessionID extracts sessionId from query param → body → X-Client-Session-Id header.
func resolveSessionID(r *http.Request) string {
	if v := strings.TrimSpace(r.URL.Query().Get("sessionId")); v != "" {
		return v
	}
	return strings.TrimSpace(r.Header.Get("X-Client-Session-Id"))
}

// resolveUserID extracts userId from query param → X-Client-User-Id header.
func resolveUserID(r *http.Request) string {
	if v := strings.TrimSpace(r.URL.Query().Get("userId")); v != "" {
		return v
	}
	return strings.TrimSpace(r.Header.Get("X-Client-User-Id"))
}
