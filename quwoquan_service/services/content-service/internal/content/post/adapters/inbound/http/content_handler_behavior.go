package http

import (
	"net/http"
	"strconv"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
)

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
