package http

import (
	"context"
	"net/http"
	"strings"
	"time"

	usertelemetry "quwoquan_service/services/user-service/internal/account/user_account/domain/user/telemetry"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	reltelemetry "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/telemetry"
)

func (h *UserHandler) handleFollow(w http.ResponseWriter, r *http.Request) {
	body := readOptionalBody(r)
	followeeID := strings.TrimSpace(r.PathValue("targetSubAccountId"))
	if followeeID == "" {
		writeInvalidArg(w, r, "targetSubAccountId required")
		return
	}
	followerID, err := h.resolveActorSubAccountID(r.Context(), r, anyString(body["actorSubAccountId"]))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := h.relationship.Follow(
		r.Context(), followerID, followeeID, anyString(body["source"]), anyString(body["clientRequestId"]),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	rel, err := h.relationship.GetRelationship(r.Context(), followerID, followeeID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"actorSubAccountId":  followerID,
		"targetSubAccountId": followeeID,
		"relationState":      relationshipState(rel, followerID, followeeID),
		"idempotentReplay":   result.IdempotentReplay || !result.Changed,
		"updatedAt":          relationshipUpdatedAt(result),
	})
}

func (h *UserHandler) handleUnfollow(w http.ResponseWriter, r *http.Request) {
	body := readOptionalBody(r)
	followeeID := strings.TrimSpace(r.PathValue("targetSubAccountId"))
	if followeeID == "" {
		writeInvalidArg(w, r, "targetSubAccountId required")
		return
	}
	followerID, err := h.resolveActorSubAccountID(r.Context(), r, anyString(body["actorSubAccountId"]))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := h.relationship.Unfollow(r.Context(), followerID, followeeID, anyString(body["clientRequestId"]))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	rel, err := h.relationship.GetRelationship(r.Context(), followerID, followeeID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"actorSubAccountId":  followerID,
		"targetSubAccountId": followeeID,
		"relationState":      relationshipState(rel, followerID, followeeID),
		"idempotentReplay":   result.IdempotentReplay || !result.Changed,
		"updatedAt":          relationshipUpdatedAt(result),
	})
}

func (h *UserHandler) handleListFollowing(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	defer func() { reltelemetry.Collector().RecordListLatency(time.Since(startedAt)) }()
	subAccountID := strings.TrimSpace(r.PathValue("subAccountId"))
	viewerID, _ := h.resolveActorSubAccountID(r.Context(), r, "")
	items, next, err := h.collectFollowListItems(
		r.Context(), viewerID, subAccountID, parseCursor(r), parseLimit(r, 20), true, parseListSearchQuery(r),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": next, "nextCursor": next})
}

func (h *UserHandler) handleListFollowers(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	defer func() { reltelemetry.Collector().RecordListLatency(time.Since(startedAt)) }()
	subAccountID := strings.TrimSpace(r.PathValue("subAccountId"))
	viewerID, _ := h.resolveActorSubAccountID(r.Context(), r, "")
	items, next, err := h.collectFollowListItems(
		r.Context(), viewerID, subAccountID, parseCursor(r), parseLimit(r, 20), false, parseListSearchQuery(r),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": next, "nextCursor": next})
}

// parseListSearchQuery 读取粉丝/关注列表的服务端搜索词（SIT2：搜索走云侧
// query + cursor + limit，端侧不做本地 contains 伪搜索）。
func parseListSearchQuery(r *http.Request) string {
	return strings.ToLower(strings.TrimSpace(r.URL.Query().Get("query")))
}

func (h *UserHandler) collectFollowListItems(
	ctx context.Context,
	viewerID, subAccountID, cursor string,
	limit int,
	listFollowing bool,
	searchQuery string,
) ([]map[string]any, string, error) {
	if limit <= 0 {
		limit = 20
	}
	items := make([]map[string]any, 0, limit)
	seen := make(map[string]struct{}, limit)
	nextCursor := cursor
	for len(items) < limit {
		var (
			edges []relmodel.Direction
			err   error
		)
		if listFollowing {
			edges, nextCursor, err = h.relationship.ListFollowing(ctx, subAccountID, nextCursor, limit)
		} else {
			edges, nextCursor, err = h.relationship.ListFollowers(ctx, subAccountID, nextCursor, limit)
		}
		if err != nil {
			return nil, "", err
		}
		if len(edges) == 0 {
			return items, "", nil
		}
		batch := h.buildFollowListItems(ctx, viewerID, edges, listFollowing)
		if len(batch) < len(edges) {
			reltelemetry.Collector().RecordFilterMismatch()
			usertelemetry.RolloutCollector().RecordAttributionMismatch()
		}
		for i := range batch {
			if !followListItemMatchesQuery(batch[i], searchQuery) {
				continue
			}
			subjectID := strings.TrimSpace(anyString(batch[i]["subAccountId"]))
			if subjectID != "" {
				if _, ok := seen[subjectID]; ok {
					continue
				}
				seen[subjectID] = struct{}{}
			}
			items = append(items, batch[i])
			if len(items) == limit {
				return items, nextCursor, nil
			}
		}
		if strings.TrimSpace(nextCursor) == "" {
			return items, "", nil
		}
	}
	return items, nextCursor, nil
}

// followListItemMatchesQuery 按昵称/用户名做服务端不区分大小写子串匹配；
// 空查询恒 true。匹配在 overfetch+fill 循环内执行，翻页语义与 block 过滤一致。
func followListItemMatchesQuery(item map[string]any, searchQuery string) bool {
	if searchQuery == "" {
		return true
	}
	for _, key := range [...]string{"displayName", "username", "subAccountId"} {
		if strings.Contains(strings.ToLower(anyString(item[key])), searchQuery) {
			return true
		}
	}
	return false
}

func (h *UserHandler) buildFollowListItems(
	ctx context.Context,
	viewerID string,
	edges []relmodel.Direction,
	listFollowing bool,
) []map[string]any {
	items := make([]map[string]any, 0, len(edges))
	for i := range edges {
		targetID := edges[i].SourcePersonaID
		if listFollowing {
			targetID = edges[i].TargetPersonaID
		}
		if targetID == "" {
			continue
		}
		if viewerID != "" {
			blocked, _ := h.relationship.CheckBlocked(ctx, viewerID, targetID)
			blockedBy, _ := h.relationship.CheckBlocked(ctx, targetID, viewerID)
			if blocked || blockedBy {
				continue
			}
		}
		view, err := h.subAccount.GetSubAccountProfileView(ctx, targetID)
		if err != nil || view == nil {
			reltelemetry.Collector().RecordPageDrift()
			usertelemetry.RolloutCollector().RecordAttributionMismatch()
			continue
		}
		item := map[string]any{
			"subAccountId":      view["subAccountId"],
			"username":          view["username"],
			"displayName":       view["displayName"],
			"avatarUrl":         view["avatarUrl"],
			"avatarVersion":     view["avatarVersion"],
			"profileVisibility": view["profileVisibility"],
			"followedAt":        optionalTimestampRFC3339(edges[i].FollowedAt),
		}
		if viewerID != "" {
			rel, _ := h.relationship.GetRelationship(ctx, viewerID, targetID)
			item["relationState"] = relationshipState(rel, viewerID, targetID)
			item["relationshipCapability"] = h.buildRelationshipCapabilityView(
				ctx, viewerID, targetID, rel, false, false,
			)
		} else {
			item["relationState"] = "not_following"
		}
		items = append(items, item)
	}
	return items
}

func optionalTimestampRFC3339(value *time.Time) string {
	if value == nil {
		return ""
	}
	return value.UTC().Format(time.RFC3339)
}
