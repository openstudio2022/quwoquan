package http

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	usertelemetry "quwoquan_service/services/user-service/internal/account/user_account/domain/user/telemetry"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	reltelemetry "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/telemetry"
)

func (h *UserHandler) handleFollow(w http.ResponseWriter, r *http.Request) {
	followeeIdentity := strings.TrimSpace(r.PathValue("targetPersonaId"))
	if followeeIdentity == "" {
		writeInvalidArg(w, r, "targetPersonaId required")
		return
	}
	actor, err := h.resolveActorPersonaID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	wire, err := decodeRelationshipMutation(r)
	if err != nil {
		writeInvalidArg(w, r, err.Error())
		return
	}
	result, err := h.relationship.Follow(r.Context(), actor, followeeIdentity, wire.Source, relationshipapp.CommandEvidence{IdempotencyKey: h.commandIdempotencyKey(r), MutationBasis: wire.MutationBasis, ExpectedVersion: *wire.ExpectedVersion})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	target := result.CanonicalTargetPersonaID
	writeJSON(w, http.StatusOK, map[string]any{"actorPersonaId": actor, "targetPersonaId": target, "relationState": relationshipState(result.State, actor, target), "idempotentReplay": result.IdempotentReplay, "updatedAt": relationshipUpdatedAt(result)})
}

func (h *UserHandler) handleUnfollow(w http.ResponseWriter, r *http.Request) {
	targetIdentity := strings.TrimSpace(r.PathValue("targetPersonaId"))
	if targetIdentity == "" {
		writeInvalidArg(w, r, "targetPersonaId required")
		return
	}
	actor, err := h.resolveActorPersonaID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	wire, err := decodeRelationshipMutation(r)
	if err != nil {
		writeInvalidArg(w, r, err.Error())
		return
	}
	result, err := h.relationship.Unfollow(r.Context(), actor, targetIdentity, relationshipapp.CommandEvidence{IdempotencyKey: h.commandIdempotencyKey(r), MutationBasis: wire.MutationBasis, ExpectedVersion: *wire.ExpectedVersion})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	target := result.CanonicalTargetPersonaID
	writeJSON(w, http.StatusOK, map[string]any{"actorPersonaId": actor, "targetPersonaId": target, "relationState": relationshipState(result.State, actor, target), "idempotentReplay": result.IdempotentReplay, "updatedAt": relationshipUpdatedAt(result)})
}

func (h *UserHandler) handleListFollowing(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	defer func() { reltelemetry.Collector().RecordListLatency(time.Since(startedAt)) }()
	personaID := strings.TrimSpace(r.PathValue("personaId"))
	viewerID, _ := h.resolveActorPersonaID(r.Context(), r, "")
	items, next, err := h.collectFollowListItems(
		r.Context(), viewerID, personaID, parseCursor(r), parseLimit(r, 20), true, parseListSearchQuery(r),
	)
	if err != nil {
		writeHTTPError(w, r, relationshipListReadError(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "nextCursor": next})
}

func (h *UserHandler) handleListFollowers(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	defer func() { reltelemetry.Collector().RecordListLatency(time.Since(startedAt)) }()
	personaID := strings.TrimSpace(r.PathValue("personaId"))
	viewerID, _ := h.resolveActorPersonaID(r.Context(), r, "")
	items, next, err := h.collectFollowListItems(
		r.Context(), viewerID, personaID, parseCursor(r), parseLimit(r, 20), false, parseListSearchQuery(r),
	)
	if err != nil {
		writeHTTPError(w, r, relationshipListReadError(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "nextCursor": next})
}

// parseListSearchQuery 读取粉丝/关注列表的服务端搜索词（SIT2：搜索走云侧
// query + cursor + limit，端侧不做本地 contains 伪搜索）。
func parseListSearchQuery(r *http.Request) string {
	return strings.ToLower(strings.TrimSpace(r.URL.Query().Get("query")))
}

func (h *UserHandler) collectFollowListItems(
	ctx context.Context,
	viewerID, personaID, cursor string,
	limit int,
	listFollowing bool,
	searchQuery string,
) ([]map[string]any, string, error) {
	if limit <= 0 {
		limit = 20
	}
	if deadline, ok := ctx.Deadline(); !ok || time.Until(deadline) > 2*time.Second {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, 2*time.Second)
		defer cancel()
	}
	facts, err := (followListReadFacade{
		relationship: h.relationship,
		personas:     h.persona,
		greetings:    h.greeting,
	}).Read(ctx, viewerID, personaID, cursor, limit, listFollowing, searchQuery)
	if err != nil {
		reltelemetry.Collector().RecordPageDrift()
		return nil, "", err
	}
	items := make([]map[string]any, 0, len(facts.Edges))
	for _, edge := range facts.Edges {
		targetID := edge.SourcePersonaID
		if listFollowing {
			targetID = edge.TargetPersonaID
		}
		profile, found := facts.Profiles[targetID]
		if !found {
			reltelemetry.Collector().RecordPageDrift()
			usertelemetry.RolloutCollector().RecordAttributionMismatch()
			continue
		}
		relationship := facts.Relationships[targetID]
		if viewerID != "" && (relationship.IsBlocked || relationship.IsBlockedBy) {
			continue
		}
		item := map[string]any{
			"personaId": profile.PersonaID, "userHandle": profile.UserHandle,
			"displayName": profile.DisplayName, "avatarUrl": profile.AvatarURL,
			"profileVisibility": profile.ProfileVisibility,
			"followedAt":        optionalTimestampRFC3339(edge.FollowedAt),
		}
		if viewerID != "" {
			item["relationState"] = relationshipState(relationship, viewerID, targetID)
			item["relationshipCapability"] = h.relationshipCapabilityViewFromFacts(
				viewerID, targetID, relationship, false, false,
				facts.PendingGreetings[targetID], facts.FormalConversations[targetID],
			)
		} else {
			item["relationState"] = "not_following"
		}
		items = append(items, item)
	}
	if len(items) < len(facts.Edges) {
		reltelemetry.Collector().RecordFilterMismatch()
		usertelemetry.RolloutCollector().RecordAttributionMismatch()
	}
	return items, facts.NextCursor, nil
}

func optionalTimestampRFC3339(value *time.Time) string {
	if value == nil {
		return ""
	}
	return value.UTC().Format(time.RFC3339)
}

func relationshipListReadError(err error) error {
	switch {
	case errors.Is(err, relationshipapp.ErrInvalidReadCursor):
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleUser, rterr.KindUser, "relationship_read_cursor_invalid"),
			"分页位置已失效，请刷新列表",
			err.Error(),
		).WithMetadata("relationship_read_cursor_invalid", http.StatusBadRequest).WithRecoveryDirective("retry", "passiveIndicator", 0)
	case errors.Is(err, context.DeadlineExceeded):
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleUser, rterr.KindSystem, "relationship_read_budget_exceeded"),
			"列表读取超时，请稍后重试",
			err.Error(),
		).WithMetadata("relationship_read_budget_exceeded", http.StatusServiceUnavailable).WithRecoveryDirective("retry", "passiveIndicator", 1)
	default:
		return err
	}
}
