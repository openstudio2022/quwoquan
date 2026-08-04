package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	activityerrors "quwoquan_service/services/assistant-service/generated/assistant/skill_activity_view"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/domain/model"
)

const listOperation = "assistant.skill_activity_view.ListSkillActivities"

type Handler struct {
	queries *application.QueryFacade
}

func NewHandler(queries *application.QueryFacade) *Handler {
	return &Handler{queries: queries}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	descriptor := mustOperationDescriptor(listOperation)
	mux.HandleFunc(descriptor.Method+" "+descriptor.PathTemplate, handler.list)
}

func (handler *Handler) list(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	limit := 32
	if raw := strings.TrimSpace(request.URL.Query().Get("limit")); raw != "" {
		parsed, parseErr := strconv.Atoi(raw)
		if parseErr != nil {
			writeError(
				writer,
				request,
				activityerrors.AppErrorFromSkillActivityInvalidArgument(parseErr.Error()),
			)
			return
		}
		limit = parsed
	}
	if handler == nil || handler.queries == nil {
		writeError(
			writer,
			request,
			activityerrors.AppErrorFromSkillActivityUnavailable("query facade is not configured"),
		)
		return
	}
	result, err := handler.queries.List(
		request.Context(),
		accountID,
		strings.TrimSpace(request.PathValue("skillId")),
		strings.TrimSpace(request.URL.Query().Get("cursor")),
		limit,
	)
	if err != nil {
		writeError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func requireAccount(request *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if ok && strings.TrimSpace(principal.Actor.AccountID) != "" {
		return strings.TrimSpace(principal.Actor.AccountID), nil
	}
	return "", activityerrors.AppErrorFromSkillActivityUnauthorized(
		"verified account principal is required",
	)
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return activityerrors.AppErrorFromSkillActivityInvalidArgument(err.Error())
	case errors.Is(err, model.ErrUnavailable):
		return activityerrors.AppErrorFromSkillActivityUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return activityerrors.AppErrorFromSkillActivityUnavailable(err.Error())
	}
}

func mustOperationDescriptor(canonicalOperationID string) rtauth.OperationSecurityDescriptor {
	for _, descriptor := range operationsecurity.ForDomain("assistant") {
		if descriptor.CanonicalOperationID == canonicalOperationID {
			return descriptor
		}
	}
	panic("missing generated operation descriptor: " + canonicalOperationID)
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(value)
}

func writeError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
