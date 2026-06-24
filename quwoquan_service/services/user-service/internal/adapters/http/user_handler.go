package http

import (
	"context"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	runtimegovernance "quwoquan_service/runtime/governance"
	"quwoquan_service/services/user-service/internal/application"
	followmodel "quwoquan_service/services/user-service/internal/domain/follow/model"
	followrepo "quwoquan_service/services/user-service/internal/domain/follow/repository"
	followtelemetry "quwoquan_service/services/user-service/internal/domain/follow/telemetry"
	usermodel "quwoquan_service/services/user-service/internal/domain/user/model"
	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
	"quwoquan_service/services/user-service/internal/generated"
)

type UserHandler struct {
	profile          *application.ProfileService
	search           *application.SearchService
	follow           *application.FollowService
	block            *application.BlockService
	greeting         *application.GreetingService
	persona          *application.PersonaService
	work             *application.WorkService
	lifeItem         *application.LifeItemService
	setting          *application.SettingService
	auth             *application.AuthService
	subAccount       *application.SubAccountService
	contactDiscovery *application.ContactDiscoveryService
	invite           *application.InviteService
	interestProfile  *application.InterestProfileService
}

func NewUserHandler(
	profile *application.ProfileService,
	search *application.SearchService,
	follow *application.FollowService,
	block *application.BlockService,
	greeting *application.GreetingService,
	persona *application.PersonaService,
	work *application.WorkService,
	lifeItem *application.LifeItemService,
	setting *application.SettingService,
	auth *application.AuthService,
	subAccount *application.SubAccountService,
	contactDiscovery *application.ContactDiscoveryService,
	invite *application.InviteService,
	interestProfile *application.InterestProfileService,
) *UserHandler {
	return &UserHandler{
		profile:          profile,
		search:           search,
		follow:           follow,
		block:            block,
		greeting:         greeting,
		persona:          persona,
		work:             work,
		lifeItem:         lifeItem,
		setting:          setting,
		auth:             auth,
		subAccount:       subAccount,
		contactDiscovery: contactDiscovery,
		invite:           invite,
		interestProfile:  interestProfile,
	}
}

func (h *UserHandler) Routes() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)

	mux.HandleFunc("GET /v1/user/profile/{userId}", h.handleGetProfile)
	mux.HandleFunc("GET /v1/user/profile/edit-snapshot", h.handleGetProfileEditSnapshot)
	mux.HandleFunc("GET /v1/user/profile/qr-card", h.handleGetProfileQRCard)
	mux.HandleFunc("GET /v1/public/profile/qr/resolve", h.handleResolveProfileQRToken)
	mux.HandleFunc("PATCH /v1/user/profile", h.handleUpdateProfile)
	mux.HandleFunc("POST /v1/user/sync", h.handlePullUserSync)
	mux.HandleFunc("GET /v1/me", h.handleGetMeProfile)
	mux.HandleFunc("GET /v1/user/{subAccountId}", h.handleGetSubAccountProfile)
	mux.HandleFunc("GET /v1/user/sub-accounts/{subAccountId}/homepage-bundle", h.handleGetUserHomepageBundle)
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

	h.registerGreetingRoutes(mux)

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
	mux.HandleFunc("GET /v1/users/{userId}/interest-profile", h.handleGetUserInterestProfile)

	mux.HandleFunc("GET /v1/user/settings/notifications", h.handleGetNotificationSettings)
	mux.HandleFunc("PATCH /v1/user/settings/notifications", h.handleUpdateNotificationSettings)
	mux.HandleFunc("GET /v1/user/settings/privacy", h.handleGetPrivacySettings)
	mux.HandleFunc("PATCH /v1/user/settings/privacy", h.handleUpdatePrivacySettings)

	// Auth & Credentials
	mux.HandleFunc("POST /v1/auth/otp/send", h.handleSendOtp)
	mux.HandleFunc("POST /internal/auth/otp-deliveries:callback", h.handleOtpDeliveryCallback)
	mux.HandleFunc("POST /v1/auth/login/phone", h.handleLoginWithPhone)
	mux.HandleFunc("POST /v1/auth/login/wechat", h.handleLoginWithWechat)
	mux.HandleFunc("POST /v1/auth/login/alipay", h.handleLoginWithAlipay)
	mux.HandleFunc("POST /v1/auth/login/qq", h.handleLoginWithQq)
	mux.HandleFunc("POST /v1/auth/login/apple", h.handleLoginWithApple)
	mux.HandleFunc("POST /v1/auth/login/one-tap", h.handleOneTapLogin)
	mux.HandleFunc("POST /v1/auth/login/one-tap/hint", h.handleOneTapLoginHint)
	mux.HandleFunc("POST /v1/auth/login/anonymous", h.handleAnonymousLogin)
	mux.HandleFunc("POST /v1/auth/token/refresh", h.handleRefreshToken)
	mux.HandleFunc("POST /v1/auth/logout", h.handleLogout)
	mux.HandleFunc("GET /v1/owner/credentials", h.handleListCredentials)
	mux.HandleFunc("POST /v1/owner/credentials/bind", h.handleBindCredential)
	mux.HandleFunc("POST /v1/owner/credentials/phone/bind", h.handleBindPhoneCredential)
	mux.HandleFunc("POST /v1/owner/credentials/carrier-phone/bind", h.handleBindCarrierPhoneCredential)
	mux.HandleFunc("DELETE /v1/owner/credentials/{credType}", h.handleUnbindCredential)
	mux.HandleFunc("GET /v1/user/credentials", h.handleListCredentials)
	mux.HandleFunc("POST /v1/user/credentials", h.handleBindCredential)
	mux.HandleFunc("DELETE /v1/user/credentials/{credType}", h.handleUnbindCredential)

	// Contact Discovery (paths owned by user_profile service.yaml: /v1/owner/...)
	mux.HandleFunc("POST /v1/owner/contact-discovery", h.handleInitiateContactDiscovery)
	mux.HandleFunc("GET /v1/owner/contact-discovery/latest", h.handleGetLatestContactDiscovery)
	mux.HandleFunc("DELETE /v1/owner/contact-discovery/{id}", h.handleDismissContactDiscovery)

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
		if hasUserErrorCode(err, "USER.USER.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, profileUpdateResponse(profile))
}

func profileUpdateResponse(profile *usermodel.UserProfile) map[string]any {
	if profile == nil {
		return map[string]any{}
	}
	return map[string]any{
		"userId":             profile.UserID,
		"accountState":       profile.AccountState,
		"nickname":           profile.Nickname,
		"nicknameCustomized": profile.NicknameCustomized,
		"avatarUrl":          profile.AvatarURL,
		"avatarAssetId":      profile.AvatarAssetID,
		"avatarVersion":      profile.AvatarVersion,
		"backgroundUrl":      profile.BackgroundURL,
		"backgroundAssetId":  profile.BackgroundAssetID,
		"bio":                profile.Bio,
		"identityTags":       profile.IdentityTags,
		"gender":             profile.Gender,
		"birthDate":          profile.BirthDate,
		"region":             profile.Region,
		"regionTagRef":       profile.RegionCode,
		"status":             profile.Status,
		"profileVersion":     profile.ProfileVersion,
		"updatedAt":          profile.UpdatedAt,
	}
}

func (h *UserHandler) handleGetProfileEditSnapshot(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	credentials, err := h.auth.ListCredentials(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	view, err := h.profile.GetEditSnapshot(r.Context(), userID, credentials)
	if err != nil {
		if hasUserErrorCode(err, "USER.USER.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *UserHandler) handleGetProfileQRCard(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	view, err := h.profile.GetQRCard(r.Context(), userID)
	if err != nil {
		if hasUserErrorCode(err, "USER.USER.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *UserHandler) handleResolveProfileQRToken(w http.ResponseWriter, r *http.Request) {
	handle := strings.TrimSpace(r.URL.Query().Get("handle"))
	token := strings.TrimSpace(r.URL.Query().Get("qr"))
	if token == "" {
		writeHTTPError(w, r, generated.AppErrorFromProfileQrTokenInvalid("qr token required"))
		return
	}
	view, err := h.profile.ResolveProfileQRToken(r.Context(), handle, token)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
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
	if activeViewerID, resolveErr := h.resolveActorSubAccountID(r.Context(), r, ""); resolveErr == nil && activeViewerID != "" {
		viewerID = activeViewerID
	}
	for _, item := range items {
		targetSubAccountID := strings.TrimSpace(anyString(item["subAccountId"]))
		relationTargetID := targetSubAccountID

		rel, _ := h.follow.GetRelationship(r.Context(), viewerID, relationTargetID)
		isBlocked, _ := h.block.CheckBlocked(r.Context(), viewerID, relationTargetID)
		isBlockedBy, _ := h.block.CheckBlocked(r.Context(), relationTargetID, viewerID)
		capability := h.buildRelationshipCapabilityView(
			r.Context(),
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

func anyString(value any) string {
	if value == nil {
		return ""
	}
	if text, ok := value.(string); ok {
		return text
	}
	return ""
}

func hasUserErrorCode(err error, want string) bool {
	if err == nil {
		return false
	}
	return rterr.NormalizeError(err).Code.String() == want
}

func userErrorDebugMessage(err error) string {
	if err == nil {
		return ""
	}
	return rterr.NormalizeError(err).DebugMessage
}

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
	followerID, err := h.resolveActorSubAccountID(r.Context(), r, anyString(body["actorSubAccountId"]))
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
	viewerID, _ := h.resolveActorSubAccountID(r.Context(), r, "")
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
	viewerID, _ := h.resolveActorSubAccountID(r.Context(), r, "")
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
	userID, err := h.resolveActorSubAccountID(r.Context(), r, "")
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
	viewerID, err := h.resolveActorSubAccountID(r.Context(), r, "")
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
	writeJSON(w, http.StatusOK, h.buildRelationshipCapabilityView(r.Context(), viewerID, targetID, rel, isBlocked, isBlockedBy))
}

func (h *UserHandler) handleBlock(w http.ResponseWriter, r *http.Request) {
	blockedID := strings.TrimSpace(r.PathValue("targetSubAccountId"))
	if blockedID == "" {
		writeInvalidArg(w, r, "targetSubAccountId required")
		return
	}
	blockerID, err := h.resolveActorSubAccountID(r.Context(), r, "")
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
	blockerID, err := h.resolveActorSubAccountID(r.Context(), r, "")
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
	blockerID, err := h.resolveActorSubAccountID(r.Context(), r, "")
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
	blockerID, err := h.resolveActorSubAccountID(r.Context(), r, "")
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

func (h *UserHandler) resolveActorSubAccountID(
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
	viewerID, subAccountID, cursor string,
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
			edges, nextCursor, err = h.follow.ListFollowing(ctx, subAccountID, nextCursor, limit)
		} else {
			edges, nextCursor, err = h.follow.ListFollowers(ctx, subAccountID, nextCursor, limit)
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
			"avatarVersion":     view["avatarVersion"],
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
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.handle_taken") {
			writeHTTPError(w, r, err)
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
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.handle_taken") {
			writeHTTPError(w, r, err)
			return
		}
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
			return
		}
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.retired_guard") {
			writeHTTPError(w, r, err)
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
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.handle_taken") {
			writeHTTPError(w, r, err)
			return
		}
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
			return
		}
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.retired_guard") {
			writeHTTPError(w, r, err)
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
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.primary_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.last_sub_account") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.active_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.retired_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.retire_required") {
			writeHTTPError(w, r, err)
			return
		}
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
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
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
			return
		}
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.primary_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.last_sub_account") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.active_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.retired_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.delete_empty_only") {
			writeHTTPError(w, r, err)
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
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.primary_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.last_sub_account") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.active_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.retired_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.retire_required") {
			writeHTTPError(w, r, err)
			return
		}
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
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
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
			return
		}
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.retired_guard") {
			writeHTTPError(w, r, err)
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

// handleGetUserInterestProfile serves the user-domain derived interest profile
// (rm_user_profile_view.interestProfile). Consumed by assistant-service for
// proactive service and by recommendation-engine for policy self-tuning.
func (h *UserHandler) handleGetUserInterestProfile(w http.ResponseWriter, r *http.Request) {
	userID := r.PathValue("userId")
	if userID == "" {
		writeInvalidArg(w, r, "userId path param required")
		return
	}
	view, err := h.interestProfile.Get(r.Context(), userID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
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

func (h *UserHandler) handleSendOtp(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	phone := strings.TrimSpace(anyString(body["phone"]))
	deviceID := strings.TrimSpace(anyString(body["deviceId"]))
	platform := strings.TrimSpace(anyString(body["platform"]))
	appVersion := strings.TrimSpace(anyString(body["appVersion"]))
	sourceOperation := strings.TrimSpace(anyString(body["sourceOperation"]))
	if phone == "" {
		writeInvalidArg(w, r, "phone required")
		return
	}
	result, err := h.auth.SendOtp(r.Context(), phone, deviceID, platform, appVersion, sourceOperation)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleOtpDeliveryCallback(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	requestID := strings.TrimSpace(anyString(body["requestId"]))
	status := strings.TrimSpace(anyString(body["status"]))
	normalizedError := strings.TrimSpace(anyString(body["normalizedError"]))
	if requestID == "" {
		writeInvalidArg(w, r, "requestId required")
		return
	}
	if status == "" {
		writeInvalidArg(w, r, "status required")
		return
	}
	if err := h.auth.HandleOtpDeliveryCallback(r.Context(), requestID, status, normalizedError); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{
		"requestId": requestID,
		"accepted":  true,
	})
}

func (h *UserHandler) handleLoginWithPhone(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	phone := strings.TrimSpace(anyString(body["phone"]))
	otpCode := strings.TrimSpace(anyString(body["otpCode"]))
	deviceID := strings.TrimSpace(anyString(body["deviceId"]))
	platform := strings.TrimSpace(anyString(body["platform"]))
	appVersion := strings.TrimSpace(anyString(body["appVersion"]))
	agreementVersion := strings.TrimSpace(anyString(body["agreementVersion"]))
	privacyVersion := strings.TrimSpace(anyString(body["privacyVersion"]))
	if phone == "" {
		writeInvalidArg(w, r, "phone required")
		return
	}
	result, err := h.auth.LoginWithPhone(
		r.Context(),
		phone,
		otpCode,
		"",
		deviceID,
		platform,
		appVersion,
		agreementVersion,
		privacyVersion,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleLoginWithWechat(w http.ResponseWriter, r *http.Request) {
	h.handleSocialProviderLogin(w, r, "wechat", "wechatCode")
}

func (h *UserHandler) handleLoginWithAlipay(w http.ResponseWriter, r *http.Request) {
	h.handleSocialProviderLogin(w, r, "alipay", "alipayAuthCode")
}

func (h *UserHandler) handleLoginWithQq(w http.ResponseWriter, r *http.Request) {
	h.handleSocialProviderLogin(w, r, "qq", "qqAuthCode")
}

func (h *UserHandler) handleLoginWithApple(w http.ResponseWriter, r *http.Request) {
	h.handleTypedCredentialLogin(w, r, "apple", "appleIdToken")
}

// handleSocialProviderLogin 处理微信/支付宝/QQ：App 只上传短期授权码，服务端置换稳定身份并首次同步资料。
func (h *UserHandler) handleSocialProviderLogin(w http.ResponseWriter, r *http.Request, provider, primaryField string) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	authCode := strings.TrimSpace(anyString(body[primaryField]))
	deviceID := strings.TrimSpace(anyString(body["deviceId"]))
	platform := strings.TrimSpace(anyString(body["platform"]))
	appVersion := strings.TrimSpace(anyString(body["appVersion"]))
	if authCode == "" {
		writeInvalidArg(w, r, primaryField+" required")
		return
	}
	result, err := h.auth.LoginWithSocialProvider(r.Context(), provider, authCode, deviceID, platform, appVersion)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleTypedCredentialLogin(w http.ResponseWriter, r *http.Request, credType, primaryField string) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	credKey := strings.TrimSpace(anyString(body[primaryField]))
	label := strings.TrimSpace(anyString(body["displayLabel"]))
	if credKey == "" {
		writeInvalidArg(w, r, primaryField+" required")
		return
	}
	result, err := h.auth.LoginWithCredential(r.Context(), credType, credKey, label)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleOneTapLogin(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	vendor := strings.TrimSpace(anyString(body["vendor"]))
	carrierToken := strings.TrimSpace(anyString(body["carrierToken"]))
	deviceID := strings.TrimSpace(anyString(body["deviceId"]))
	platform := strings.TrimSpace(anyString(body["platform"]))
	appVersion := strings.TrimSpace(anyString(body["appVersion"]))
	agreementVersion := strings.TrimSpace(anyString(body["agreementVersion"]))
	privacyVersion := strings.TrimSpace(anyString(body["privacyVersion"]))
	if carrierToken == "" {
		writeInvalidArg(w, r, "carrierToken required")
		return
	}
	result, err := h.auth.LoginWithOneTap(
		r.Context(),
		vendor,
		carrierToken,
		deviceID,
		platform,
		appVersion,
		agreementVersion,
		privacyVersion,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleOneTapLoginHint(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	vendor := strings.TrimSpace(anyString(body["vendor"]))
	carrierToken := strings.TrimSpace(anyString(body["carrierToken"]))
	deviceID := strings.TrimSpace(anyString(body["deviceId"]))
	platform := strings.TrimSpace(anyString(body["platform"]))
	appVersion := strings.TrimSpace(anyString(body["appVersion"]))
	if carrierToken == "" {
		writeInvalidArg(w, r, "carrierToken required")
		return
	}
	result, err := h.auth.ResolveOneTapLoginHint(
		r.Context(),
		vendor,
		carrierToken,
		deviceID,
		platform,
		appVersion,
	)
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

func (h *UserHandler) handleRefreshToken(w http.ResponseWriter, r *http.Request) {
	body, err := readBody(r)
	if err != nil {
		writeInvalidArg(w, r, "invalid body")
		return
	}
	refreshToken := strings.TrimSpace(anyString(body["refreshToken"]))
	if refreshToken == "" {
		writeInvalidArg(w, r, "refreshToken required")
		return
	}
	result, err := h.auth.RefreshToken(r.Context(), refreshToken)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleLogout(w http.ResponseWriter, r *http.Request) {
	body, _ := readBody(r)
	ownerID := strings.TrimSpace(userIDFromHeader(r))
	refreshToken := strings.TrimSpace(anyString(body["refreshToken"]))
	if err := h.auth.Logout(r.Context(), ownerID, refreshToken); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
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

func (h *UserHandler) handleBindPhoneCredential(w http.ResponseWriter, r *http.Request) {
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
	phone, _ := body["phone"].(string)
	otpCode, _ := body["otpCode"].(string)
	label, _ := body["displayLabel"].(string)
	if err := h.auth.BindPhoneCredential(r.Context(), userID, phone, otpCode, label); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *UserHandler) handleBindCarrierPhoneCredential(w http.ResponseWriter, r *http.Request) {
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
	vendor, _ := body["vendor"].(string)
	carrierToken, _ := body["carrierToken"].(string)
	deviceID, _ := body["deviceId"].(string)
	platform, _ := body["platform"].(string)
	label, _ := body["displayLabel"].(string)
	if err := h.auth.BindCarrierPhoneCredential(r.Context(), userID, vendor, carrierToken, deviceID, platform, label); err != nil {
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

// --- Invites ---
