package http

import (
	"context"
	"net/http"
	"strings"
	"time"

	generated "quwoquan_service/services/user-service/generated/account/user_account"
	relationshipgenerated "quwoquan_service/services/user-service/generated/relationship/persona_relationship"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

func (h *UserHandler) handleGetRelationship(w http.ResponseWriter, r *http.Request) {
	targetID := strings.TrimSpace(r.PathValue("personaId"))
	if targetID == "" {
		writeInvalidArg(w, r, "personaId required")
		return
	}
	userID, err := h.resolveActorPersonaID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	rel, err := h.relationship.GetRelationship(r.Context(), userID, targetID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, newRelationshipViewResponse(userID, targetID, rel))
}

func (h *UserHandler) handleGetRelationshipCapability(w http.ResponseWriter, r *http.Request) {
	targetID := strings.TrimSpace(r.PathValue("personaId"))
	if targetID == "" {
		writeInvalidArg(w, r, "personaId required")
		return
	}
	viewerID, err := h.resolveActorPersonaID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if targetID == "me" {
		targetID = viewerID
	}
	rel, err := h.relationship.GetRelationship(r.Context(), viewerID, targetID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	isBlocked, err := h.relationship.CheckBlocked(r.Context(), viewerID, targetID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	isBlockedBy, err := h.relationship.CheckBlocked(r.Context(), targetID, viewerID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, h.relationshipCapabilityView(r.Context(), viewerID, targetID, rel, isBlocked, isBlockedBy))
}

func (h *UserHandler) handleBlock(w http.ResponseWriter, r *http.Request) {
	blockedID := strings.TrimSpace(r.PathValue("targetPersonaId"))
	if blockedID == "" {
		writeInvalidArg(w, r, "targetPersonaId required")
		return
	}
	blockerID, err := h.resolveActorPersonaID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := h.relationship.Block(r.Context(), blockerID, blockedID, h.commandIdempotencyKey(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"targetPersonaId":  blockedID,
		"blocked":          true,
		"idempotentReplay": result.IdempotentReplay || !result.Changed,
		"updatedAt":        relationshipUpdatedAt(result),
	})
}

func (h *UserHandler) handleUnblock(w http.ResponseWriter, r *http.Request) {
	blockedID := strings.TrimSpace(r.PathValue("targetPersonaId"))
	if blockedID == "" {
		writeInvalidArg(w, r, "targetPersonaId required")
		return
	}
	blockerID, err := h.resolveActorPersonaID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := h.relationship.Unblock(r.Context(), blockerID, blockedID, h.commandIdempotencyKey(r))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"targetPersonaId":  blockedID,
		"blocked":          false,
		"idempotentReplay": result.IdempotentReplay || !result.Changed,
		"updatedAt":        relationshipUpdatedAt(result),
	})
}

func (h *UserHandler) handleListBlocked(w http.ResponseWriter, r *http.Request) {
	blockerID, err := h.resolveActorPersonaID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	edges, next, err := h.relationship.ListBlocked(r.Context(), blockerID, parseCursor(r), parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items := make([]blockedListItemResponse, 0, len(edges))
	for _, edge := range edges {
		items = append(items, newBlockedListItemResponse(edge))
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "nextCursor": next})
}

func (h *UserHandler) resolveActorPersonaID(
	ctx context.Context,
	r *http.Request,
	explicitActorID string,
) (string, error) {
	userID := strings.TrimSpace(userIDFromHeader(r))
	if userID == "" {
		return "", generated.AppErrorFromInvalidArgument("X-Client-User-Id header required")
	}
	trustedPersonaID := personaIDFromHeader(r)
	actorID := strings.TrimSpace(explicitActorID)
	if actorID != "" && actorID != trustedPersonaID {
		// metadata ownership_policy: actor_self —— body 里的 actorPersonaId
		// 是纯客户端输入，与 token principal 不一致时必须证明归属当前认证
		// 账号且未退役，防止用合法凭证伪造他人 persona 执行关系/招呼命令。
		return h.verifyActorPersonaOwnership(ctx, userID, actorID)
	}
	if actorID == "" {
		actorID = trustedPersonaID
	}
	if actorID != "" {
		return actorID, nil
	}
	activeContext, err := h.persona.GetActivePersonaContextView(ctx, userID)
	if err != nil {
		return "", err
	}
	actorID = strings.TrimSpace(anyString(activeContext["personaId"]))
	if actorID == "" {
		return "", generated.AppErrorFromInvalidArgument("active persona context is required")
	}
	return actorID, nil
}

func (h *UserHandler) verifyActorPersonaOwnership(
	ctx context.Context,
	accountID, actorID string,
) (string, error) {
	if h.persona == nil {
		return "", generated.AppErrorFromInternalError("persona service is unavailable")
	}
	persona, err := h.persona.GetPersonaProfile(ctx, actorID)
	if err != nil {
		return "", err
	}
	if persona == nil || persona.UserID != accountID {
		return "", relationshipgenerated.AppErrorFromRelationshipActorForbidden(
			"actor persona does not belong to the authenticated account",
		)
	}
	if strings.EqualFold(strings.TrimSpace(persona.Status), "retired") {
		return "", relationshipgenerated.AppErrorFromRelationshipActorForbidden(
			"retired persona cannot act",
		)
	}
	return persona.PersonaID, nil
}

func readOptionalBody(r *http.Request) map[string]any {
	if r == nil || r.Body == nil || r.ContentLength == 0 {
		return map[string]any{}
	}
	body, err := readBody(r)
	if err != nil || body == nil {
		return map[string]any{}
	}
	return body
}

func relationshipUpdatedAt(result relmodel.MutationResult) string {
	updatedAt := result.State.UpdatedAt
	if updatedAt.IsZero() {
		updatedAt = result.OccurredAt
	}
	if updatedAt.IsZero() {
		updatedAt = time.Now().UTC()
	}
	return updatedAt.UTC().Format(time.RFC3339)
}

func relationshipState(rel relmodel.RelationshipState, viewerID, targetID string) string {
	return rel.RelationState(viewerID, targetID)
}
