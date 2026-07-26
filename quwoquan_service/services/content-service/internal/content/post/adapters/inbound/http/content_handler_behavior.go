package http

import (
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	behaviorapp "quwoquan_service/services/content-service/internal/content/post/application/behavior"
)

func (h *ContentHandler) handleReportBehaviors(w http.ResponseWriter, r *http.Request) {
	raw, err := readBehaviorRequestBody(r)
	if err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体读取失败", err.Error()))
		return
	}
	var batch struct {
		UserID        string                           `json:"userId"`
		SessionID     string                           `json:"sessionId"`
		FeedSessionID string                           `json:"feedSessionId"`
		Events        []behaviorapp.BehaviorEventInput `json:"events"`
	}
	if err := json.Unmarshal(raw, &batch); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	if len(batch.Events) == 0 {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "events 不能为空", "empty events"))
		return
	}
	// A verified principal is authoritative. Body/header actor fields are only
	// retained for non-production direct contract fixtures that bypass the guard.
	if actorID, ok := VerifiedOperationActorID(r); ok {
		batch.UserID = actorID
		for i := range batch.Events {
			batch.Events[i].UserID = actorID
		}
	} else if strings.TrimSpace(batch.UserID) == "" {
		batch.UserID = ResolveUserID(r)
	}
	if strings.TrimSpace(batch.SessionID) == "" {
		batch.SessionID = resolveSessionID(r)
	}
	personaID := ResolvePersonaID(r)
	for i := range batch.Events {
		// persona 只来自已验证主体（或隔离 transport fixture 的 header 回退），
		// 不从客户端行为 body 读取。
		batch.Events[i].PersonaID = personaID
		if strings.TrimSpace(batch.Events[i].UserID) == "" {
			batch.Events[i].UserID = batch.UserID
		}
		if strings.TrimSpace(batch.Events[i].SessionID) == "" {
			batch.Events[i].SessionID = batch.SessionID
		}
		if strings.TrimSpace(batch.Events[i].FeedSessionID) == "" {
			batch.Events[i].FeedSessionID = strings.TrimSpace(batch.FeedSessionID)
		}
		// N0-3：like/comment/report 是服务端权威信号（对象命令 outbox 事实注入），
		// 通用行为端点拒收端侧补报，防止双计与伪造。
		switch strings.ToLower(strings.TrimSpace(batch.Events[i].Action)) {
		case "like", "comment", "report":
			writeHTTPError(
				w,
				r,
				rterr.NewInvalidArgument(
					rterr.ModuleContent,
					"该行为由服务端权威采集，需走专属命令路由",
					"like/comment/report are server-authoritative; use the dedicated command route",
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

const maxBehaviorRequestBytes = 128 * 1024

func readBehaviorRequestBody(r *http.Request) ([]byte, error) {
	var reader io.Reader = r.Body
	var compressed *gzip.Reader
	if strings.EqualFold(strings.TrimSpace(r.Header.Get("Content-Encoding")), "gzip") {
		var err error
		compressed, err = gzip.NewReader(r.Body)
		if err != nil {
			return nil, fmt.Errorf("invalid gzip body: %w", err)
		}
		defer compressed.Close()
		reader = compressed
	}
	raw, err := io.ReadAll(io.LimitReader(reader, maxBehaviorRequestBytes+1))
	if err != nil {
		return nil, fmt.Errorf("read behavior body: %w", err)
	}
	if len(raw) > maxBehaviorRequestBytes {
		return nil, fmt.Errorf("behavior body exceeds %d bytes", maxBehaviorRequestBytes)
	}
	return raw, nil
}

// handleGetMyFootprint 我的足迹只读列表：仅本人可见，复用既有行为边，
// 不产生交集与影响事实。type 枚举与展示语义由云侧统一定义，端侧仅透传与展示。
func (h *ContentHandler) handleGetMyFootprint(w http.ResponseWriter, r *http.Request) {
	userID := ResolveUserID(r)
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

func (h *ContentHandler) handleGetEntityWishlistState(
	w http.ResponseWriter,
	r *http.Request,
) {
	userID := ResolveUserID(r)
	if strings.TrimSpace(userID) == "" {
		writeHTTPError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "unauthorized"),
			"需要登录后查看想去状态",
			"entity wishlist state requires authenticated user",
		))
		return
	}
	query := r.URL.Query()
	state, err := h.behaviorService.GetEntityWishlistState(
		r.Context(),
		userID,
		query.Get("objectId"),
		query.Get("objectKind"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, state)
}
