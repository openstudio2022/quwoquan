package http

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	preferenceerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_preference"
	preferenceapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/application"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
)

const maxRequestBodyBytes = 1 << 20

type Handler struct {
	commands *preferenceapplication.CommandFacade
	queries  *preferenceapplication.QueryFacade
}

type setPreferenceRequest struct {
	Scope           string `json:"scope"`
	SessionID       string `json:"sessionId"`
	Kind            string `json:"kind"`
	Value           string `json:"value"`
	SourceType      string `json:"sourceType"`
	SourceSessionID string `json:"sourceSessionId"`
	Confirmed       bool   `json:"confirmed"`
}

func NewHandler(
	commands *preferenceapplication.CommandFacade,
	queries *preferenceapplication.QueryFacade,
) *Handler {
	return &Handler{commands: commands, queries: queries}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /assistant/preferences", h.set)
	mux.HandleFunc("GET /assistant/preferences", h.list)
	mux.HandleFunc("POST /assistant/preferences/{preferenceId}/revoke", h.revoke)
	mux.HandleFunc("POST /assistant/preferences/{preferenceId}/restore", h.restore)
}

func (h *Handler) set(w http.ResponseWriter, r *http.Request) {
	accountID, err := preferenceAccountID(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	var input setPreferenceRequest
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxRequestBodyBytes))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		writeError(w, r, preferenceapplication.InvalidArgumentError(err.Error()))
		return
	}
	preference, err := h.commands.SetPreference(r.Context(), preferenceapplication.SetPreferenceCommand{
		UserID: accountID, Scope: input.Scope, SessionID: input.SessionID,
		Kind: input.Kind, Value: input.Value, SourceType: input.SourceType,
		SourceSessionID: input.SourceSessionID, Confirmed: input.Confirmed,
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, preference)
}

func (h *Handler) list(w http.ResponseWriter, r *http.Request) {
	accountID, err := preferenceAccountID(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	view, err := h.queries.ListPreferences(r.Context(), preferenceapplication.ListPreferencesQuery{
		UserID: accountID, Scope: strings.TrimSpace(r.URL.Query().Get("scope")),
		SessionID: strings.TrimSpace(r.URL.Query().Get("sessionId")),
		Status:    strings.TrimSpace(r.URL.Query().Get("status")), Limit: 100,
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) revoke(w http.ResponseWriter, r *http.Request) {
	h.updateStatus(w, r, h.commands.RevokePreference)
}

func (h *Handler) restore(w http.ResponseWriter, r *http.Request) {
	h.updateStatus(w, r, h.commands.RestorePreference)
}

func (h *Handler) updateStatus(
	w http.ResponseWriter,
	r *http.Request,
	update func(context.Context, string, string) (preferencemodel.AssistantPreference, error),
) {
	accountID, err := preferenceAccountID(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	preference, err := update(r.Context(), accountID, r.PathValue("preferenceId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, preference)
}

func preferenceAccountID(r *http.Request) (string, error) {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		if value := strings.TrimSpace(principal.Actor.AccountID); value != "" {
			return value, nil
		}
		if value := strings.TrimSpace(principal.Subject); value != "" {
			return value, nil
		}
	}
	return "", preferenceerrors.AppErrorFromPreferenceUnauthorized(
		"trusted account principal is required",
	)
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
