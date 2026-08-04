package http

import (
	"net/http"
	"strings"

	generated "quwoquan_service/services/user-service/generated/account/user_account"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	usertelemetry "quwoquan_service/services/user-service/internal/account/user_account/domain/user/telemetry"
	reltelemetry "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/telemetry"
)

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
	payload, err := decodePersonaCommandBody(r, &wire)
	if err != nil {
		writeInvalidArg(w, r, "invalid request body: "+err.Error())
		return
	}
	meta, err := personaCommandMeta(r, payload)
	if err != nil {
		writeInvalidArg(w, r, err.Error())
		return
	}
	if writeHandleReadonlyIfRequested(w, r, wire.UserHandle) {
		return
	}
	profile, err := h.profile.UpdateProfile(
		r.Context(),
		userID,
		wire.command(),
		meta,
	)
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
	view, err := h.profile.GetEditSnapshot(r.Context(), userID, profileCredentials)
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
	view, err := h.persona.GetMeProfileView(r.Context(), userID)
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
	var request pullUserSyncRequest
	if err := decodeStrictJSON(r, &request); err != nil {
		writeInvalidArg(w, r, "invalid request body")
		return
	}
	afterSeq := int64(0)
	if request.AfterSeq != nil {
		afterSeq = *request.AfterSeq
	}
	limit := 200
	if request.Limit != nil {
		limit = *request.Limit
	}
	if afterSeq < 0 || limit < 1 || limit > 500 {
		writeInvalidArg(w, r, "invalid sync cursor or limit")
		return
	}
	resp, err := h.profile.PullSync(r.Context(), userID, afterSeq, limit)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

type pullUserSyncRequest struct {
	AfterSeq *int64 `json:"afterSeq"`
	Limit    *int   `json:"limit"`
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
	if activeViewerID, resolveErr := h.resolveActorPersonaID(r.Context(), r, ""); resolveErr == nil && activeViewerID != "" {
		viewerID = activeViewerID
	}
	for _, item := range items {
		targetPersonaID := strings.TrimSpace(anyString(item["personaId"]))
		rel, _ := h.relationship.GetRelationship(r.Context(), viewerID, targetPersonaID)
		isBlocked, _ := h.relationship.CheckBlocked(r.Context(), viewerID, targetPersonaID)
		isBlockedBy, _ := h.relationship.CheckBlocked(r.Context(), targetPersonaID, viewerID)
		capability := h.relationshipCapabilityView(
			r.Context(), viewerID, targetPersonaID, rel, isBlocked, isBlockedBy,
		)
		if item["chatAvailable"] != nil && item["chatAvailable"] != capability.CanOpenConversation {
			reltelemetry.Collector().RecordCapabilityMismatch()
			usertelemetry.RolloutCollector().RecordAttributionMismatch()
		}
		item["relationshipCapability"] = capability
		item["chatAvailable"] = capability.CanOpenConversation
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "cursor": ""})
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
