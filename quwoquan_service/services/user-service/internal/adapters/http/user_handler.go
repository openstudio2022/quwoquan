package http

import (
	"net/http"
	"strings"

	"quwoquan_service/services/user-service/internal/application"
)

type UserHandler struct {
	profile  *application.ProfileService
	follow   *application.FollowService
	block    *application.BlockService
	persona  *application.PersonaService
	work     *application.WorkService
	lifeItem *application.LifeItemService
	setting  *application.SettingService
}

func NewUserHandler(
	profile *application.ProfileService,
	follow *application.FollowService,
	block *application.BlockService,
	persona *application.PersonaService,
	work *application.WorkService,
	lifeItem *application.LifeItemService,
	setting *application.SettingService,
) *UserHandler {
	return &UserHandler{
		profile:  profile,
		follow:   follow,
		block:    block,
		persona:  persona,
		work:     work,
		lifeItem: lifeItem,
		setting:  setting,
	}
}

func (h *UserHandler) Routes() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)

	mux.HandleFunc("GET /v1/user/profile/{userId}", h.handleGetProfile)
	mux.HandleFunc("PATCH /v1/user/profile", h.handleUpdateProfile)

	mux.HandleFunc("POST /v1/user/follow/{targetUserId}", h.handleFollow)
	mux.HandleFunc("DELETE /v1/user/follow/{targetUserId}", h.handleUnfollow)
	mux.HandleFunc("GET /v1/user/{userId}/following", h.handleListFollowing)
	mux.HandleFunc("GET /v1/user/{userId}/followers", h.handleListFollowers)
	mux.HandleFunc("GET /v1/user/{userId}/relationship", h.handleGetRelationship)

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
