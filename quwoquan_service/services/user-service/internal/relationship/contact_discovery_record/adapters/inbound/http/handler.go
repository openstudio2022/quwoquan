package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	usergenerated "quwoquan_service/services/user-service/generated/account/user_account"
	contactapp "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/application"
	"quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/model"
	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

type Handler struct {
	service      *contactapp.ContactDiscoveryService
	relationship *relationshipapp.PersonaRelationshipService
	greeting     *greetingapp.GreetingService
}

func NewHandler(
	service *contactapp.ContactDiscoveryService,
	relationship *relationshipapp.PersonaRelationshipService,
	greeting *greetingapp.GreetingService,
) (*Handler, error) {
	if service == nil || relationship == nil || greeting == nil {
		return nil, errors.New("contact discovery handler requires service, relationship and greeting readers")
	}
	return &Handler{service: service, relationship: relationship, greeting: greeting}, nil
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /owner/contact-discovery", handler.handleInitiateContactDiscovery)
	mux.HandleFunc("GET /owner/contact-discovery/latest", handler.handleGetLatestContactDiscovery)
	mux.HandleFunc("DELETE /owner/contact-discovery/{id}", handler.handleDismissContactDiscovery)
}

func (handler *Handler) handleInitiateContactDiscovery(w http.ResponseWriter, r *http.Request) {
	userID := actorAccountID(r)
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
	record, err := handler.service.Initiate(
		r.Context(), userID, phones, idempotencyKey(r),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusAccepted, handler.buildContactDiscoveryResponse(r, userID, record))
}

func (handler *Handler) handleGetLatestContactDiscovery(w http.ResponseWriter, r *http.Request) {
	userID := actorAccountID(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	record, err := handler.service.GetLatest(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if record == nil {
		writeNotFound(w, r, "resource not found")
		return
	}
	writeJSON(w, http.StatusOK, handler.buildContactDiscoveryResponse(r, userID, record))
}

// buildContactDiscoveryResponse assembles the sanitized wire body: the privacy
// baseline (matchedPersonaIds) plus the enriched matches[] projection
// (ContactDiscoveryMatchWire) carrying the initiator's own hashedPhone, a
// trimmed profile, and the viewer-scoped relationship capability that drives
// the "添加 / 已添加" button. ownerAccountId and the raw uploaded hashes never
// leave the server (json:"-" on the record + this explicit allow-list).
func (handler *Handler) buildContactDiscoveryResponse(r *http.Request, viewerID string, record *model.ContactDiscoveryRecord) map[string]any {
	resp := map[string]any{
		"id":                record.ID,
		"status":            record.Status,
		"matchedPersonaIds": nonNilStrings(record.MatchedPersonaIds),
		"matchCount":        record.MatchCount,
		"expireAt":          record.ExpireAt,
		"completedAt":       record.CompletedAt,
		"matches":           []map[string]any{},
	}
	if record.Status == "dismissed" || record.Status == "expired" {
		return resp
	}

	matches, err := handler.service.MatchesFor(r.Context(), record.HashedPhones)
	if err != nil || len(matches) == 0 {
		return resp
	}

	relationViewerID := viewerID
	if activeViewerID, resolveErr := actorPersonaID(r); resolveErr == nil && activeViewerID != "" {
		relationViewerID = activeViewerID
	}

	wire := make([]map[string]any, 0, len(matches))
	for _, m := range matches {
		rel, _ := handler.relationship.GetRelationship(r.Context(), relationViewerID, m.PersonaID)
		isBlocked, _ := handler.relationship.CheckBlocked(r.Context(), relationViewerID, m.PersonaID)
		isBlockedBy, _ := handler.relationship.CheckBlocked(r.Context(), m.PersonaID, relationViewerID)
		capability := handler.relationshipCapabilityView(r.Context(), relationViewerID, m.PersonaID, rel, isBlocked, isBlockedBy)
		item := map[string]any{
			"hashedPhone":            m.HashedPhone,
			"personaId":              m.PersonaID,
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

func (handler *Handler) handleDismissContactDiscovery(w http.ResponseWriter, r *http.Request) {
	userID := actorAccountID(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	id := r.PathValue("id")
	if err := handler.service.Dismiss(
		r.Context(), userID, id, idempotencyKey(r),
	); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (handler *Handler) relationshipCapabilityView(
	ctx context.Context,
	viewerID, targetID string,
	rel relmodel.RelationshipState,
	isBlocked, isBlockedBy bool,
) relationshipapp.RelationshipCapabilityView {
	hasPendingGreeting, _ := handler.greeting.HasPendingBetween(ctx, viewerID, targetID)
	hasFormalConversation, _ := handler.greeting.HasFormalConversation(ctx, viewerID, targetID)
	return relationshipapp.NewRelationshipCapabilityView(
		relmodel.RelationshipCapabilityFacts{
			ViewerPersonaID:       viewerID,
			TargetPersonaID:       targetID,
			Relationship:          rel,
			IsBlocked:             isBlocked,
			IsBlockedBy:           isBlockedBy,
			HasPendingGreeting:    hasPendingGreeting,
			HasFormalConversation: hasFormalConversation,
		},
	)
}

func actorAccountID(r *http.Request) string {
	current, ok := operation.FromContext(r.Context())
	if !ok {
		return ""
	}
	return strings.TrimSpace(current.Actor.AccountID)
}

func idempotencyKey(r *http.Request) string {
	current, ok := operation.FromContext(r.Context())
	if !ok {
		return ""
	}
	return strings.TrimSpace(current.IdempotencyKey)
}

func actorPersonaID(r *http.Request) (string, error) {
	current, ok := operation.FromContext(r.Context())
	if !ok || strings.TrimSpace(current.Actor.PersonaID) == "" {
		return "", usergenerated.AppErrorFromInvalidArgument("active persona context is required")
	}
	return strings.TrimSpace(current.Actor.PersonaID), nil
}

func readBody(r *http.Request) (map[string]any, error) {
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		return nil, err
	}
	return body, nil
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func writeInvalidArg(w http.ResponseWriter, r *http.Request, message string) {
	writeHTTPError(w, r, usergenerated.AppErrorFromInvalidArgument(message))
}

func writeNotFound(w http.ResponseWriter, r *http.Request, message string) {
	writeHTTPError(w, r, usergenerated.AppErrorFromUserNotFound(message))
}
