package http

import (
	"net/http"
	"strings"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

// --- Contact Discovery ---

func (h *UserHandler) handleInitiateContactDiscovery(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	rawPhones, _ := body["hashedPhones"].([]any)
	phones := make([]string, 0, len(rawPhones))
	for _, p := range rawPhones {
		if s, ok := p.(string); ok {
			phones = append(phones, s)
		}
	}
	record, err := h.contactDiscovery.Initiate(r.Context(), userID, phones)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusAccepted, h.buildContactDiscoveryResponse(r, userID, record))
}

func (h *UserHandler) handleGetLatestContactDiscovery(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	record, err := h.contactDiscovery.GetLatest(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if record == nil {
		writeNotFound(w, r, "resource not found")
		return
	}
	writeJSON(w, http.StatusOK, h.buildContactDiscoveryResponse(r, userID, record))
}

// buildContactDiscoveryResponse assembles the sanitized wire body: the privacy
// baseline (matchedSubAccountIds) plus the enriched matches[] projection
// (ContactDiscoveryMatchWire) carrying the initiator's own hashedPhone, a
// trimmed profile, and the viewer-scoped relationship capability that drives
// the "添加 / 已添加" button. ownerAccountId and the raw uploaded hashes never
// leave the server (json:"-" on the record + this explicit allow-list).
func (h *UserHandler) buildContactDiscoveryResponse(r *http.Request, viewerID string, record *model.ContactDiscoveryRecord) map[string]any {
	resp := map[string]any{
		"id":                   record.ID,
		"status":               record.Status,
		"matchedSubAccountIds": nonNilStrings(record.MatchedSubAccountIds),
		"matchCount":           record.MatchCount,
		"expireAt":             record.ExpireAt,
		"completedAt":          record.CompletedAt,
		"matches":              []map[string]any{},
	}
	if record.Status == "dismissed" || record.Status == "expired" {
		return resp
	}

	matches, err := h.contactDiscovery.MatchesFor(r.Context(), record.HashedPhones)
	if err != nil || len(matches) == 0 {
		return resp
	}

	relationViewerID := viewerID
	if activeViewerID, resolveErr := h.resolveActorSubAccountID(r.Context(), r, ""); resolveErr == nil && activeViewerID != "" {
		relationViewerID = activeViewerID
	}

	wire := make([]map[string]any, 0, len(matches))
	for _, m := range matches {
		rel, _ := h.follow.GetRelationship(r.Context(), relationViewerID, m.SubAccountID)
		isBlocked, _ := h.block.CheckBlocked(r.Context(), relationViewerID, m.SubAccountID)
		isBlockedBy, _ := h.block.CheckBlocked(r.Context(), m.SubAccountID, relationViewerID)
		capability := h.buildRelationshipCapabilityView(r.Context(), relationViewerID, m.SubAccountID, rel, isBlocked, isBlockedBy)
		if m.SubAccountID != "" {
			capability["targetSubAccountId"] = m.SubAccountID
		}
		item := map[string]any{
			"hashedPhone":            m.HashedPhone,
			"subAccountId":           m.SubAccountID,
			"userHandle":             m.UserHandle,
			"displayName":            m.DisplayName,
			"avatarVersion":          m.AvatarVersion,
			"relationshipCapability": capability,
		}
		if strings.TrimSpace(m.AvatarURL) != "" {
			item["avatarUrl"] = m.AvatarURL
		}
		if strings.TrimSpace(m.Region) != "" {
			item["region"] = m.Region
		}
		wire = append(wire, item)
	}
	resp["matches"] = wire
	return resp
}

func nonNilStrings(in []string) []string {
	if in == nil {
		return []string{}
	}
	return in
}

func (h *UserHandler) handleDismissContactDiscovery(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	id := r.PathValue("id")
	if err := h.contactDiscovery.Dismiss(r.Context(), userID, id); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}
