package http

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/user-service/internal/application"
	credentialapp "quwoquan_service/services/user-service/internal/application/account/credential_binding"
	registrationapp "quwoquan_service/services/user-service/internal/application/account/device_registration"
	accountlifecycleapp "quwoquan_service/services/user-service/internal/application/account/user_account"
	usersettingsapp "quwoquan_service/services/user-service/internal/application/account/user_settings"
	proposalapp "quwoquan_service/services/user-service/internal/application/persona/profile_update_proposal"
	visitapp "quwoquan_service/services/user-service/internal/application/relationship/followed_subject_visit_state"
	followingapp "quwoquan_service/services/user-service/internal/application/relationship/following_subject"
	relationshipapp "quwoquan_service/services/user-service/internal/application/relationship/persona_relationship"
	subjectfollowapp "quwoquan_service/services/user-service/internal/application/relationship/subject_follow"
	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
	relmodel "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/model"
	reltelemetry "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/telemetry"
	usermodel "quwoquan_service/services/user-service/internal/domain/user/model"
	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
	"quwoquan_service/services/user-service/internal/generated"
)

type UserHandler struct {
	profile                    *application.ProfileService
	search                     *application.SearchService
	relationship               *relationshipapp.PersonaRelationshipService
	greeting                   *application.GreetingService
	settingsCommands           *usersettingsapp.UserSettingsCommandFacade
	settingsQueries            *usersettingsapp.UserSettingsQueryFacade
	auth                       *application.AuthService
	credentialQueries          *credentialapp.CredentialQueryFacade
	deviceRegistrationCommands *registrationapp.CommandFacade
	deviceRegistrationQueries  *registrationapp.QueryFacade
	subAccount                 *application.SubAccountService
	contactDiscovery           *application.ContactDiscoveryService
	interestProfile            *application.InterestProfileService
	profileProposal            *proposalapp.Facade
	subjectFollow              *subjectfollowapp.SubjectFollowService
	followedSubjectVisit       *visitapp.VisitService
	followingSubjects          *followingapp.QueryService
	accountLifecycle           *accountlifecycleapp.CloseAccountFacade
	accountEnforcement         *accountlifecycleapp.AccountEnforcementCommandFacade
	accountSecurity            accountports.AccountSecurityReader
	wechatLogin                *application.FederatedLoginFacade
	alipayLogin                *application.FederatedLoginFacade
	qqLogin                    *application.FederatedLoginFacade
}

// WithAccountLifecycle 注入 UserAccount 生命周期终态 facade（CloseAccount）。
func (h *UserHandler) WithAccountLifecycle(
	facade *accountlifecycleapp.CloseAccountFacade,
) *UserHandler {
	h.accountLifecycle = facade
	return h
}

// WithAccountEnforcement 注入受信 Suspend/Restore command facade。
func (h *UserHandler) WithAccountEnforcement(
	facade *accountlifecycleapp.AccountEnforcementCommandFacade,
) *UserHandler {
	h.accountEnforcement = facade
	return h
}

// WithAccountSecurityReader 注入认证后终端用户请求的 fail-closed 安全状态校验。
func (h *UserHandler) WithAccountSecurityReader(
	reader accountports.AccountSecurityReader,
) *UserHandler {
	h.accountSecurity = reader
	return h
}

// WithFederatedLogins injects the explicitly bound authorization capabilities
// for the corresponding published HTTP routes.
func (h *UserHandler) WithFederatedLogins(
	wechat *application.FederatedLoginFacade,
	alipay *application.FederatedLoginFacade,
	qq *application.FederatedLoginFacade,
) *UserHandler {
	h.wechatLogin = wechat
	h.alipayLogin = alipay
	h.qqLogin = qq
	return h
}

const (
	PullUserSyncPath   = "/user/sync"
	LoginAnonymousPath = "/auth/login/anonymous"
)

func NewUserHandler(
	profile *application.ProfileService,
	search *application.SearchService,
	relationship *relationshipapp.PersonaRelationshipService,
	greeting *application.GreetingService,
	settingsCommands *usersettingsapp.UserSettingsCommandFacade,
	settingsQueries *usersettingsapp.UserSettingsQueryFacade,
	auth *application.AuthService,
	credentialQueries *credentialapp.CredentialQueryFacade,
	deviceRegistrationCommands *registrationapp.CommandFacade,
	deviceRegistrationQueries *registrationapp.QueryFacade,
	subAccount *application.SubAccountService,
	contactDiscovery *application.ContactDiscoveryService,
	interestProfile *application.InterestProfileService,
	profileProposal *proposalapp.Facade,
	subjectFollow *subjectfollowapp.SubjectFollowService,
	followedSubjectVisit *visitapp.VisitService,
	followingSubjects *followingapp.QueryService,
) (*UserHandler, error) {
	if profileProposal == nil {
		return nil, errors.New("ProfileUpdateProposal Facade is required")
	}
	if settingsCommands == nil || settingsQueries == nil {
		return nil, errors.New("UserSettings facades are required")
	}
	if credentialQueries == nil {
		return nil, errors.New("CredentialBinding query facade is required")
	}
	if deviceRegistrationCommands == nil || deviceRegistrationQueries == nil {
		return nil, errors.New("DeviceRegistration facades are required")
	}
	handler := &UserHandler{
		profile:                    profile,
		search:                     search,
		relationship:               relationship,
		greeting:                   greeting,
		settingsCommands:           settingsCommands,
		settingsQueries:            settingsQueries,
		auth:                       auth,
		credentialQueries:          credentialQueries,
		deviceRegistrationCommands: deviceRegistrationCommands,
		deviceRegistrationQueries:  deviceRegistrationQueries,
		subAccount:                 subAccount,
		contactDiscovery:           contactDiscovery,
		interestProfile:            interestProfile,
		profileProposal:            profileProposal,
		subjectFollow:              subjectFollow,
		followedSubjectVisit:       followedSubjectVisit,
		followingSubjects:          followingSubjects,
	}
	return handler, nil
}

func (h *UserHandler) Routes() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)

	mux.HandleFunc("GET /user/profile/{userId}", h.handleGetProfile)
	mux.HandleFunc("GET /user/profile/edit-snapshot", h.handleGetProfileEditSnapshot)
	mux.HandleFunc("GET /user/profile/qr-card", h.handleGetProfileQRCard)
	mux.HandleFunc("GET /public/profile/qr/resolve", h.handleResolveProfileQRToken)
	mux.HandleFunc("PATCH /user/profile", h.handleUpdateProfile)
	mux.HandleFunc("POST "+PullUserSyncPath, h.handlePullUserSync)
	mux.HandleFunc("GET /me", h.handleGetMeProfile)
	mux.HandleFunc("GET /user/{subAccountId}", h.handleGetSubAccountProfile)
	mux.HandleFunc("GET /user/sub-accounts/{subAccountId}/homepage-bundle", h.handleGetUserHomepageBundle)
	mux.HandleFunc("GET /user/search/social-relations", h.handleSearchSocialRelations)

	mux.HandleFunc("POST /user/sub-accounts/{targetSubAccountId}/follow", h.handleFollow)
	mux.HandleFunc("DELETE /user/sub-accounts/{targetSubAccountId}/follow", h.handleUnfollow)
	mux.HandleFunc("GET /user/sub-accounts/{subAccountId}/following", h.handleListFollowing)
	mux.HandleFunc("GET /user/sub-accounts/{subAccountId}/followers", h.handleListFollowers)
	mux.HandleFunc("GET /user/sub-accounts/{subAccountId}/relationship", h.handleGetRelationship)
	mux.HandleFunc("GET /user/sub-accounts/{subAccountId}/relationship/capability", h.handleGetRelationshipCapability)

	mux.HandleFunc("POST /user/sub-accounts/{targetSubAccountId}/block", h.handleBlock)
	mux.HandleFunc("DELETE /user/sub-accounts/{targetSubAccountId}/block", h.handleUnblock)
	mux.HandleFunc("GET /user/blocked", h.handleListBlocked)

	h.registerGreetingRoutes(mux)
	h.registerProfileProposalRoutes(mux)
	h.registerSubjectFollowRoutes(mux)
	h.registerAccountLifecycleRoutes(mux)
	h.registerDeviceRegistrationRoutes(mux)

	mux.HandleFunc("GET /user/personas", h.handleListPersonas)
	mux.HandleFunc("GET /user/personas/summary", h.handleGetPersonaManagementSummary)
	mux.HandleFunc("GET /user/personas/active", h.handleGetActivePersonaContext)
	mux.HandleFunc("POST /user/personas", h.handleCreatePersona)
	mux.HandleFunc("PATCH /user/personas/{subAccountId}", h.handleUpdatePersona)
	mux.HandleFunc("POST /user/personas/{subAccountId}/profile-sync", h.handleApplyPersonaProfileSync)
	mux.HandleFunc("GET /user/personas/{subAccountId}/lifecycle-guard", h.handleGetPersonaLifecycleGuard)
	mux.HandleFunc("POST /user/personas/{subAccountId}/retire", h.handleRetirePersona)
	mux.HandleFunc("POST /user/personas/{subAccountId}/activate", h.handleActivatePersona)

	mux.HandleFunc("GET /users/{userId}/interest-profile", h.handleGetUserInterestProfile)

	mux.HandleFunc("GET /user/settings/notifications", h.handleGetNotificationSettings)
	mux.HandleFunc("PATCH /user/settings/notifications", h.handleUpdateNotificationSettings)
	mux.HandleFunc("GET /user/settings/privacy", h.handleGetPrivacySettings)
	mux.HandleFunc("PATCH /user/settings/privacy", h.handleUpdatePrivacySettings)
	mux.HandleFunc("GET /user/settings/calls", h.handleGetCallSettings)
	mux.HandleFunc("PATCH /user/settings/calls", h.handleUpdateCallSettings)
	mux.HandleFunc("GET /user/settings/appearance", h.handleGetAppearanceSettings)
	mux.HandleFunc("PATCH /user/settings/appearance", h.handleUpdateAppearanceSettings)
	// Auth & Credentials
	mux.HandleFunc("POST /auth/otp/send", h.handleSendOtp)
	mux.HandleFunc("POST /internal/auth/otp-deliveries:callback", h.handleOtpDeliveryCallback)
	mux.HandleFunc("POST /auth/login/phone", h.handleLoginWithPhone)
	mux.HandleFunc("POST /auth/authorization/alipay", h.handleCreateAlipayAuthorizationRequest)
	mux.HandleFunc("POST /auth/login/wechat", h.handleLoginWithWechat)
	mux.HandleFunc("POST /auth/login/alipay", h.handleLoginWithAlipay)
	mux.HandleFunc("POST /auth/login/qq", h.handleLoginWithQq)
	mux.HandleFunc("POST /auth/login/one-tap", h.handleOneTapLogin)
	mux.HandleFunc("POST /auth/login/one-tap/hint", h.handleOneTapLoginHint)
	mux.HandleFunc("POST "+LoginAnonymousPath, h.handleAnonymousLogin)
	mux.HandleFunc("POST /auth/token/refresh", h.handleRefreshToken)
	mux.HandleFunc("POST /auth/logout", h.handleLogout)
	mux.HandleFunc("GET /owner/credentials", h.handleListCredentials)
	mux.HandleFunc("POST /owner/credentials/phone/bind", h.handleBindPhoneCredential)
	mux.HandleFunc("POST /owner/credentials/carrier-phone/bind", h.handleBindCarrierPhoneCredential)
	mux.HandleFunc("DELETE /owner/credentials/{credType}", h.handleUnbindCredential)

	// Contact Discovery (paths owned by user_profile service.yaml: /owner/...)
	mux.HandleFunc("POST /owner/contact-discovery", h.handleInitiateContactDiscovery)
	mux.HandleFunc("GET /owner/contact-discovery/latest", h.handleGetLatestContactDiscovery)
	mux.HandleFunc("DELETE /owner/contact-discovery/{id}", h.handleDismissContactDiscovery)

	return h.enforceAccountSecurity(mux)
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
	if actorID := userIDFromHeader(r); actorID == "" || actorID != userID {
		writeForbidden(w, r, "owner profile is private")
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
	var wire updateProfileWire
	if _, err := decodePersonaCommandBody(r, &wire); err != nil {
		writeInvalidArg(w, r, "invalid request body: "+err.Error())
		return
	}
	if writeHandleReadonlyIfRequested(w, r, wire.UserHandle) {
		return
	}
	profile, err := h.profile.UpdateProfile(r.Context(), userID, wire.command())
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
	credentials, err := h.credentialQueries.ListCredentials(r.Context())
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	profileCredentials := make([]application.ProfileCredentialView, 0, len(credentials))
	for _, credential := range credentials {
		profileCredentials = append(profileCredentials, application.ProfileCredentialView{
			CredentialType: credential.CredentialType,
			DisplayLabel:   credential.DisplayLabel,
			IsActive:       credential.IsActive,
		})
	}
	view, err := h.profile.GetEditSnapshot(
		r.Context(),
		userID,
		profileCredentials,
	)
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

		rel, _ := h.relationship.GetRelationship(r.Context(), viewerID, relationTargetID)
		isBlocked, _ := h.relationship.CheckBlocked(r.Context(), viewerID, relationTargetID)
		isBlockedBy, _ := h.relationship.CheckBlocked(r.Context(), relationTargetID, viewerID)
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
			reltelemetry.Collector().RecordCapabilityMismatch()
			usertelemetry.RolloutCollector().RecordAttributionMismatch()
		}
		item["relationshipCapability"] = capability
		item["chatAvailable"] = capability["canOpenConversation"] == true
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": ""})
}

// 最近搜索（RecentSearchState）已按 metadata 归属 search 域，
// 由 search-service 承载 /search/recent 系列路由；user-service 不再持有该状态。

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
	result, err := h.relationship.Follow(
		r.Context(),
		followerID,
		followeeID,
		anyString(body["source"]),
		anyString(body["clientRequestId"]),
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
	result, err := h.relationship.Unfollow(
		r.Context(),
		followerID,
		followeeID,
		anyString(body["clientRequestId"]),
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

func (h *UserHandler) handleListFollowing(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	defer func() {
		reltelemetry.Collector().RecordListLatency(time.Since(startedAt))
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
		parseListSearchQuery(r),
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
		reltelemetry.Collector().RecordListLatency(time.Since(startedAt))
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
		parseListSearchQuery(r),
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
	rel, err := h.relationship.GetRelationship(r.Context(), userID, targetID)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, newRelationshipViewResponse(userID, targetID, rel))
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
	result, err := h.relationship.Block(
		r.Context(),
		blockerID,
		blockedID,
		h.commandIdempotencyKey(r),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"targetSubAccountId": blockedID,
		"blocked":            true,
		"idempotentReplay":   result.IdempotentReplay || !result.Changed,
		"updatedAt":          relationshipUpdatedAt(result),
	})
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
	result, err := h.relationship.Unblock(
		r.Context(),
		blockerID,
		blockedID,
		h.commandIdempotencyKey(r),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"targetSubAccountId": blockedID,
		"blocked":            false,
		"idempotentReplay":   result.IdempotentReplay || !result.Changed,
		"updatedAt":          relationshipUpdatedAt(result),
	})
}

func (h *UserHandler) handleListBlocked(w http.ResponseWriter, r *http.Request) {
	blockerID, err := h.resolveActorSubAccountID(r.Context(), r, "")
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

func (h *UserHandler) resolveActorSubAccountID(
	ctx context.Context,
	r *http.Request,
	explicitActorID string,
) (string, error) {
	userID := strings.TrimSpace(userIDFromHeader(r))
	if userID == "" {
		return "", generated.AppErrorFromInvalidArgument("X-Client-User-Id header required")
	}
	trustedPersonaID := subAccountIDFromHeader(r)
	actorID := strings.TrimSpace(explicitActorID)
	if actorID != "" && actorID != trustedPersonaID {
		// metadata ownership_policy: actor_self —— body 里的 actorSubAccountId
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
	activeContext, err := h.subAccount.GetActivePersonaContextView(ctx, userID)
	if err != nil {
		return "", err
	}
	actorID = strings.TrimSpace(anyString(activeContext["subAccountId"]))
	if actorID == "" {
		return "", generated.AppErrorFromInvalidArgument("active persona context is required")
	}
	return actorID, nil
}

func (h *UserHandler) verifyActorPersonaOwnership(
	ctx context.Context,
	accountID, actorID string,
) (string, error) {
	if h.subAccount == nil {
		return "", generated.AppErrorFromInternalError("sub-account service is unavailable")
	}
	persona, err := h.subAccount.GetSubAccountProfile(ctx, actorID)
	if err != nil {
		return "", err
	}
	if persona == nil || persona.UserID != accountID {
		return "", generated.AppErrorFromRelationshipActorForbidden(
			"actor persona does not belong to the authenticated account",
		)
	}
	if strings.EqualFold(strings.TrimSpace(persona.Status), "retired") {
		return "", generated.AppErrorFromRelationshipActorForbidden(
			"retired persona cannot act",
		)
	}
	return persona.SubAccountID, nil
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
			// SIT2：粉丝/关注行下发 viewer→row 完整关系能力位，
			// 端侧行内关注/回关/私信按钮不再从 relationState 单字段猜测。
			// blocked/blockedBy 行已在上方 CheckBlocked 过滤，此处恒为 false。
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
	var wire createPersonaWire
	payload, err := decodePersonaCommandBody(r, &wire)
	if err != nil {
		writeInvalidArg(w, r, "invalid body: "+err.Error())
		return
	}
	if writeHandleReadonlyIfRequested(w, r, wire.UserHandle) {
		return
	}
	meta, err := personaCommandMeta(r, payload)
	if err != nil {
		writeInvalidArg(w, r, err.Error())
		return
	}
	p, err := h.subAccount.CreateSubAccount(r.Context(), userID, application.CreatePersonaCommand{
		DisplayName:    wire.DisplayName,
		AvatarURL:      wire.AvatarURL,
		IsolationLevel: wire.IsolationLevel,
		PurposeHint:    wire.PurposeHint,
	}, meta)
	if err != nil {
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
	var wire updatePersonaWire
	payload, err := decodePersonaCommandBody(r, &wire)
	if err != nil {
		writeInvalidArg(w, r, "invalid body: "+err.Error())
		return
	}
	if writeHandleReadonlyIfRequested(w, r, wire.UserHandle) {
		return
	}
	meta, err := personaCommandMeta(r, payload)
	if err != nil {
		writeInvalidArg(w, r, err.Error())
		return
	}
	p, err := h.subAccount.UpdatePersona(r.Context(), userID, personaID, application.UpdatePersonaCommand{
		DisplayName:    wire.DisplayName,
		Phone:          wire.Phone,
		Email:          wire.Email,
		AvatarURL:      wire.AvatarURL,
		BackgroundURL:  wire.BackgroundURL,
		IsolationLevel: wire.IsolationLevel,
		PurposeHint:    wire.PurposeHint,
		Sync: application.PersonaProfileSyncOptions{
			ApplyScope:    wire.ApplyScope,
			SyncTargetIDs: wire.SyncTargetIDs,
			FieldsMask:    wire.FieldsMask,
		},
	}, meta)
	if err != nil {
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
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
	var wire profileSyncWire
	payload, err := decodePersonaCommandBody(r, &wire)
	if err != nil {
		writeInvalidArg(w, r, "invalid body: "+err.Error())
		return
	}
	meta, err := personaCommandMeta(r, payload)
	if err != nil {
		writeInvalidArg(w, r, err.Error())
		return
	}
	result, err := h.subAccount.ApplyPersonaProfileSync(r.Context(), userID, personaID,
		application.PersonaProfileSyncOptions{
			ApplyScope:    wire.ApplyScope,
			SyncTargetIDs: wire.SyncTargetIDs,
			FieldsMask:    wire.FieldsMask,
		}, meta)
	if err != nil {
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
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

func (h *UserHandler) handleRetirePersona(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	personaID := r.PathValue("subAccountId")
	meta, err := personaCommandMeta(r, nil)
	if err != nil {
		writeInvalidArg(w, r, err.Error())
		return
	}
	view, err := h.subAccount.RetirePersona(r.Context(), userID, personaID, meta)
	if err != nil {
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
			return
		}
		if hasUserErrorCode(err, "USER.SUB_ACCOUNT.primary_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.last_sub_account") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.active_guard") ||
			hasUserErrorCode(err, "USER.SUB_ACCOUNT.retired_guard") {
			writeHTTPError(w, r, err)
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *UserHandler) handleActivatePersona(w http.ResponseWriter, r *http.Request) {
	personaID := r.PathValue("subAccountId")
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id header required")
		return
	}
	meta, err := personaCommandMeta(r, nil)
	if err != nil {
		writeInvalidArg(w, r, err.Error())
		return
	}
	err = h.subAccount.ActivateSubAccount(r.Context(), userID, personaID, meta)
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
	challengeID := strings.TrimSpace(anyString(body["challengeId"]))
	status := strings.TrimSpace(anyString(body["status"]))
	if requestID == "" {
		writeInvalidArg(w, r, "requestId required")
		return
	}
	if status == "" {
		writeInvalidArg(w, r, "status required")
		return
	}
	if challengeID == "" {
		writeInvalidArg(w, r, "challengeId required")
		return
	}
	if err := h.auth.HandleOtpDeliveryCallback(
		r.Context(),
		challengeID,
		status,
	); err != nil {
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
	h.handleFederatedLogin(w, r, h.wechatLogin, "wechatCode")
}

func (h *UserHandler) handleLoginWithAlipay(w http.ResponseWriter, r *http.Request) {
	h.handleFederatedLogin(w, r, h.alipayLogin, "alipayAuthCode")
}

func (h *UserHandler) handleLoginWithQq(w http.ResponseWriter, r *http.Request) {
	h.handleFederatedLogin(w, r, h.qqLogin, "qqAuthCode")
}

func (h *UserHandler) handleFederatedLogin(
	w http.ResponseWriter,
	r *http.Request,
	login *application.FederatedLoginFacade,
	primaryField string,
) {
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
	if login == nil {
		writeHTTPError(
			w,
			r,
			generated.AppErrorFromSocialProviderUnavailable(
				"federated identity capability unavailable",
			),
		)
		return
	}
	result, err := login.Login(r.Context(), authCode, deviceID, platform, appVersion)
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
	creds, err := h.credentialQueries.ListCredentials(r.Context())
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"credentials": creds})
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
	result, err := h.auth.BindPhoneCredential(
		r.Context(),
		userID,
		phone,
		otpCode,
		label,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
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
	carrierToken, _ := body["carrierToken"].(string)
	deviceID, _ := body["deviceId"].(string)
	platform, _ := body["platform"].(string)
	label, _ := body["displayLabel"].(string)
	result, err := h.auth.BindCarrierPhoneCredential(
		r.Context(),
		userID,
		carrierToken,
		deviceID,
		platform,
		label,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *UserHandler) handleUnbindCredential(w http.ResponseWriter, r *http.Request) {
	userID := userIDFromHeader(r)
	if userID == "" {
		writeInvalidArg(w, r, "X-Client-User-Id required")
		return
	}
	credType := r.PathValue("credType")
	result, err := h.auth.UnbindCredential(r.Context(), userID, credType)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

// --- SubAccounts ---

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
