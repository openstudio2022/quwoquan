package http

import (
	"context"
	"net/http"
	"strings"
	"time"

	runtimegovernance "quwoquan_service/runtime/governance"
	"quwoquan_service/services/user-service/internal/application"
	followmodel "quwoquan_service/services/user-service/internal/domain/follow/model"
	followrepo "quwoquan_service/services/user-service/internal/domain/follow/repository"
	followtelemetry "quwoquan_service/services/user-service/internal/domain/follow/telemetry"
	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
	"quwoquan_service/services/user-service/internal/generated"
)

type UserHandler struct {
	profile          *application.ProfileService
	search           *application.SearchService
	follow           *application.FollowService
	block            *application.BlockService
	persona          *application.PersonaService
	work             *application.WorkService
	lifeItem         *application.LifeItemService
	setting          *application.SettingService
	auth             *application.AuthService
	subAccount       *application.SubAccountService
	contactDiscovery *application.ContactDiscoveryService
	invite           *application.InviteService
}

func NewUserHandler(
	profile *application.ProfileService,
	search *application.SearchService,
	follow *application.FollowService,
	block *application.BlockService,
	persona *application.PersonaService,
	work *application.WorkService,
	lifeItem *application.LifeItemService,
	setting *application.SettingService,
	auth *application.AuthService,
	subAccount *application.SubAccountService,
	contactDiscovery *application.ContactDiscoveryService,
	invite *application.InviteService,
) *UserHandler {
	return &UserHandler{
		profile:          profile,
		search:           search,
		follow:           follow,
		block:            block,
		persona:          persona,
		work:             work,
		lifeItem:         lifeItem,
		setting:          setting,
		auth:             auth,
		subAccount:       subAccount,
		contactDiscovery: contactDiscovery,
		invite:           invite,
	}
}

func (h *UserHandler) Routes() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)

	mux.HandleFunc("GET /v1/user/profile/{userId}", h.handleGetProfile)
	mux.HandleFunc("PATCH /v1/user/profile", h.handleUpdateProfile)
	mux.HandleFunc("POST /v1/user/sync", h.handlePullUserSync)
	mux.HandleFunc("GET /v1/me", h.handleGetMeProfile)
	mux.HandleFunc("GET /v1/user/{subAccountId}", h.handleGetSubAccountProfile)
	mux.HandleFunc("GET /v1/user/search/social-relations", h.handleSearchSocialRelations)
	mux.HandleFunc("GET /v1/user/search/recent", h.handleListRecentSearches)
	mux.HandleFunc("PUT /v1/user/search/recent/{entryId}", h.handleUpsertRecentSearch)
	mux.HandleFunc("DELETE /v1/user/search/recent/{entryId}", h.handleDeleteRecentSearch)
	mux.HandleFunc("DELETE /v1/user/search/recent", h.handleClearRecentSearches)

	mux.HandleFunc("POST /v1/user/sub-accounts/{targetSubAccountId}/follow", h.handleFollow)
	mux.HandleFunc("DELETE /v1/user/sub-accounts/{targetSubAccountId}/follow", h.handleUnfollow)
	mux.HandleFunc("GET /v1/user/sub-accounts/{subAccountId}/following", h.handleListFollowing)
	mux.HandleFunc("GET /v1/user/sub-accounts/{subAccountId}/followers", h.handleListFollowers)
	mux.HandleFunc("GET /v1/user/sub-accounts/{subAccountId}/relationship", h.handleGetRelationship)
	mux.HandleFunc("GET /v1/user/sub-accounts/{subAccountId}/relationship/capability", h.handleGetRelationshipCapability)

	mux.HandleFunc("POST /v1/user/sub-accounts/{targetSubAccountId}/block", h.handleBlock)
	mux.HandleFunc("DELETE /v1/user/sub-accounts/{targetSubAccountId}/block", h.handleUnblock)
	mux.HandleFunc("GET /v1/user/blocked", h.handleListBlocked)
	mux.HandleFunc("GET /v1/user/sub-accounts/{targetSubAccountId}/block/check", h.handleCheckBlocked)

	mux.HandleFunc("GET /v1/user/personas", h.handleListPersonas)
	mux.HandleFunc("GET /v1/user/personas/summary", h.handleGetPersonaManagementSummary)
	mux.HandleFunc("GET /v1/user/personas/active", h.handleGetActivePersonaContext)
	mux.HandleFunc("POST /v1/user/personas", h.handleCreatePersona)
	mux.HandleFunc("PATCH /v1/user/personas/{subAccountId}", h.handleUpdatePersona)
	mux.HandleFunc("POST /v1/user/personas/{subAccountId}/profile-sync", h.handleApplyPersonaProfileSync)
	mux.HandleFunc("GET /v1/user/personas/{subAccountId}/lifecycle-guard", h.handleGetPersonaLifecycleGuard)
	mux.HandleFunc("POST /v1/user/personas/{subAccountId}/retire", h.handleRetirePersona)
	mux.HandleFunc("DELETE /v1/user/personas/{subAccountId}/delete-empty", h.handleDeleteEmptyPersona)
	mux.HandleFunc("POST /v1/user/personas/{subAccountId}/activate", h.handleActivatePersona)

	mux.HandleFunc("GET /v1/users/{userId}/works", h.handleListUserWorks)
	mux.HandleFunc("GET /v1/users/{userId}/life-items", h.handleListUserLifeItems)
	mux.HandleFunc("GET /v1/users/{userId}/likes", h.handleListUserLikes)

	mux.HandleFunc("GET /v1/user/settings/notifications", h.handleGetNotificationSettings)
	mux.HandleFunc("PATCH /v1/user/settings/notifications", h.handleUpdateNotificationSettings)
	mux.HandleFunc("GET /v1/user/settings/privacy", h.handleGetPrivacySettings)
	mux.HandleFunc("PATCH /v1/user/settings/privacy", h.handleUpdatePrivacySettings)

	// Auth & Credentials
	mux.HandleFunc("POST /v1/auth/login", h.handleLogin)
	mux.HandleFunc("POST /v1/auth/login/anonymous", h.handleAnonymousLogin)
	mux.HandleFunc("GET /v1/user/credentials", h.handleListCredentials)
	mux.HandleFunc("POST /v1/user/credentials", h.handleBindCredential)
	mux.HandleFunc("DELETE /v1/user/credentials/{credType}", h.handleUnbindCredential)

	// Contact Discovery
	mux.HandleFunc("POST /v1/user/contact-discovery", h.handleInitiateContactDiscovery)
	mux.HandleFunc("GET /v1/user/contact-discovery/latest", h.handleGetLatestContactDiscovery)
	mux.HandleFunc("DELETE /v1/user/contact-discovery/{id}", h.handleDismissContactDiscovery)

	// Invites
	mux.HandleFunc("POST /v1/user/invites", h.handleGenerateInvite)
	mux.HandleFunc("GET /v1/user/invites", h.handleListInvites)
	mux.HandleFunc("GET /v1/invites/{code}", h.handleGetInviteByCode)
	mux.HandleFunc("POST /v1/invites/{code}/accept", h.handleAcceptInvite)

	return mux
}

func (h *UserHandler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleGetProfile(w http.ResponseWriter, r *http.Request) {
	userID := r.PathValue("userId")
	if userID == "" {
		writeInvalidArg(w, r, "userId is required")
		return
	}
	snap, err := h.profile.GetProfile(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if snap == nil {
		writeNotFound(w, r, "user "+userID)
		return
	}
	writeJSON(w, http.StatusOK, snap)
}

func (h *UserHandler) handleUpdateProfile(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid request body")
		return
	}
	profile, err := h.profile.UpdateProfile(r.Context(), userID, data)
	if err != nil {
		if strings.Contains(err.Error(), "nickname_taken") {
			writeHTTPError(w, r, appErrNicknameTaken(err.Error()))
			return
		}
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, r, err.Error())
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, profile)
}

func (h *UserHandler) handleGetMeProfile(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	view, err := h.subAccount.GetMeProfileView(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if view == nil {
		writeNotFound(w, r, "user "+userID)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *UserHandler) handlePullUserSync(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid request body")
		return
	}
	afterSeq := int64(0)
	switch raw := body["afterSeq"].(type) {
	case float64:
		afterSeq = int64(raw)
	case int64:
		afterSeq = raw
	case int:
		afterSeq = int64(raw)
	}
	limit := 200
	if raw, ok := body["limit"].(float64); ok && int(raw) > 0 {
		limit = int(raw)
	}
	resp, err := h.profile.PullSync(r.Context(), userID, afterSeq, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *UserHandler) handleSearchSocialRelations(w http.ResponseWriter, r *http.Request) {
	viewerID := userIDFromHeader(r)
	if viewerID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	query := strings.TrimSpace(r.URL.Query().Get("query"))
	if query == "" {
		writeJSON(w, http.StatusOK, map[string]any{"items": []map[string]any{}, "cursor": ""})
		return
	}
	items, err := h.search.SearchSocialRelations(r.Context(), query, parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if activeViewerID, resolveErr := h.resolveActorProfileSubjectID(r.Context(), r, ""); resolveErr == nil && activeViewerID != "" {
		viewerID = activeViewerID
	}
	for _, item := range items {
		targetSubAccountID := strings.TrimSpace(anyString(item["subAccountId"]))
		relationTargetID := targetSubAccountID

		rel, _ := h.follow.GetRelationship(r.Context(), viewerID, relationTargetID)
		isBlocked, _ := h.block.CheckBlocked(r.Context(), viewerID, relationTargetID)
		isBlockedBy, _ := h.block.CheckBlocked(r.Context(), relationTargetID, viewerID)
		capability := buildRelationshipCapabilityView(
			viewerID,
			relationTargetID,
			rel,
			isBlocked,
			isBlockedBy,
		)
		if targetSubAccountID != "" {
			capability["targetSubAccountId"] = targetSubAccountID
		}
		if item["chatAvailable"] != nil && item["chatAvailable"] != capability["canOpenConversation"] {
			followtelemetry.Collector().RecordRelationshipCapabilityMismatch()
			usertelemetry.RolloutCollector().RecordAttributionMismatch()
		}
		item["relationshipCapability"] = capability
		item["chatAvailable"] = capability["canOpenConversation"] == true
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": ""})
}

func (h *UserHandler) handleListRecentSearches(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	items, err := h.search.ListRecentSearches(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *UserHandler) handleUpsertRecentSearch(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	entryID := strings.TrimSpace(r.PathValue("entryId"))
	if entryID == "" {
		writeInvalidArg(w, r, "entryId is required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	if strings.TrimSpace(anyString(body["query"])) == "" {
		writeInvalidArg(w, r, "query is required")
		return
	}
	entry, created, err := h.search.UpsertRecentSearch(r.Context(), userID, entryID, body)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	status := http.StatusOK
	if created {
		status = http.StatusCreated
	}
	writeJSON(w, status, entry)
}

func (h *UserHandler) handleDeleteRecentSearch(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	entryID := strings.TrimSpace(r.PathValue("entryId"))
	if entryID == "" {
		writeInvalidArg(w, r, "entryId is required")
		return
	}
	if err := h.search.DeleteRecentSearch(r.Context(), userID, entryID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleClearRecentSearches(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	if err := h.search.ClearRecentSearches(r.Context(), userID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func appErrNicknameTaken(msg string) error {
	return appErr("AppErrorFromNicknameTaken", msg)
}

func appErr(_, msg string) error {
	return appErrFromMsg(msg)
}

func appErrFromMsg(msg string) error {
	if strings.Contains(msg, "nickname_taken") {
		return appErrNickname(msg)
	}
	return nil
}

func appErrNickname(msg string) error {
	return (&nickErr{msg: msg})
}

func anyString(value any) string {
	if value == nil {
		return ""
	}
	if text, ok := value.(string); ok {
		return text
	}
	return ""
}

type nickErr struct{ msg string }

func (e *nickErr) Error() string { return e.msg }

func (h *UserHandler) handleFollow(w http.ResponseWriter, r *http.Request) {
	body := readOptionalBody(r)
	followeeID := strings.TrimSpace(r.PathValue("targetSubAccountId"))
	if followeeID == "" {
		writeInvalidArg(w, r, "targetSubAccountId required")
		return
	}
	followerID, err := h.resolveActorProfileSubjectID(r.Context(), r, anyString(body["actorSubAccountId"]))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	created, err := h.follow.Follow(r.Context(), followerID, followeeID, anyString(body["source"]))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	rel, err := h.follow.GetRelationship(r.Context(), followerID, followeeID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"actorSubAccountId":  followerID,
		"targetSubAccountId": followeeID,
		"relationState":      relationshipState(rel, followerID, followeeID),
		"idempotentReplay":   !created,
		"updatedAt":          currentTimestampRFC3339(),
	})
}

func (h *UserHandler) handleUnfollow(w http.ResponseWriter, r *http.Request) {
	body := readOptionalBody(r)
	followeeID := strings.TrimSpace(r.PathValue("targetSubAccountId"))
	if followeeID == "" {
		writeInvalidArg(w, r, "targetSubAccountId required")
		return
	}
	followerID, err := h.resolveActorProfileSubjectID(r.Context(), r, anyString(body["actorSubAccountId"]))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	deleted, err := h.follow.Unfollow(r.Context(), followerID, followeeID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	rel, err := h.follow.GetRelationship(r.Context(), followerID, followeeID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"actorSubAccountId":  followerID,
		"targetSubAccountId": followeeID,
		"relationState":      relationshipState(rel, followerID, followeeID),
		"idempotentReplay":   !deleted,
		"updatedAt":          currentTimestampRFC3339(),
	})
}

func (h *UserHandler) handleListFollowing(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	defer func() {
		followtelemetry.Collector().RecordGraphListLatency(time.Since(startedAt))
	}()
	subAccountID := strings.TrimSpace(r.PathValue("subAccountId"))
	viewerID, _ := h.resolveActorProfileSubjectID(r.Context(), r, "")
	items, next, err := h.collectFollowListItems(
		r.Context(),
		viewerID,
		subAccountID,
		parseCursor(r),
		parseLimit(r, 20),
		true,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": next, "nextCursor": next})
}

func (h *UserHandler) handleListFollowers(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	defer func() {
		followtelemetry.Collector().RecordGraphListLatency(time.Since(startedAt))
	}()
	subAccountID := strings.TrimSpace(r.PathValue("subAccountId"))
	viewerID, _ := h.resolveActorProfileSubjectID(r.Context(), r, "")
	items, next, err := h.collectFollowListItems(
		r.Context(),
		viewerID,
		subAccountID,
		parseCursor(r),
		parseLimit(r, 20),
		false,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": next, "nextCursor": next})
}

func (h *UserHandler) handleGetRelationship(w http.ResponseWriter, r *http.Request) {
	targetID := strings.TrimSpace(r.PathValue("subAccountId"))
	if targetID == "" {
		writeInvalidArg(w, r, "subAccountId required")
		return
	}
	userID, err := h.resolveActorProfileSubjectID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	rel, err := h.follow.GetRelationship(r.Context(), userID, targetID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, rel)
}

func (h *UserHandler) handleGetRelationshipCapability(w http.ResponseWriter, r *http.Request) {
	targetID := strings.TrimSpace(r.PathValue("subAccountId"))
	if targetID == "" {
		writeInvalidArg(w, r, "subAccountId required")
		return
	}
	viewerID, err := h.resolveActorProfileSubjectID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if targetID == "me" {
		targetID = viewerID
	}
	rel, err := h.follow.GetRelationship(r.Context(), viewerID, targetID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	isBlocked, err := h.block.CheckBlocked(r.Context(), viewerID, targetID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	isBlockedBy, err := h.block.CheckBlocked(r.Context(), targetID, viewerID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, buildRelationshipCapabilityView(viewerID, targetID, rel, isBlocked, isBlockedBy))
}

func (h *UserHandler) handleBlock(w http.ResponseWriter, r *http.Request) {
	blockedID := strings.TrimSpace(r.PathValue("targetSubAccountId"))
	if blockedID == "" {
		writeInvalidArg(w, r, "targetSubAccountId required")
		return
	}
	blockerID, err := h.resolveActorProfileSubjectID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if err := h.block.Block(r.Context(), blockerID, blockedID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleUnblock(w http.ResponseWriter, r *http.Request) {
	blockedID := strings.TrimSpace(r.PathValue("targetSubAccountId"))
	if blockedID == "" {
		writeInvalidArg(w, r, "targetSubAccountId required")
		return
	}
	blockerID, err := h.resolveActorProfileSubjectID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if err := h.block.Unblock(r.Context(), blockerID, blockedID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleListBlocked(w http.ResponseWriter, r *http.Request) {
	blockerID, err := h.resolveActorProfileSubjectID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	edges, next, err := h.block.ListBlocked(r.Context(), blockerID, parseCursor(r), parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": edges, "nextCursor": next})
}

func (h *UserHandler) handleCheckBlocked(w http.ResponseWriter, r *http.Request) {
	blockedID := strings.TrimSpace(r.PathValue("targetSubAccountId"))
	if blockedID == "" {
		writeInvalidArg(w, r, "targetSubAccountId required")
		return
	}
	blockerID, err := h.resolveActorProfileSubjectID(r.Context(), r, "")
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	blocked, err := h.block.CheckBlocked(r.Context(), blockerID, blockedID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"blocked": blocked})
}

func (h *UserHandler) resolveActorProfileSubjectID(
	ctx context.Context,
	r *http.Request,
	explicitActorID string,
) (string, error) {
	userID := strings.TrimSpace(userIDFromHeader(r))
	if userID == "" {
		return "", generated.AppErrorFromInvalidArgument("X-Client-User-Id header required")
	}
	actorID := strings.TrimSpace(explicitActorID)
	currentFallback := !runtimegovernance.PersonaContextEnabled() || !runtimegovernance.PersonaGraphEnabled()
	if actorID == "" {
		actorID = subAccountIDFromHeader(r)
	}
	if actorID != "" {
		if currentFallback {
			followtelemetry.Collector().RecordCurrentGraphRead()
		}
		return actorID, nil
	}
	activeContext, err := h.subAccount.GetActivePersonaContextView(ctx, userID)
	if err != nil {
		if currentFallback {
			followtelemetry.Collector().RecordCurrentGraphRead()
			return userID, nil
		}
		return "", err
	}
	actorID = strings.TrimSpace(anyString(activeContext["subAccountId"]))
	if actorID == "" {
		actorID = userID
		followtelemetry.Collector().RecordCurrentFollowRead()
		return actorID, nil
	}
	if currentFallback {
		followtelemetry.Collector().RecordCurrentGraphRead()
	}
	return actorID, nil
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

func currentTimestampRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339)
}

func relationshipState(rel *followrepo.Relationship, viewerID, targetID string) string {
	if viewerID == targetID {
		return "self"
	}
	if rel == nil {
		return "not_following"
	}
	switch {
	case rel.IsMutual:
		return "mutual"
	case rel.IsFollowing:
		return "following"
	case rel.IsFollowedBy:
		return "followed_by"
	default:
		return "not_following"
	}
}

func (h *UserHandler) collectFollowListItems(
	ctx context.Context,
	viewerID, profileSubjectID, cursor string,
	limit int,
	listFollowing bool,
) ([]map[string]any, string, error) {
	if limit <= 0 {
		limit = 20
	}
	items := make([]map[string]any, 0, limit)
	seen := make(map[string]struct{}, limit)
	nextCursor := cursor
	for len(items) < limit {
		var (
			edges []followmodel.FollowEdge
			err   error
		)
		if listFollowing {
			edges, nextCursor, err = h.follow.ListFollowing(ctx, profileSubjectID, nextCursor, limit)
		} else {
			edges, nextCursor, err = h.follow.ListFollowers(ctx, profileSubjectID, nextCursor, limit)
		}
		if err != nil {
			return nil, "", err
		}
		if len(edges) == 0 {
			return items, "", nil
		}
		batch := h.buildFollowListItems(ctx, viewerID, edges, listFollowing)
		if len(batch) < len(edges) {
			followtelemetry.Collector().RecordGraphFilterMismatch()
			usertelemetry.RolloutCollector().RecordAttributionMismatch()
		}
		for i := range batch {
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

func (h *UserHandler) buildFollowListItems(
	ctx context.Context,
	viewerID string,
	edges []followmodel.FollowEdge,
	listFollowing bool,
) []map[string]any {
	items := make([]map[string]any, 0, len(edges))
	for i := range edges {
		targetID := edges[i].FollowerID
		if listFollowing {
			targetID = edges[i].FolloweeID
		}
		if targetID == "" {
			continue
		}
		if viewerID != "" {
			blocked, _ := h.block.CheckBlocked(ctx, viewerID, targetID)
			blockedBy, _ := h.block.CheckBlocked(ctx, targetID, viewerID)
			if blocked || blockedBy {
				continue
			}
		}
		view, err := h.subAccount.GetSubAccountProfileView(ctx, targetID)
		if err != nil || view == nil {
			followtelemetry.Collector().RecordGraphPageDrift()
			usertelemetry.RolloutCollector().RecordAttributionMismatch()
			continue
		}
		item := map[string]any{
			"subAccountId":      view["subAccountId"],
			"username":          view["username"],
			"displayName":       view["displayName"],
			"avatarUrl":         view["avatarUrl"],
			"profileVisibility": view["profileVisibility"],
			"followedAt":        edges[i].CreatedAt.Format(time.RFC3339),
		}
		if viewerID != "" {
			rel, _ := h.follow.GetRelationship(ctx, viewerID, targetID)
			item["relationState"] = relationshipState(rel, viewerID, targetID)
		} else {
			item["relationState"] = "not_following"
		}
		items = append(items, item)
	}
	return items
}

func (h *UserHandler) handleListPersonas(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	personas, err := h.subAccount.ListSubAccounts(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items := make([]map[string]any, 0, len(personas))
	for i := range personas {
		items = append(items, application.BuildPersonaManagementItem(personas[i]))
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *UserHandler) handleGetPersonaManagementSummary(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	summary, err := h.subAccount.GetPersonaManagementSummary(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, summary)
}

func (h *UserHandler) handleGetActivePersonaContext(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	view, err := h.subAccount.GetActivePersonaContextView(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *UserHandler) handleCreatePersona(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	p, err := h.subAccount.CreateSubAccount(r.Context(), userID, data)
	if err != nil {
		if strings.Contains(err.Error(), "persona_handle_taken") {
			writeInvalidArg(w, r, "用户号已被占用")
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, application.BuildPersonaManagementItem(*p))
}

func (h *UserHandler) handleUpdatePersona(w http.ResponseWriter, r *http.Request) {
	personaID := r.PathValue("subAccountId")
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	p, err := h.subAccount.UpdatePersona(r.Context(), userID, personaID, data)
	if err != nil {
		if strings.Contains(err.Error(), "persona_handle_taken") {
			writeInvalidArg(w, r, "用户号已被占用")
			return
		}
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, r, err.Error())
			return
		}
		if strings.Contains(err.Error(), "retired persona") {
			writeInvalidArg(w, r, "已退役分身不可继续编辑")
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, application.BuildPersonaManagementItem(*p))
}

func (h *UserHandler) handleApplyPersonaProfileSync(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	personaID := r.PathValue("subAccountId")
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	result, err := h.subAccount.ApplyPersonaProfileSync(r.Context(), userID, personaID, data)
	if err != nil {
		if strings.Contains(err.Error(), "persona_handle_taken") {
			writeInvalidArg(w, r, "用户号已被占用")
			return
		}
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, r, err.Error())
			return
		}
		if strings.Contains(err.Error(), "retired persona") {
			writeInvalidArg(w, r, "已退役分身不可继续同步资料")
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleGetPersonaLifecycleGuard(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	personaID := r.PathValue("subAccountId")
	guard, err := h.subAccount.GetPersonaLifecycleGuard(r.Context(), userID, personaID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, guard)
}

func (h *UserHandler) handleDeletePersona(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	personaID := r.PathValue("subAccountId")
	err := h.subAccount.DeleteSubAccount(r.Context(), userID, personaID)
	if err != nil {
		if strings.Contains(err.Error(), "primary") ||
			strings.Contains(err.Error(), "last") ||
			strings.Contains(err.Error(), "switch to another persona") {
			writeForbidden(w, r, err.Error())
			return
		}
		if strings.Contains(err.Error(), "retired persona") {
			writeInvalidArg(w, r, "已退役分身不可删除")
			return
		}
		if strings.Contains(err.Error(), "must be retired") {
			writeConflict(w, r, "该分身已有记录归因，请使用退役而不是删除", err.Error())
			return
		}
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, r, err.Error())
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleRetirePersona(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	personaID := r.PathValue("subAccountId")
	view, err := h.subAccount.RetirePersona(r.Context(), userID, personaID)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, r, err.Error())
			return
		}
		if strings.Contains(err.Error(), "primary") ||
			strings.Contains(err.Error(), "last") ||
			strings.Contains(err.Error(), "switch to another persona") {
			writeForbidden(w, r, err.Error())
			return
		}
		if strings.Contains(err.Error(), "retired persona") {
			writeInvalidArg(w, r, "该分身已退役")
			return
		}
		if strings.Contains(err.Error(), "empty persona should be deleted directly") {
			writeInvalidArg(w, r, "空白分身请直接删除，无需退役")
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *UserHandler) handleDeleteEmptyPersona(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	personaID := r.PathValue("subAccountId")
	if err := h.subAccount.DeleteEmptyPersona(r.Context(), userID, personaID); err != nil {
		if strings.Contains(err.Error(), "primary") ||
			strings.Contains(err.Error(), "last") ||
			strings.Contains(err.Error(), "switch to another persona") {
			writeForbidden(w, r, err.Error())
			return
		}
		if strings.Contains(err.Error(), "retired persona") {
			writeInvalidArg(w, r, "已退役分身不可删除")
			return
		}
		if strings.Contains(err.Error(), "must be retired") {
			writeConflict(w, r, "该分身已有记录归因，请使用退役而不是删除", err.Error())
			return
		}
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, r, err.Error())
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleActivatePersona(w http.ResponseWriter, r *http.Request) {
	personaID := r.PathValue("subAccountId")
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	err := h.subAccount.ActivateSubAccount(r.Context(), userID, personaID)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, r, err.Error())
			return
		}
		if strings.Contains(err.Error(), "retired persona") {
			writeInvalidArg(w, r, "已退役分身不可再激活")
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleListUserWorks(w http.ResponseWriter, r *http.Request) {
	userID := r.PathValue("userId")
	works, next, err := h.work.ListUserWorks(r.Context(), userID, parseCursor(r), parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": works, "nextCursor": next})
}

func (h *UserHandler) handleListUserLifeItems(w http.ResponseWriter, r *http.Request) {
	userID := r.PathValue("userId")
	category := r.URL.Query().Get("category")
	items, next, err := h.lifeItem.ListUserLifeItems(r.Context(), userID, category, parseCursor(r), parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "nextCursor": next})
}

func (h *UserHandler) handleListUserLikes(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"items": []any{}, "nextCursor": ""})
}

func (h *UserHandler) handleGetNotificationSettings(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	s, err := h.setting.GetNotificationSettings(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if s == nil {
		writeJSON(w, http.StatusOK, map[string]any{})
		return
	}
	writeJSON(w, http.StatusOK, s)
}

func (h *UserHandler) handleUpdateNotificationSettings(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	if err := h.setting.UpdateNotificationSettings(r.Context(), userID, data); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleGetPrivacySettings(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	s, err := h.setting.GetPrivacySettings(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if s == nil {
		writeJSON(w, http.StatusOK, map[string]any{})
		return
	}
	writeJSON(w, http.StatusOK, s)
}

func (h *UserHandler) handleUpdatePrivacySettings(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	if err := h.setting.UpdatePrivacySettings(r.Context(), userID, data); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// --- Auth & Credentials ---

func (h *UserHandler) handleLogin(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	credType, _ := body["credentialType"].(string)
	credKey, _ := body["credentialKey"].(string)
	label, _ := body["displayLabel"].(string)
	if credType == "" || credKey == "" {
		writeInvalidArg(w, r, "credentialType and credentialKey required")
		return
	}
	result, err := h.auth.LoginWithCredential(r.Context(), credType, credKey, label)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleAnonymousLogin(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	installID, _ := body["installId"].(string)
	deviceFingerprintHash, _ := body["deviceFingerprintHash"].(string)
	platform, _ := body["platform"].(string)
	appVersion, _ := body["appVersion"].(string)
	if strings.TrimSpace(installID) == "" {
		writeInvalidArg(w, r, "installId required")
		return
	}
	if strings.TrimSpace(deviceFingerprintHash) == "" {
		writeInvalidArg(w, r, "deviceFingerprintHash required")
		return
	}
	result, err := h.auth.LoginAnonymously(
		r.Context(),
		installID,
		deviceFingerprintHash,
		platform,
		appVersion,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleListCredentials(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	creds, err := h.auth.ListCredentials(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"credentials": creds})
}

func (h *UserHandler) handleBindCredential(w http.ResponseWriter, r *http.Request) {
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
	credType, _ := body["credentialType"].(string)
	credKey, _ := body["credentialKey"].(string)
	label, _ := body["displayLabel"].(string)
	if err := h.auth.BindCredential(r.Context(), userID, credType, credKey, label); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleUnbindCredential(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	credType := r.PathValue("credType")
	if err := h.auth.UnbindCredential(r.Context(), userID, credType); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// --- SubAccounts ---

func (h *UserHandler) handleListSubAccounts(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	accounts, err := h.subAccount.ListSubAccounts(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"subAccounts": accounts})
}

func (h *UserHandler) handleCreateSubAccount(w http.ResponseWriter, r *http.Request) {
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
	account, err := h.subAccount.CreateSubAccount(r.Context(), userID, body)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, account)
}

func (h *UserHandler) handleActivateSubAccount(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	subAccountID := r.PathValue("subAccountId")
	if err := h.subAccount.ActivateSubAccount(r.Context(), userID, subAccountID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleDeleteSubAccount(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	subAccountID := r.PathValue("subAccountId")
	if err := h.subAccount.DeleteSubAccount(r.Context(), userID, subAccountID); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleGetSubAccountProfile(w http.ResponseWriter, r *http.Request) {
	subAccountID := r.PathValue("subAccountId")
	profile, err := h.subAccount.GetSubAccountProfileView(r.Context(), subAccountID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if profile == nil {
		writeNotFound(w, r, "resource not found")
		return
	}
	writeJSON(w, http.StatusOK, profile)
}

func buildRelationshipCapabilityView(viewerID, targetID string, rel *followrepo.Relationship, isBlocked, isBlockedBy bool) map[string]any {
	relationState := "not_following"
	canFollow := true
	canUnfollow := false
	canMessage := true
	canFollowBack := false
	canStartVoiceCall := false
	canStartVideoCall := false

	switch {
	case viewerID == targetID:
		relationState = "self"
		canFollow = false
		canMessage = false
	case rel != nil && rel.IsMutual:
		relationState = "mutual"
		canFollow = false
		canUnfollow = true
		canStartVoiceCall = true
		canStartVideoCall = true
	case rel != nil && rel.IsFollowing:
		relationState = "following"
		canFollow = false
		canUnfollow = true
	case rel != nil && rel.IsFollowedBy:
		relationState = "followed_by"
		canFollowBack = true
	}

	if isBlocked || isBlockedBy {
		canMessage = false
		canStartVoiceCall = false
		canStartVideoCall = false
	}

	return map[string]any{
		"viewerSubAccountId":  viewerID,
		"targetSubAccountId":  targetID,
		"relationState":       relationState,
		"canFollow":           canFollow,
		"canUnfollow":         canUnfollow,
		"canMessage":          canMessage,
		"canFollowBack":       canFollowBack,
		"canOpenConversation": canMessage,
		"canGreet":            false,
		"canAddSameInterest":  false,
		"canSetCloseFriend":   false,
		"canStartVoiceCall":   canStartVoiceCall,
		"canStartVideoCall":   canStartVideoCall,
		"isBlocked":           isBlocked,
		"isBlockedBy":         isBlockedBy,
	}
}

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
	writeJSON(w, http.StatusAccepted, record)
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
	writeJSON(w, http.StatusOK, record)
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

// --- Invites ---

func (h *UserHandler) handleGenerateInvite(w http.ResponseWriter, r *http.Request) {
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
	subAccountID, _ := body["subAccountId"].(string)
	channel, _ := body["channel"].(string)
	inviteePhone, _ := body["inviteePhone"].(string)
	if subAccountID == "" || channel == "" {
		writeInvalidArg(w, r, "subAccountId and channel required")
		return
	}
	record, err := h.invite.Generate(r.Context(), subAccountID, userID, channel, inviteePhone)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, record)
}

func (h *UserHandler) handleListInvites(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	subAccountID := r.URL.Query().Get("subAccountId")
	statusFilter := r.URL.Query().Get("status")
	records, err := h.invite.ListByInviter(r.Context(), subAccountID, statusFilter, 20, 0)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"invites": records})
}

func (h *UserHandler) handleGetInviteByCode(w http.ResponseWriter, r *http.Request) {
	code := r.PathValue("code")
	record, err := h.invite.GetByCode(r.Context(), code)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	if record == nil {
		writeNotFound(w, r, "resource not found")
		return
	}
	writeJSON(w, http.StatusOK, record)
}

func (h *UserHandler) handleAcceptInvite(w http.ResponseWriter, r *http.Request) {
	code := r.PathValue("code")
	record, err := h.invite.Accept(r.Context(), code)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, record)
}
