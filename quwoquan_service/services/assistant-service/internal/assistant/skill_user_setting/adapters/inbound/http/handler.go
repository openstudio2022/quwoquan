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
	settingerrors "quwoquan_service/services/assistant-service/generated/assistant/skill_user_setting"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
)

const (
	listOperation = "assistant.skill_user_setting.ListSkillUserSettings"
	getOperation  = "assistant.skill_user_setting.GetSkillUserSetting"
	putOperation  = "assistant.skill_user_setting.PutSkillUserSetting"
)

type Handler struct {
	commands *application.CommandFacade
	queries  *application.QueryFacade
}

func NewHandler(commands *application.CommandFacade, queries *application.QueryFacade) *Handler {
	return &Handler{commands: commands, queries: queries}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	list := mustOperationDescriptor(listOperation)
	get := mustOperationDescriptor(getOperation)
	put := mustOperationDescriptor(putOperation)
	mux.HandleFunc(list.Method+" "+list.PathTemplate, handler.handleList)
	mux.HandleFunc(get.Method+" "+get.PathTemplate, handler.handleGet)
	mux.HandleFunc(put.Method+" "+put.PathTemplate, handler.handlePut)
}

func (handler *Handler) handleList(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	limit, err := parseListLimit(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	settings, err := handler.queries.List(request.Context(), accountID, limit)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{"items": settings})
}

func (handler *Handler) handleGet(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	setting, err := handler.queries.Get(
		request.Context(),
		accountID,
		strings.TrimSpace(request.PathValue("skillId")),
	)
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, setting)
}

func (handler *Handler) handlePut(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	var body struct {
		Status                    string          `json:"status"`
		ConfigurationData         json.RawMessage `json:"configurationData"`
		ConfigurationSchemaDigest string          `json:"configurationSchemaDigest"`
		MemoryPolicy              string          `json:"memoryPolicy"`
		ConnectorConnectionRefs   []string        `json:"connectorConnectionRefs"`
		ExpectedRevision          int64           `json:"expectedRevision"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 96<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(
			writer,
			request,
			settingerrors.AppErrorFromSkillSettingInvalidArgument(err.Error()),
		)
		return
	}
	result, err := handler.commands.Put(request.Context(), model.PutInput{
		AccountID:                 accountID,
		SkillID:                   strings.TrimSpace(request.PathValue("skillId")),
		Status:                    body.Status,
		ConfigurationData:         body.ConfigurationData,
		ConfigurationSchemaDigest: body.ConfigurationSchemaDigest,
		MemoryPolicy:              body.MemoryPolicy,
		ConnectorConnectionRefs:   body.ConnectorConnectionRefs,
		ExpectedRevision:          body.ExpectedRevision,
		IdempotencyKey:            strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeHTTPError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"setting":  result.Setting,
		"changed":  result.Changed,
		"replayed": result.Replayed,
	})
}

func requireAccount(request *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if ok && strings.TrimSpace(principal.Actor.AccountID) != "" {
		return strings.TrimSpace(principal.Actor.AccountID), nil
	}
	return "", settingerrors.AppErrorFromSkillSettingUnauthorized(
		"SkillUserSetting requires a verified account principal",
	)
}

func parseListLimit(request *http.Request) (int, error) {
	values, present := request.URL.Query()["limit"]
	if !present {
		return 64, nil
	}
	if len(values) != 1 {
		return 0, settingerrors.AppErrorFromSkillSettingInvalidArgument(
			"limit must be provided at most once",
		)
	}
	limit, err := strconv.Atoi(strings.TrimSpace(values[0]))
	if err != nil || limit <= 0 || limit > 100 {
		return 0, settingerrors.AppErrorFromSkillSettingInvalidArgument(
			"limit must be an integer between 1 and 100",
		)
	}
	return limit, nil
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, model.ErrNotFound):
		return settingerrors.AppErrorFromSkillSettingNotFound(err.Error())
	case errors.Is(err, model.ErrInvalidArgument):
		return settingerrors.AppErrorFromSkillSettingInvalidArgument(err.Error())
	case errors.Is(err, model.ErrSchemaMismatch):
		return settingerrors.AppErrorFromSkillSettingSchemaDigestMismatch(err.Error())
	case errors.Is(err, model.ErrRevisionConflict):
		return settingerrors.AppErrorFromSkillSettingRevisionConflict(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return settingerrors.AppErrorFromSkillSettingIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrPackageUnavailable):
		return settingerrors.AppErrorFromSkillSettingPackageUnavailable(err.Error())
	case errors.Is(err, model.ErrStorageUnavailable):
		return settingerrors.AppErrorFromSkillSettingStorageUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return settingerrors.AppErrorFromSkillSettingStorageUnavailable(err.Error())
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

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
