package http

import (
	"encoding/json"
	"io"
	"net/http"
	"slices"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
)

// handleGetMyIntersectionSummary 我的主页「我的交集」聚合摘要。
func (h *ContentHandler) handleGetMyIntersectionSummary(w http.ResponseWriter, r *http.Request) {
	if h.intersectionService == nil {
		h.handleNotImplemented(w, r, "GetMyIntersectionSummary")
		return
	}
	personaID := ResolvePersonaID(r)
	if strings.TrimSpace(personaID) == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "需要登录", "missing user"))
		return
	}
	summary, err := h.intersectionService.Summary(r.Context(), personaID)
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
	personaID := ResolvePersonaID(r)
	if strings.TrimSpace(personaID) == "" {
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
	items, nextCursor, hasMore, err := h.intersectionService.List(r.Context(), personaID, intersectionapp.IntersectionListQuery{
		Dimension:  dimension,
		Filter:     strings.TrimSpace(q.Get("filter")),
		SourceRef:  strings.TrimSpace(q.Get("sourceRef")),
		TimeBucket: strings.TrimSpace(q.Get("timeBucket")),
		Cursor:     strings.TrimSpace(q.Get("cursor")),
		Limit:      limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":      items,
		"dimension":  dimension,
		"nextCursor": nextCursor,
		"hasMore":    hasMore,
	})
}

// markIntersectionsVisitedAck 是 MarkIntersectionsVisited 的强类型回执
// （services/content-service/contracts/content/intersection_visit_state/fields.yaml#MarkIntersectionsVisitedAck）。
type markIntersectionsVisitedAck struct {
	Dimensions []string `json:"dimensions"`
	Status     string   `json:"status"`
}

// intersectionDimensions 是交集维度的封闭集合（_shared/types.yaml#IntersectionDimension）。
var intersectionDimensions = []string{"identity", "location", "content", "interest", "relationship"}

// handleMarkIntersectionsVisited 推进已读水位并清零未读红点；dimension 为空推进全部维度。
func (h *ContentHandler) handleMarkIntersectionsVisited(w http.ResponseWriter, r *http.Request) {
	if h.intersectionService == nil {
		h.handleNotImplemented(w, r, "MarkIntersectionsVisited")
		return
	}
	personaID := ResolvePersonaID(r)
	if strings.TrimSpace(personaID) == "" {
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
	dimension := strings.TrimSpace(body.Dimension)
	if dimension != "" && !slices.Contains(intersectionDimensions, dimension) {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"交集维度无效",
			"dimension must be one of identity/location/content/interest/relationship",
		))
		return
	}
	if err := h.intersectionService.MarkVisited(r.Context(), personaID, dimension); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	visited := intersectionDimensions
	if dimension != "" {
		visited = []string{dimension}
	}
	writeJSON(w, http.StatusOK, markIntersectionsVisitedAck{
		Dimensions: visited,
		Status:     "visited",
	})
}

// handleGetObjectIntersections 对象页「我与该对象」关系类交集（§2 证据组闭集）。
func (h *ContentHandler) handleGetObjectIntersections(w http.ResponseWriter, r *http.Request) {
	if h.intersectionService == nil {
		h.handleNotImplemented(w, r, "GetObjectIntersections")
		return
	}
	personaID := ResolvePersonaID(r)
	if strings.TrimSpace(personaID) == "" {
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
	items, err := h.intersectionService.ObjectIntersections(r.Context(), personaID, objectID, objectType, limit)
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
