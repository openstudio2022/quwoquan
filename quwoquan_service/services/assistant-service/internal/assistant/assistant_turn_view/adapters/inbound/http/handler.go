package http

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	turnviewerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_turn_view"
	turnviewapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/application"
)

type Handler struct {
	queries *turnviewapplication.QueryFacade
}

func NewHandler(queries *turnviewapplication.QueryFacade) *Handler {
	if queries == nil {
		panic("assistant turn view query facade is required")
	}
	return &Handler{queries: queries}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	if mux == nil {
		panic("assistant turn view HTTP mux is required")
	}
	mux.HandleFunc(
		"GET /assistant/sessions/{sessionId}/turns",
		handler.handleListSessionTurns,
	)
}

func (handler *Handler) handleListSessionTurns(
	writer http.ResponseWriter,
	request *http.Request,
) {
	userID, err := requireIdentifiedUser(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	view, err := handler.queries.ListSessionTurns(
		request.Context(),
		userID,
		request.PathValue("sessionId"),
		parseLimit(request),
		request.URL.Query().Get("cursor"),
	)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(writer).Encode(view)
}

func requireIdentifiedUser(request *http.Request) (string, error) {
	if principal, ok := rtauth.PrincipalFromContext(request.Context()); ok {
		if subject := strings.TrimSpace(principal.Subject); subject != "" {
			return subject, nil
		}
	}
	if userID := strings.TrimSpace(request.Header.Get("X-Client-User-Id")); userID != "" {
		return userID, nil
	}
	return "", turnviewerrors.AppErrorFromTurnViewUnauthorized(
		"assistant turn view requires an identified persona",
	)
}

func parseLimit(request *http.Request) int {
	raw := strings.TrimSpace(request.URL.Query().Get("limit"))
	if raw == "" {
		return 20
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 {
		return 20
	}
	return limit
}

func writeError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
