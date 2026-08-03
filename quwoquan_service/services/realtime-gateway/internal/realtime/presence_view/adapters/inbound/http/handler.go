package http

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/realtime-gateway/generated/realtime/connection"
	presenceapp "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/application"
)

type Handler struct{ queries *presenceapp.QueryFacade }

func NewHandler(queries *presenceapp.QueryFacade) *Handler {
	if queries == nil {
		panic("presence http handler requires query facade")
	}
	return &Handler{queries: queries}
}

func (handler *Handler) Routes(mux *http.ServeMux) {
	mux.HandleFunc(
		"GET /internal/realtime/personas/{personaId}/presence",
		handler.handleGetPersonaPresence,
	)
}

func (handler *Handler) handleGetPersonaPresence(
	w http.ResponseWriter,
	r *http.Request,
) {
	personaID := strings.TrimSpace(r.PathValue("personaId"))
	if personaID == "" {
		writeError(w, r, generated.AppErrorFromInternalError("personaId is required"))
		return
	}
	view, err := handler.queries.GetPersonaPresence(
		r.Context(), personaID, time.Now().UTC(),
	)
	if err != nil {
		writeError(w, r, generated.AppErrorFromInternalError(
			"realtime presence query failed",
		))
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(view)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
