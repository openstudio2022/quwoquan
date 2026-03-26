package http

import (
	"net/http"
	"strings"

	"quwoquan_service/services/user-service/internal/application"
	followrepo "quwoquan_service/services/user-service/internal/domain/follow/repository"
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
	mux.HandleFunc("GET /v1/me", h.handleGetMeProfile)
	mux.HandleFunc("GET /v1/user/{subAccountId}", h.handleGetSubAccountProfile)
	mux.HandleFunc("GET /v1/user/search/social-relations", h.handleSearchSocialRelations)
	mux.HandleFunc("GET /v1/user/search/recent", h.handleListRecentSearches)
	mux.HandleFunc("PUT /v1/user/search/recent/{entryId}", h.handleUpsertRecentSearch)
	mux.HandleFunc("DELETE /v1/user/search/recent/{entryId}", h.handleDeleteRecentSearch)
	mux.HandleFunc("DELETE /v1/user/search/recent", h.handleClearRecentSearches)

	mux.HandleFunc("POST /v1/user/follow/{targetUserId}", h.handleFollow)
	mux.HandleFunc("DELETE /v1/user/follow/{targetUserId}", h.handleUnfollow)
	mux.HandleFunc("GET /v1/users/{userId}/following", h.handleListFollowing)
	mux.HandleFunc("GET /v1/users/{userId}/followers", h.handleListFollowers)
	mux.HandleFunc("GET /v1/users/{userId}/relationship", h.handleGetRelationship)
	mux.HandleFunc("GET /v1/user/{userId}/relationship/capability", h.handleGetRelationshipCapability)

	mux.HandleFunc("POST /v1/user/block/{targetUserId}", h.handleBlock)
	mux.HandleFunc("DELETE /v1/user/block/{targetUserId}", h.handleUnblock)
	mux.HandleFunc("GET /v1/user/blocked", h.handleListBlocked)
	mux.HandleFunc("GET /v1/user/block/check/{targetUserId}", h.handleCheckBlocked)

	mux.HandleFunc("GET /v1/user/personas", h.handleListPersonas)
	mux.HandleFunc("POST /v1/user/personas", h.handleCreatePersona)
	mux.HandleFunc("PATCH /v1/user/personas/{personaId}", h.handleUpdatePersona)
	mux.HandleFunc("DELETE /v1/user/personas/{personaId}", h.handleDeletePersona)
	mux.HandleFunc("POST /v1/user/personas/{personaId}/activate", h.handleActivatePersona)

	mux.HandleFunc("GET /v1/users/{userId}/works", h.handleListUserWorks)
	mux.HandleFunc("GET /v1/users/{userId}/life-items", h.handleListUserLifeItems)
	mux.HandleFunc("GET /v1/users/{userId}/likes", h.handleListUserLikes)

	mux.HandleFunc("GET /v1/user/settings/notifications", h.handleGetNotificationSettings)
	mux.HandleFunc("PATCH /v1/user/settings/notifications", h.handleUpdateNotificationSettings)
	mux.HandleFunc("GET /v1/user/settings/privacy", h.handleGetPrivacySettings)
	mux.HandleFunc("PATCH /v1/user/settings/privacy", h.handleUpdatePrivacySettings)

	// Auth & Credentials
	mux.HandleFunc("POST /v1/auth/login", h.handleLogin)
	mux.HandleFunc("GET /v1/user/credentials", h.handleListCredentials)
	mux.HandleFunc("POST /v1/user/credentials", h.handleBindCredential)
	mux.HandleFunc("DELETE /v1/user/credentials/{credType}", h.handleUnbindCredential)

	// SubAccounts
	mux.HandleFunc("GET /v1/user/sub-accounts", h.handleListSubAccounts)
	mux.HandleFunc("POST /v1/user/sub-accounts", h.handleCreateSubAccount)
	mux.HandleFunc("POST /v1/user/sub-accounts/{subAccountId}/activate", h.handleActivateSubAccount)
	mux.HandleFunc("DELETE /v1/user/sub-accounts/{subAccountId}", h.handleDeleteSubAccount)
	mux.HandleFunc("GET /v1/sub-accounts/{subAccountId}", h.handleGetSubAccountProfile)

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
		writeInvalidArg(w, "userId is required")
		return
	}
	snap, err := h.profile.GetProfile(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	if snap == nil {
		writeNotFound(w, "user "+userID)
		return
	}
	writeJSON(w, http.StatusOK, snap)
}

func (h *UserHandler) handleUpdateProfile(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid request body")
		return
	}
	profile, err := h.profile.UpdateProfile(r.Context(), userID, data)
	if err != nil {
		if strings.Contains(err.Error(), "nickname_taken") {
			writeHTTPError(w, appErrNicknameTaken(err.Error()))
			return
		}
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, err.Error())
			return
		}
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, profile)
}

func (h *UserHandler) handleGetMeProfile(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	view, err := h.subAccount.GetMeProfileView(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	if view == nil {
		writeNotFound(w, "user "+userID)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *UserHandler) handleSearchSocialRelations(w http.ResponseWriter, r *http.Request) {
	viewerID := userIDFromHeader(r)
	if viewerID == "" {
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	query := strings.TrimSpace(r.URL.Query().Get("query"))
	if query == "" {
		writeJSON(w, http.StatusOK, map[string]any{"items": []map[string]any{}, "cursor": ""})
		return
	}
	items, err := h.search.SearchSocialRelations(r.Context(), query, parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	for _, item := range items {
		targetProfileSubjectID := strings.TrimSpace(anyString(item["profileSubjectId"]))
		targetOwnerID := strings.TrimSpace(anyString(item["ownerUserId"]))
		targetSubAccountID := strings.TrimSpace(anyString(item["subAccountId"]))
		relationTargetID := targetOwnerID
		if relationTargetID == "" {
			relationTargetID = targetProfileSubjectID
		}

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
		capability["targetProfileSubjectId"] = targetProfileSubjectID
		if targetSubAccountID != "" {
			capability["targetSubAccountId"] = targetSubAccountID
		}
		item["relationshipCapability"] = capability
		item["chatAvailable"] = capability["canOpenConversation"] == true
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": ""})
}

func (h *UserHandler) handleListRecentSearches(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	items, err := h.search.ListRecentSearches(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *UserHandler) handleUpsertRecentSearch(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	entryID := strings.TrimSpace(r.PathValue("entryId"))
	if entryID == "" {
		writeInvalidArg(w, "entryId is required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid body")
		return
	}
	if strings.TrimSpace(anyString(body["query"])) == "" {
		writeInvalidArg(w, "query is required")
		return
	}
	entry, created, err := h.search.UpsertRecentSearch(r.Context(), userID, entryID, body)
	if err != nil {
		writeHTTPError(w, err)
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
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	entryID := strings.TrimSpace(r.PathValue("entryId"))
	if entryID == "" {
		writeInvalidArg(w, "entryId is required")
		return
	}
	if err := h.search.DeleteRecentSearch(r.Context(), userID, entryID); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleClearRecentSearches(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	if err := h.search.ClearRecentSearches(r.Context(), userID); err != nil {
		writeHTTPError(w, err)
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
	followerID := userIDFromHeader(r)
	followeeID := r.PathValue("targetUserId")
	if followerID == "" || followeeID == "" {
		writeInvalidArg(w, "followerID and targetUserId required")
		return
	}
	if err := h.follow.Follow(r.Context(), followerID, followeeID); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleUnfollow(w http.ResponseWriter, r *http.Request) {
	followerID := userIDFromHeader(r)
	followeeID := r.PathValue("targetUserId")
	if followerID == "" || followeeID == "" {
		writeInvalidArg(w, "followerID and targetUserId required")
		return
	}
	if err := h.follow.Unfollow(r.Context(), followerID, followeeID); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleListFollowing(w http.ResponseWriter, r *http.Request) {
	userID := r.PathValue("userId")
	edges, next, err := h.follow.ListFollowing(r.Context(), userID, parseCursor(r), parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": edges, "nextCursor": next})
}

func (h *UserHandler) handleListFollowers(w http.ResponseWriter, r *http.Request) {
	userID := r.PathValue("userId")
	edges, next, err := h.follow.ListFollowers(r.Context(), userID, parseCursor(r), parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": edges, "nextCursor": next})
}

func (h *UserHandler) handleGetRelationship(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	targetID := r.PathValue("userId")
	if userID == "" || targetID == "" {
		writeInvalidArg(w, "userId required")
		return
	}
	rel, err := h.follow.GetRelationship(r.Context(), userID, targetID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, rel)
}

func (h *UserHandler) handleGetRelationshipCapability(w http.ResponseWriter, r *http.Request) {
	viewerID := userIDFromHeader(r)
	targetID := r.PathValue("userId")
	if viewerID == "" || targetID == "" {
		writeInvalidArg(w, "userId required")
		return
	}
	if targetID == "me" {
		targetID = viewerID
	}
	rel, err := h.follow.GetRelationship(r.Context(), viewerID, targetID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	isBlocked, err := h.block.CheckBlocked(r.Context(), viewerID, targetID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	isBlockedBy, err := h.block.CheckBlocked(r.Context(), targetID, viewerID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, buildRelationshipCapabilityView(viewerID, targetID, rel, isBlocked, isBlockedBy))
}

func (h *UserHandler) handleBlock(w http.ResponseWriter, r *http.Request) {
	blockerID := userIDFromHeader(r)
	blockedID := r.PathValue("targetUserId")
	if blockerID == "" || blockedID == "" {
		writeInvalidArg(w, "blockerID and targetUserId required")
		return
	}
	if err := h.block.Block(r.Context(), blockerID, blockedID); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleUnblock(w http.ResponseWriter, r *http.Request) {
	blockerID := userIDFromHeader(r)
	blockedID := r.PathValue("targetUserId")
	if blockerID == "" || blockedID == "" {
		writeInvalidArg(w, "blockerID and targetUserId required")
		return
	}
	if err := h.block.Unblock(r.Context(), blockerID, blockedID); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleListBlocked(w http.ResponseWriter, r *http.Request) {
	blockerID := userIDFromHeader(r)
	if blockerID == "" {
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	edges, next, err := h.block.ListBlocked(r.Context(), blockerID, parseCursor(r), parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": edges, "nextCursor": next})
}

func (h *UserHandler) handleCheckBlocked(w http.ResponseWriter, r *http.Request) {
	blockerID := userIDFromHeader(r)
	blockedID := r.PathValue("targetUserId")
	if blockerID == "" || blockedID == "" {
		writeInvalidArg(w, "blockerID and targetUserId required")
		return
	}
	blocked, err := h.block.CheckBlocked(r.Context(), blockerID, blockedID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"blocked": blocked})
}

func (h *UserHandler) handleListPersonas(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	personas, err := h.persona.List(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": personas})
}

func (h *UserHandler) handleCreatePersona(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid body")
		return
	}
	p, err := h.persona.Create(r.Context(), userID, data)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, p)
}

func (h *UserHandler) handleUpdatePersona(w http.ResponseWriter, r *http.Request) {
	personaID := r.PathValue("personaId")
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid body")
		return
	}
	p, err := h.persona.Update(r.Context(), personaID, data)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, err.Error())
			return
		}
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, p)
}

func (h *UserHandler) handleDeletePersona(w http.ResponseWriter, r *http.Request) {
	personaID := r.PathValue("personaId")
	err := h.persona.Delete(r.Context(), personaID)
	if err != nil {
		if strings.Contains(err.Error(), "primary") {
			writeForbidden(w, err.Error())
			return
		}
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, err.Error())
			return
		}
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleActivatePersona(w http.ResponseWriter, r *http.Request) {
	personaID := r.PathValue("personaId")
	err := h.persona.Activate(r.Context(), personaID)
	if err != nil {
		if strings.Contains(err.Error(), "not found") {
			writeNotFound(w, err.Error())
			return
		}
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleListUserWorks(w http.ResponseWriter, r *http.Request) {
	userID := r.PathValue("userId")
	works, next, err := h.work.ListUserWorks(r.Context(), userID, parseCursor(r), parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": works, "nextCursor": next})
}

func (h *UserHandler) handleListUserLifeItems(w http.ResponseWriter, r *http.Request) {
	userID := r.PathValue("userId")
	category := r.URL.Query().Get("category")
	items, next, err := h.lifeItem.ListUserLifeItems(r.Context(), userID, category, parseCursor(r), parseLimit(r, 20))
	if err != nil {
		writeHTTPError(w, err)
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
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	s, err := h.setting.GetNotificationSettings(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, err)
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
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid body")
		return
	}
	if err := h.setting.UpdateNotificationSettings(r.Context(), userID, data); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleGetPrivacySettings(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	s, err := h.setting.GetPrivacySettings(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, err)
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
		writeInvalidArg(w, "X-Client-User-Id header required")
		return
	}
	data, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid body")
		return
	}
	if err := h.setting.UpdatePrivacySettings(r.Context(), userID, data); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// --- Auth & Credentials ---

func (h *UserHandler) handleLogin(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid body")
		return
	}
	credType, _ := body["credentialType"].(string)
	credKey, _ := body["credentialKey"].(string)
	label, _ := body["displayLabel"].(string)
	if credType == "" || credKey == "" {
		writeInvalidArg(w, "credentialType and credentialKey required")
		return
	}
	result, err := h.auth.LoginWithCredential(r.Context(), credType, credKey, label)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleListCredentials(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	creds, err := h.auth.ListCredentials(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"credentials": creds})
}

func (h *UserHandler) handleBindCredential(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid body")
		return
	}
	credType, _ := body["credentialType"].(string)
	credKey, _ := body["credentialKey"].(string)
	label, _ := body["displayLabel"].(string)
	if err := h.auth.BindCredential(r.Context(), userID, credType, credKey, label); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleUnbindCredential(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	credType := r.PathValue("credType")
	if err := h.auth.UnbindCredential(r.Context(), userID, credType); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// --- SubAccounts ---

func (h *UserHandler) handleListSubAccounts(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	accounts, err := h.subAccount.ListSubAccounts(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"subAccounts": accounts})
}

func (h *UserHandler) handleCreateSubAccount(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid body")
		return
	}
	account, err := h.subAccount.CreateSubAccount(r.Context(), userID, body)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, account)
}

func (h *UserHandler) handleActivateSubAccount(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	subAccountID := r.PathValue("subAccountId")
	if err := h.subAccount.ActivateSubAccount(r.Context(), userID, subAccountID); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleDeleteSubAccount(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	subAccountID := r.PathValue("subAccountId")
	if err := h.subAccount.DeleteSubAccount(r.Context(), userID, subAccountID); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleGetSubAccountProfile(w http.ResponseWriter, r *http.Request) {
	subAccountID := r.PathValue("subAccountId")
	profile, err := h.subAccount.GetSubAccountProfileView(r.Context(), subAccountID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	if profile == nil {
		http.NotFound(w, r)
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
		"viewerProfileSubjectId": viewerID,
		"targetProfileSubjectId": targetID,
		"viewerSubAccountId":     viewerID,
		"targetSubAccountId":     targetID,
		"relationState":          relationState,
		"canFollow":              canFollow,
		"canUnfollow":            canUnfollow,
		"canMessage":             canMessage,
		"canFollowBack":          canFollowBack,
		"canOpenConversation":    canMessage,
		"canGreet":               false,
		"canAddSameInterest":     false,
		"canSetCloseFriend":      false,
		"canStartVoiceCall":      canStartVoiceCall,
		"canStartVideoCall":      canStartVideoCall,
		"isBlocked":              isBlocked,
		"isBlockedBy":            isBlockedBy,
	}
}

// --- Contact Discovery ---

func (h *UserHandler) handleInitiateContactDiscovery(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid body")
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
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusAccepted, record)
}

func (h *UserHandler) handleGetLatestContactDiscovery(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	record, err := h.contactDiscovery.GetLatest(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	if record == nil {
		http.NotFound(w, r)
		return
	}
	writeJSON(w, http.StatusOK, record)
}

func (h *UserHandler) handleDismissContactDiscovery(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	id := r.PathValue("id")
	if err := h.contactDiscovery.Dismiss(r.Context(), userID, id); err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// --- Invites ---

func (h *UserHandler) handleGenerateInvite(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, "invalid body")
		return
	}
	subAccountID, _ := body["subAccountId"].(string)
	channel, _ := body["channel"].(string)
	inviteePhone, _ := body["inviteePhone"].(string)
	if subAccountID == "" || channel == "" {
		writeInvalidArg(w, "subAccountId and channel required")
		return
	}
	record, err := h.invite.Generate(r.Context(), subAccountID, userID, channel, inviteePhone)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusCreated, record)
}

func (h *UserHandler) handleListInvites(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, "X-Client-User-Id required")
		return
	}
	subAccountID := r.URL.Query().Get("subAccountId")
	statusFilter := r.URL.Query().Get("status")
	records, err := h.invite.ListByInviter(r.Context(), subAccountID, statusFilter, 20, 0)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"invites": records})
}

func (h *UserHandler) handleGetInviteByCode(w http.ResponseWriter, r *http.Request) {
	code := r.PathValue("code")
	record, err := h.invite.GetByCode(r.Context(), code)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	if record == nil {
		http.NotFound(w, r)
		return
	}
	writeJSON(w, http.StatusOK, record)
}

func (h *UserHandler) handleAcceptInvite(w http.ResponseWriter, r *http.Request) {
	code := r.PathValue("code")
	record, err := h.invite.Accept(r.Context(), code)
	if err != nil {
		writeHTTPError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, record)
}
