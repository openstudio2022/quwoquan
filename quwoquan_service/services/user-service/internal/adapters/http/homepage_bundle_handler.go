package http

import (
	"crypto/sha1"
	"encoding/hex"
	"net/http"
	"strings"
)

// handleGetUserHomepageBundle 主页首屏聚合（锁定决策 #1）：一次返回身份域真相
// profile / stats / relationshipCapability / tabCounts / viewerContext / cacheVersion，
// 消除首屏串行阻塞。交集与影响力 evidence 仍由 content 域接口端侧并发拉取，user 域不聚合
// content / intersection 事实，避免成为内容事实第二真相源。auth=optional，游客可读公开档案。
func (h *UserHandler) handleGetUserHomepageBundle(w http.ResponseWriter, r *http.Request) {
	targetID := strings.TrimSpace(r.PathValue("subAccountId"))
	if targetID == "" {
		writeInvalidArg(w, r, "subAccountId required")
		return
	}

	profile, err := h.subAccount.GetSubAccountProfileView(r.Context(), targetID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if profile == nil {
		writeNotFound(w, r, "resource not found")
		return
	}

	// target 归一身份：persona 优先 subAccountId，owner 态回落 userId。
	targetSubAccountID := strings.TrimSpace(anyString(profile["subAccountId"]))
	if targetSubAccountID == "" {
		targetSubAccountID = strings.TrimSpace(anyString(profile["userId"]))
	}

	// viewer 解析（游客容忍）：无鉴权头 = 游客态，不报错，跳过关系能力。
	viewerID := ""
	if strings.TrimSpace(userIDFromHeader(r)) != "" {
		if resolved, resolveErr := h.resolveActorSubAccountID(r.Context(), r, ""); resolveErr == nil {
			viewerID = strings.TrimSpace(resolved)
		}
	}
	isGuest := viewerID == ""
	isOwner := !isGuest && viewerID == targetSubAccountID

	// stats：仅身份域可直接计数的真相（与 UserProfileStatsWire 对齐）。
	stats := map[string]any{
		"followingCount": homepageCount(profile["followingCount"]),
		"followerCount":  homepageCount(profile["followerCount"]),
		"circleCount":    homepageCount(profile["circleCount"]),
		"likeCount":      homepageCount(profile["likeCount"]),
		"postCount":      homepageCount(profile["postCount"]),
	}

	// tabCounts：Tab 角标计数。collectionsCount 属 content 域，user 域不造假，置 0 由端覆盖。
	tabCounts := map[string]any{
		"worksCount":       homepageCount(profile["postCount"]),
		"likesCount":       homepageCount(profile["likeCount"]),
		"circlesCount":     homepageCount(profile["circleCount"]),
		"collectionsCount": 0,
	}

	// relationshipCapability：viewer→target 关系能力。游客态不下发（端按 nil 走未登录引导）。
	var relationshipCapability map[string]any
	relationToTarget := "not_following"
	if isOwner {
		relationToTarget = "self"
	}
	if !isGuest {
		rel, relErr := h.relationship.GetRelationship(r.Context(), viewerID, targetSubAccountID)
		if relErr != nil {
			writeHTTPError(w, r, relErr)
			return
		}
		isBlocked, blockErr := h.relationship.CheckBlocked(r.Context(), viewerID, targetSubAccountID)
		if blockErr != nil {
			writeHTTPError(w, r, blockErr)
			return
		}
		isBlockedBy, blockedByErr := h.relationship.CheckBlocked(r.Context(), targetSubAccountID, viewerID)
		if blockedByErr != nil {
			writeHTTPError(w, r, blockedByErr)
			return
		}
		relationshipCapability = h.buildRelationshipCapabilityView(r.Context(), viewerID, targetSubAccountID, rel, isBlocked, isBlockedBy)
		relationToTarget = relationshipState(rel, viewerID, targetSubAccountID)
	}

	viewerContext := map[string]any{
		"viewerSubAccountId": viewerID,
		"isOwner":            isOwner,
		"isGuest":            isGuest,
		"relationToTarget":   relationToTarget,
		"canViewFullProfile": true,
	}

	cacheVersion := homepageBundleCacheVersion(
		targetSubAccountID,
		anyString(profile["updatedAt"]),
		viewerID,
		relationToTarget,
	)

	bundle := map[string]any{
		"profile":                profile,
		"stats":                  stats,
		"relationshipCapability": relationshipCapability,
		"tabCounts":              tabCounts,
		"viewerContext":          viewerContext,
		"cacheVersion":           cacheVersion,
	}
	writeJSON(w, http.StatusOK, bundle)
}

// homepageCount 将 profile 视图中的计数字段归一为 int（容忍 int / int64 / float64）。
func homepageCount(value any) int {
	switch v := value.(type) {
	case int:
		return v
	case int32:
		return int(v)
	case int64:
		return int(v)
	case float64:
		return int(v)
	case float32:
		return int(v)
	default:
		return 0
	}
}

// homepageBundleCacheVersion 生成主页 bundle 版本锚：随档案更新时间 / viewer / 关系态变化，
// 供端做乐观回填与并发刷新一致性校验。
func homepageBundleCacheVersion(parts ...string) string {
	sum := sha1.Sum([]byte(strings.Join(parts, "|")))
	return hex.EncodeToString(sum[:])[:16]
}
