package http

import (
	"net/http"

	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

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
