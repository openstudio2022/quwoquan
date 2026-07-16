package http

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

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
	activityType := strings.TrimSpace(r.URL.Query().Get("type"))
	if activityType != "" && activityType != "share" {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInteractionTypeInvalid(
			"supported interaction type filter is share",
		))
		return
	}
	if activityType == "share" {
		if err := requireActiveShareInteractionOwner(r, subAccountID); err != nil {
			writeHTTPError(w, r, err)
			return
		}
		items, nextCursor, hasMore, err := h.postService.ListProfileShareInteractions(
			r.Context(), subAccountID, direction, cursor, limit,
		)
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"items":      profileShareInteractionJSONItems(items),
			"nextCursor": nextCursor,
			"hasMore":    hasMore,
		})
		return
	}
	items, nextCursor, hasMore, err := h.postService.ListProfileInteractionActivities(
		r.Context(), subAccountID, operationActorID(r), direction, cursor, limit,
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

func (h *ContentHandler) handleUpdateProfileInteractionState(w http.ResponseWriter, r *http.Request) {
	subAccountID := strings.TrimSpace(r.PathValue("subAccountId"))
	interactionID := strings.TrimSpace(r.PathValue("interactionId"))
	if subAccountID == "" || interactionID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"互动标识不能为空",
			"missing subAccountId or interactionId",
		))
		return
	}
	if err := requireActiveShareInteractionOwner(r, subAccountID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if err := h.postService.MarkProfileShareInteractionState(
		r.Context(),
		subAccountID,
		interactionID,
		strings.TrimSpace(r.URL.Query().Get("state")),
	); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func requireActiveShareInteractionOwner(r *http.Request, subAccountID string) error {
	claims, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok || strings.TrimSpace(claims.Subject) == "" {
		return contentgenerated.AppErrorFromUnauthorized("share interactions require authenticated principal")
	}
	activeSubAccountID := strings.TrimSpace(claims.Persona)
	if activeSubAccountID == "" {
		return contentgenerated.AppErrorFromUnauthorized(
			"share interactions require an active persona principal",
		)
	}
	if activeSubAccountID != strings.TrimSpace(subAccountID) {
		return contentgenerated.AppErrorFromInteractionOwnerForbidden(
			"requested sub-account is not the active principal persona",
		)
	}
	return nil
}

func profileShareInteractionJSONItems(items []postmodel.ProfileInteractionActivityView) []map[string]any {
	result := make([]map[string]any, 0, len(items))
	for _, item := range items {
		raw, err := json.Marshal(item)
		if err != nil {
			continue
		}
		payload := map[string]any{}
		if err := json.Unmarshal(raw, &payload); err != nil {
			continue
		}
		if item.SeenAt.IsZero() {
			delete(payload, "seenAt")
		}
		if item.ReadAt.IsZero() {
			delete(payload, "readAt")
		}
		result = append(result, payload)
	}
	return result
}
