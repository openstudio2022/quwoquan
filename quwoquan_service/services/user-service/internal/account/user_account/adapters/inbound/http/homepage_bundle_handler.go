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
	targetID := strings.TrimSpace(r.PathValue("personaId"))
	if targetID == "" {
		writeInvalidArg(w, r, "personaId required")
		return
	}

	profile, err := h.persona.GetPersonaProfileView(r.Context(), targetID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if profile == nil {
		writeNotFound(w, r, "resource not found")
		return
	}

	// target 归一身份：persona/creator 使用 personaId；账号主页回落公开 userHandle，
	// 不把 owner 映射重新塞回公开 Profile wire。
	targetPersonaID := strings.TrimSpace(anyString(profile["personaId"]))
	if targetPersonaID == "" {
		targetPersonaID = strings.TrimSpace(anyString(profile["userHandle"]))
	}

	// viewer 解析（游客容忍）：无鉴权头 = 游客态，不报错，跳过关系能力。
	viewerID := ""
	if strings.TrimSpace(userIDFromHeader(r)) != "" {
		if resolved, resolveErr := h.resolveActorPersonaID(r.Context(), r, ""); resolveErr == nil {
			viewerID = strings.TrimSpace(resolved)
		}
	}
	isGuest := viewerID == ""
	isOwner := !isGuest && viewerID == targetPersonaID

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
	var relationshipCapability any
	relationToTarget := "not_following"
	if isOwner {
		relationToTarget = "self"
	}
	if !isGuest {
		rel, relErr := h.relationship.GetRelationship(r.Context(), viewerID, targetPersonaID)
		if relErr != nil {
			writeHTTPError(w, r, relErr)
			return
		}
		isBlocked, blockErr := h.relationship.CheckBlocked(r.Context(), viewerID, targetPersonaID)
		if blockErr != nil {
			writeHTTPError(w, r, blockErr)
			return
		}
		isBlockedBy, blockedByErr := h.relationship.CheckBlocked(r.Context(), targetPersonaID, viewerID)
		if blockedByErr != nil {
			writeHTTPError(w, r, blockedByErr)
			return
		}
		relationshipCapability = h.relationshipCapabilityView(r.Context(), viewerID, targetPersonaID, rel, isBlocked, isBlockedBy)
		relationToTarget = relationshipState(rel, viewerID, targetPersonaID)
	}

	viewerContext := map[string]any{
		"viewerPersonaId":    viewerID,
		"isOwner":            isOwner,
		"isGuest":            isGuest,
		"relationToTarget":   relationToTarget,
		"canViewFullProfile": true,
	}

	cacheVersion := homepageBundleCacheVersion(
		targetPersonaID,
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
