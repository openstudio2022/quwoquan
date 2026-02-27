package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"

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
		UserID:          resolveUserID(r),
		SessionID:       resolveSessionID(r),
		Type:            params.Type,
		SubCategory:     params.SubCategory,
		Cursor:          params.Cursor,
		Limit:           params.Limit,
		BlockedUserIDs:  resolveBlockedUserIDs(r),
		BlockedKeywords: resolveBlockedKeywords(r),
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
	post, ok, deleted := h.postService.GetPostOrTombstone(r.Context(), postID)
	if !ok {
		if deleted {
			writeHTTPError(w, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "conflict"),
				"内容已删除",
				"post deleted",
				false,
			))
			return
		}
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

func (h *ContentHandler) handlePublishPost(w http.ResponseWriter, r *http.Request) {
	postID := postIDFromPath(r.URL.Path)
	post, err := h.postService.PublishPost(r.Context(), postID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, post)
}

func (h *ContentHandler) handleDeletePost(w http.ResponseWriter, r *http.Request) {
	postID := postIDFromPath(r.URL.Path)
	if err := h.postService.DeletePost(r.Context(), postID, resolveUserID(r)); err != nil {
		writeHTTPError(w, err)
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
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	resp, err := h.postService.UpdatePostCircles(r.Context(), postID, resolveUserID(r), body.Add, body.Remove)
	if err != nil {
		writeHTTPError(w, err)
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
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	resp, err := h.postService.RepostToCircle(r.Context(), postID, resolveUserID(r), body.CircleID, "")
	if err != nil {
		writeHTTPError(w, err)
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
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	resp, err := h.postService.RepostToCircle(r.Context(), postID, resolveUserID(r), body.CircleID, body.Quote)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	resp["sourceType"] = "quote"
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleInitMediaUpload(w http.ResponseWriter, r *http.Request) {
	var body struct {
		MediaType string `json:"mediaType"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	resp := h.postService.InitMediaUpload(r.Context(), resolveUserID(r), body.MediaType)
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleCompleteMediaUpload(w http.ResponseWriter, r *http.Request) {
	sessionID := pathParamAfter(r.URL.Path, "/v1/content/media/uploads/", ":complete")
	asset, err := h.postService.CompleteMediaUpload(r.Context(), sessionID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, asset)
}

func (h *ContentHandler) handleAbortMediaUpload(w http.ResponseWriter, r *http.Request) {
	sessionID := pathParamAfter(r.URL.Path, "/v1/content/media/uploads/", ":abort")
	if err := h.postService.AbortMediaUpload(r.Context(), sessionID); err != nil {
		writeHTTPError(w, err)
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
		writeHTTPError(w, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "not_found"),
			"媒体不存在",
			"media not found",
			false,
		))
		return
	}
	writeJSON(w, http.StatusOK, asset)
}

func (h *ContentHandler) handleSelectAutoVideoCover(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/v1/content/media/", "/cover:auto")
	asset, err := h.postService.SelectAutoVideoCover(r.Context(), mediaID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, asset)
}

func (h *ContentHandler) handleSelectManualVideoCover(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/v1/content/media/", "/cover:manual")
	var body struct {
		CoverAssetID string `json:"coverAssetId"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	asset, err := h.postService.SelectManualVideoCover(r.Context(), mediaID, body.CoverAssetID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, asset)
}

func (h *ContentHandler) handleGenerateArticleSummary(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Title string `json:"title"`
		Body  string `json:"body"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	summary := h.postService.GenerateArticleSummary(body.Title, body.Body)
	writeJSON(w, http.StatusOK, map[string]any{"summary": summary})
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

func (h *ContentHandler) handleLikePost(w http.ResponseWriter, r *http.Request, postID string) {
	likeCount, changed, err := h.postService.LikePost(r.Context(), postID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
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
	likeCount, changed, err := h.postService.UnlikePost(r.Context(), postID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"postId":    postID,
		"liked":     false,
		"changed":   changed,
		"likeCount": likeCount,
	})
}

func (h *ContentHandler) handleFavoritePost(w http.ResponseWriter, r *http.Request, postID string) {
	favoriteCount, changed, err := h.postService.FavoritePost(r.Context(), postID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"postId":        postID,
		"favorited":     true,
		"changed":       changed,
		"favoriteCount": favoriteCount,
	})
}

func (h *ContentHandler) handleUnfavoritePost(w http.ResponseWriter, r *http.Request, postID string) {
	favoriteCount, changed, err := h.postService.UnfavoritePost(r.Context(), postID, resolveUserID(r))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"postId":        postID,
		"favorited":     false,
		"changed":       changed,
		"favoriteCount": favoriteCount,
	})
}

func (h *ContentHandler) handleGetReactionState(w http.ResponseWriter, r *http.Request, postID string) {
	liked, favorited := h.postService.GetReactionState(postID, resolveUserID(r))
	writeJSON(w, http.StatusOK, map[string]any{
		"postId":     postID,
		"liked":      liked,
		"favorited":  favorited,
		"shared":     false,
		"reported":   false,
		"updatedAt":  time.Now().UTC().Format(time.RFC3339),
	})
}

func (h *ContentHandler) handleCreateComment(w http.ResponseWriter, r *http.Request, postID string) {
	var body struct {
		Content          string `json:"content"`
		ReplyToCommentID string `json:"replyToCommentId"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeHTTPError(w, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	comment, commentCount, err := h.postService.AddComment(
		r.Context(),
		postID,
		resolveUserID(r),
		body.Content,
		body.ReplyToCommentID,
	)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"comment":      comment,
		"commentCount": commentCount,
	})
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
	return strings.TrimSpace(parts[3])
}

func (h *ContentHandler) handleNotImplemented(w http.ResponseWriter, r *http.Request, operation string) {
	switch operation {
	case "LikePost":
		h.handleLikePost(w, r, postIDFromPath(r.URL.Path))
		return
	case "UnlikePost":
		h.handleUnlikePost(w, r, postIDFromPath(r.URL.Path))
		return
	case "FavoritePost":
		h.handleFavoritePost(w, r, postIDFromPath(r.URL.Path))
		return
	case "UnfavoritePost":
		h.handleUnfavoritePost(w, r, postIDFromPath(r.URL.Path))
		return
	case "GetReactionState":
		h.handleGetReactionState(w, r, postIDFromPath(r.URL.Path))
		return
	case "CreateComment":
		h.handleCreateComment(w, r, postIDFromPath(r.URL.Path))
		return
	case "PublishPost":
		h.handlePublishPost(w, r)
		return
	case "DeletePost":
		h.handleDeletePost(w, r)
		return
	case "UpdatePostCircles":
		h.handleUpdatePostCircles(w, r)
		return
	case "RepostToCircle":
		h.handleRepostToCircle(w, r)
		return
	case "QuoteToCircle":
		h.handleQuoteToCircle(w, r)
		return
	case "InitMediaUpload":
		h.handleInitMediaUpload(w, r)
		return
	case "CompleteMediaUpload":
		h.handleCompleteMediaUpload(w, r)
		return
	case "AbortMediaUpload":
		h.handleAbortMediaUpload(w, r)
		return
	case "GetMediaAsset":
		h.handleGetMediaAsset(w, r)
		return
	case "SelectAutoVideoCover":
		h.handleSelectAutoVideoCover(w, r)
		return
	case "SelectManualVideoCover":
		h.handleSelectManualVideoCover(w, r)
		return
	case "GenerateArticleSummary":
		h.handleGenerateArticleSummary(w, r)
		return
	}
	writeHTTPError(w, rterr.NewAppError(
		rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "unavailable"),
		"接口暂未开放",
		"operation not implemented: "+operation+" "+r.Method+" "+r.URL.Path,
		true,
	))
}

func pathParamAfter(path, prefix, suffix string) string {
	v := strings.TrimSpace(strings.TrimPrefix(path, prefix))
	if suffix != "" {
		v = strings.TrimSuffix(v, suffix)
	}
	return strings.Trim(strings.TrimSpace(v), "/")
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

// resolveBlockedUserIDs extracts blocked author IDs from:
//   1) query: blockedUserIds=a,b
//   2) header: X-Blocked-User-Ids: a,b
func resolveBlockedUserIDs(r *http.Request) []string {
	if v := strings.TrimSpace(r.URL.Query().Get("blockedUserIds")); v != "" {
		return splitCSV(v)
	}
	return splitCSV(r.Header.Get("X-Blocked-User-Ids"))
}

// resolveBlockedKeywords extracts blocked keywords from:
//   1) query: blockedKeywords=k1,k2
//   2) header: X-Blocked-Keywords: k1,k2
func resolveBlockedKeywords(r *http.Request) []string {
	if v := strings.TrimSpace(r.URL.Query().Get("blockedKeywords")); v != "" {
		return splitCSV(v)
	}
	return splitCSV(r.Header.Get("X-Blocked-Keywords"))
}

func splitCSV(raw string) []string {
	if strings.TrimSpace(raw) == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		v := strings.TrimSpace(p)
		if v != "" {
			out = append(out, v)
		}
	}
	return out
}
