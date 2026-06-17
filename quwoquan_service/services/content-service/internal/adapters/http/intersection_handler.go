package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

// handleGetMyIntersectionSummary 我的主页「我的交集」聚合摘要。
func (h *ContentHandler) handleGetMyIntersectionSummary(w http.ResponseWriter, r *http.Request) {
	if h.intersectionService == nil {
		h.handleNotImplemented(w, r, "GetMyIntersectionSummary")
		return
	}
	userID := resolveUserID(r)
	if strings.TrimSpace(userID) == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "需要登录", "missing user"))
		return
	}
	summary, err := h.intersectionService.Summary(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, summary)
}

// handleListMyIntersections 按维度分页的交集列表（自上次查看新增在前）。
func (h *ContentHandler) handleListMyIntersections(w http.ResponseWriter, r *http.Request) {
	if h.intersectionService == nil {
		h.handleNotImplemented(w, r, "ListMyIntersections")
		return
	}
	userID := resolveUserID(r)
	if strings.TrimSpace(userID) == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "需要登录", "missing user"))
		return
	}
	q := r.URL.Query()
	dimension := strings.TrimSpace(q.Get("dimension"))
	limit := 50
	if raw := strings.TrimSpace(q.Get("limit")); raw != "" {
		if parsed, perr := strconv.Atoi(raw); perr == nil && parsed > 0 {
			limit = parsed
		}
	}
	items, err := h.intersectionService.List(r.Context(), userID, dimension, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":     items,
		"dimension": dimension,
	})
}

// handleMarkIntersectionsVisited 推进已读水位并清零未读红点。
func (h *ContentHandler) handleMarkIntersectionsVisited(w http.ResponseWriter, r *http.Request) {
	if h.intersectionService == nil {
		h.handleNotImplemented(w, r, "MarkIntersectionsVisited")
		return
	}
	userID := resolveUserID(r)
	if strings.TrimSpace(userID) == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "需要登录", "missing user"))
		return
	}
	var body struct {
		Dimension string `json:"dimension"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	if err := h.intersectionService.MarkVisited(r.Context(), userID, body.Dimension); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"dimension": body.Dimension,
		"status":    "visited",
	})
}

// handleGetFeedIntersections 首页/频道交集推荐（事实+概率混排，过保鲜期/冷却窗口）。
func (h *ContentHandler) handleGetFeedIntersections(w http.ResponseWriter, r *http.Request) {
	if h.intersectionService == nil {
		h.handleNotImplemented(w, r, "GetFeedIntersections")
		return
	}
	userID := resolveUserID(r)
	q := r.URL.Query()
	channel := strings.TrimSpace(q.Get("channel"))
	limit := 4
	if raw := strings.TrimSpace(q.Get("limit")); raw != "" {
		if parsed, perr := strconv.Atoi(raw); perr == nil && parsed > 0 {
			limit = parsed
		}
	}
	items, err := h.intersectionService.Feed(r.Context(), userID, channel, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":   items,
		"channel": channel,
	})
}

// handleGetObjectIntersections 对象页「我与该对象」关系类交集（§2 证据组闭集）。
func (h *ContentHandler) handleGetObjectIntersections(w http.ResponseWriter, r *http.Request) {
	if h.intersectionService == nil {
		h.handleNotImplemented(w, r, "GetObjectIntersections")
		return
	}
	userID := resolveUserID(r)
	if strings.TrimSpace(userID) == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "需要登录", "missing user"))
		return
	}
	q := r.URL.Query()
	objectID := strings.TrimSpace(q.Get("objectId"))
	objectType := strings.TrimSpace(q.Get("objectType"))
	if objectID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "缺少对象", "missing objectId"))
		return
	}
	limit := 8
	if raw := strings.TrimSpace(q.Get("limit")); raw != "" {
		if parsed, perr := strconv.Atoi(raw); perr == nil && parsed > 0 {
			limit = parsed
		}
	}
	items, err := h.intersectionService.ObjectIntersections(r.Context(), userID, objectID, objectType, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":      items,
		"objectId":   objectID,
		"objectType": objectType,
	})
}

// handleReportIntersectionExposure 曝光上报（写跨会话冷却集）。
func (h *ContentHandler) handleReportIntersectionExposure(w http.ResponseWriter, r *http.Request) {
	if h.intersectionService == nil {
		h.handleNotImplemented(w, r, "ReportIntersectionExposure")
		return
	}
	userID := resolveUserID(r)
	if strings.TrimSpace(userID) == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "需要登录", "missing user"))
		return
	}
	var body struct {
		ObjectIDs []string `json:"objectIds"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	if err := h.intersectionService.ReportExposure(r.Context(), userID, body.ObjectIDs); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"cooledCount": len(body.ObjectIDs),
		"status":      "recorded",
	})
}
