package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	pageerrors "quwoquan_service/services/assistant-service/generated/assistant/page_context"
	pageapplication "quwoquan_service/services/assistant-service/internal/assistant/page_context/application"
	pagemodel "quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
)

type Handler struct{ facade *pageapplication.Facade }

type reportCommand struct {
	ContextSnapshot pagemodel.Snapshot `json:"contextSnapshot"`
}

func NewHandler(facade *pageapplication.Facade) *Handler { return &Handler{facade: facade} }

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /assistant/page-context", h.report)
}

func (h *Handler) report(w http.ResponseWriter, r *http.Request) {
	accountID, personaID, err := pageIdentity(r)
	if err != nil {
		rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	var input reportCommand
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		err = pageerrors.AppErrorFromPageContextInvalidArgument(err.Error())
		rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	receipt, err := h.facade.Report(r.Context(), accountID, personaID, input.ContextSnapshot)
	if err != nil {
		if errors.Is(err, pageapplication.ErrStoreUnavailable) {
			err = pageerrors.AppErrorFromPageContextUnavailable(err.Error())
		} else {
			err = pageerrors.AppErrorFromPageContextInvalidArgument(err.Error())
		}
		rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(receipt)
}

func pageIdentity(r *http.Request) (string, string, error) {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		accountID := strings.TrimSpace(principal.Actor.AccountID)
		if accountID == "" {
			accountID = strings.TrimSpace(principal.Subject)
		}
		personaID := strings.TrimSpace(principal.Actor.PersonaID)
		if accountID != "" && personaID != "" {
			return accountID, personaID, nil
		}
	}
	return "", "", pageerrors.AppErrorFromPageContextUnauthorized("trusted account and persona principal are required")
}
