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
	personas, err := h.persona.ListPersonas(r.Context(), userID)
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
	summary, err := h.persona.GetPersonaManagementSummary(r.Context(), userID)
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
	view, err := h.persona.GetActivePersonaContextView(r.Context(), userID)
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
	p, err := h.persona.CreatePersona(r.Context(), userID, application.CreatePersonaCommand{
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
	personaID := r.PathValue("personaId")
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
	p, err := h.persona.UpdatePersona(r.Context(), userID, personaID, application.UpdatePersonaCommand{
		DisplayName:    wire.DisplayName,
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
		if hasUserErrorCode(err, "USER.PERSONA.not_found") {
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
	personaID := r.PathValue("personaId")
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
	result, err := h.persona.ApplyPersonaProfileSync(r.Context(), userID, personaID,
		application.PersonaProfileSyncOptions{
			ApplyScope:    wire.ApplyScope,
			SyncTargetIDs: wire.SyncTargetIDs,
			FieldsMask:    wire.FieldsMask,
		}, meta)
	if err != nil {
		if hasUserErrorCode(err, "USER.PERSONA.not_found") {
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
	personaID := r.PathValue("personaId")
	guard, err := h.persona.GetPersonaLifecycleGuard(r.Context(), userID, personaID)
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
	personaID := r.PathValue("personaId")
	meta, err := personaCommandMeta(r, nil)
	if err != nil {
		writeInvalidArg(w, r, err.Error())
		return
	}
	view, err := h.persona.RetirePersona(r.Context(), userID, personaID, meta)
	if err != nil {
		if hasUserErrorCode(err, "USER.PERSONA.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
			return
		}
		if hasUserErrorCode(err, "USER.PERSONA.primary_guard") ||
			hasUserErrorCode(err, "USER.PERSONA.last_persona") ||
			hasUserErrorCode(err, "USER.PERSONA.active_guard") ||
			hasUserErrorCode(err, "USER.PERSONA.retired_guard") {
			writeHTTPError(w, r, err)
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *UserHandler) handleActivatePersona(w http.ResponseWriter, r *http.Request) {
	personaID := r.PathValue("personaId")
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
	err = h.persona.ActivatePersona(r.Context(), userID, personaID, meta)
	if err != nil {
		if hasUserErrorCode(err, "USER.PERSONA.not_found") {
			writeNotFound(w, r, userErrorDebugMessage(err))
			return
		}
		if hasUserErrorCode(err, "USER.PERSONA.retired_guard") {
			writeHTTPError(w, r, err)
			return
		}
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}
