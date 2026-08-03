package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	entryerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_entry_view"
	entryapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/application"
)

type Handler struct{ queries *entryapplication.QueryFacade }

func NewHandler(queries *entryapplication.QueryFacade) *Handler {
	return &Handler{queries: queries}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /assistant/entry", h.getEntry)
}

func (h *Handler) getEntry(w http.ResponseWriter, r *http.Request) {
	accountID, err := accountID(r)
	if err != nil {
		rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	view, err := h.queries.GetEntry(
		r.Context(), accountID,
		strings.TrimSpace(r.URL.Query().Get("pageType")),
		strings.TrimSpace(r.URL.Query().Get("objectId")),
	)
	if err != nil {
		if errors.Is(err, entryapplication.ErrInvalidPageContext) {
			err = entryerrors.AppErrorFromEntryInvalidArgument(err.Error())
		} else {
			err = entryerrors.AppErrorFromEntryProjectionUnavailable(err.Error())
		}
		rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(view)
}

func accountID(r *http.Request) (string, error) {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		if value := strings.TrimSpace(principal.Actor.AccountID); value != "" {
			return value, nil
		}
		if value := strings.TrimSpace(principal.Subject); value != "" {
			return value, nil
		}
	}
	return "", entryerrors.AppErrorFromEntryUnauthorized("trusted account principal is required")
}
