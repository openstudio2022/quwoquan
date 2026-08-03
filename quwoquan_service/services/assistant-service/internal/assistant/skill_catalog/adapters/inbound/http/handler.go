package http

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	catalogerrors "quwoquan_service/services/assistant-service/generated/assistant/skill_catalog"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
)

const listSkillsOperation = "assistant.skill_catalog.ListSkills"
const getSkillCatalogItemOperation = "assistant.skill_catalog.GetSkillCatalogItem"

type Handler struct {
	queries *application.QueryService
}

func NewHandler(queries *application.QueryService) *Handler {
	return &Handler{queries: queries}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	detailDescriptor := mustOperationDescriptor(getSkillCatalogItemOperation)
	mux.HandleFunc(
		detailDescriptor.Method+" "+detailDescriptor.PathTemplate,
		handler.handleGetSkillCatalogItem,
	)
	descriptor := mustOperationDescriptor(listSkillsOperation)
	mux.HandleFunc(
		descriptor.Method+" "+descriptor.PathTemplate,
		handler.handleListSkills,
	)
}

func (handler *Handler) handleGetSkillCatalogItem(
	writer http.ResponseWriter,
	request *http.Request,
) {
	accountID, err := requireVerifiedAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	if handler == nil || handler.queries == nil {
		writeHTTPError(
			writer,
			request,
			catalogerrors.AppErrorFromSkillCatalogUnavailable(
				"skill catalog query service is not configured",
			),
		)
		return
	}
	view, err := handler.queries.GetSkillCatalogItem(
		request.Context(),
		application.GetSkillCatalogItemQuery{
			AccountID: accountID,
			SkillID:   request.PathValue("skillId"),
		},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, view)
}

func (handler *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)
	return mux
}

func (handler *Handler) handleListSkills(
	writer http.ResponseWriter,
	request *http.Request,
) {
	accountID, err := requireVerifiedAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	if handler == nil || handler.queries == nil {
		writeHTTPError(
			writer,
			request,
			catalogerrors.AppErrorFromSkillCatalogUnavailable(
				"skill catalog query service is not configured",
			),
		)
		return
	}
	limit, err := parseLimit(request, 64)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	view, err := handler.queries.ListSkills(
		request.Context(),
		application.ListSkillsQuery{
			AccountID: accountID,
			Limit:     limit,
		},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, view)
}

func requireVerifiedAccount(request *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if ok && strings.TrimSpace(principal.Actor.AccountID) != "" {
		return strings.TrimSpace(principal.Actor.AccountID), nil
	}
	return "", catalogerrors.AppErrorFromSkillCatalogUnauthorized(
		"skill catalog requires a verified account principal",
	)
}

func parseLimit(request *http.Request, fallback int) (int, error) {
	values, present := request.URL.Query()["limit"]
	if !present {
		return fallback, nil
	}
	if len(values) != 1 {
		return 0, catalogerrors.AppErrorFromSkillCatalogInvalidArgument(
			"limit must be provided at most once",
		)
	}
	raw := strings.TrimSpace(values[0])
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 || limit > 100 {
		return 0, catalogerrors.AppErrorFromSkillCatalogInvalidArgument(
			"limit must be an integer between 1 and 100",
		)
	}
	return limit, nil
}

func mustOperationDescriptor(
	canonicalOperationID string,
) rtauth.OperationSecurityDescriptor {
	for _, descriptor := range operationsecurity.ForDomain("assistant") {
		if descriptor.CanonicalOperationID == canonicalOperationID {
			return descriptor
		}
	}
	panic("missing generated operation descriptor: " + canonicalOperationID)
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
