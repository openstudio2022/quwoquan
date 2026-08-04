package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	datacontrolerrors "quwoquan_service/services/assistant-service/generated/assistant/skill_data_control_request"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
)

const (
	createOperation  = "assistant.skill_data_control_request.CreateSkillDataControlRequest"
	confirmOperation = "assistant.skill_data_control_request.ConfirmSkillDataControlRequest"
	getOperation     = "assistant.skill_data_control_request.GetSkillDataControlRequest"
	maxBodyBytes     = 64 << 10
)

type Handler struct {
	service *application.Service
}

func NewHandler(service *application.Service) *Handler {
	return &Handler{service: service}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	create := mustOperationDescriptor(createOperation)
	confirm := mustOperationDescriptor(confirmOperation)
	get := mustOperationDescriptor(getOperation)
	mux.HandleFunc(create.Method+" "+create.PathTemplate, handler.create)
	mux.HandleFunc(confirm.Method+" "+confirm.PathTemplate, handler.confirm)
	mux.HandleFunc(get.Method+" "+get.PathTemplate, handler.get)
}

func (handler *Handler) create(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body struct {
		RequestedActions []string `json:"requestedActions"`
	}
	if err := decode(writer, request, &body); err != nil {
		writeError(
			writer,
			request,
			datacontrolerrors.AppErrorFromSkillDataControlInvalidArgument(err.Error()),
		)
		return
	}
	result, err := handler.service.Create(
		request.Context(),
		accountID,
		strings.TrimSpace(request.PathValue("skillId")),
		body.RequestedActions,
		strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	)
	if err != nil {
		writeError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func (handler *Handler) confirm(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	var body struct {
		ExpectedRevision int64 `json:"expectedRevision"`
		Confirmed        *bool `json:"confirmed"`
	}
	if err := decode(writer, request, &body); err != nil || body.Confirmed == nil {
		if err == nil {
			err = errors.New("confirmed is required")
		}
		writeError(
			writer,
			request,
			datacontrolerrors.AppErrorFromSkillDataControlInvalidArgument(err.Error()),
		)
		return
	}
	result, err := handler.service.Confirm(
		request.Context(),
		accountID,
		strings.TrimSpace(request.PathValue("requestId")),
		body.ExpectedRevision,
		*body.Confirmed,
		strings.TrimSpace(request.Header.Get("Idempotency-Key")),
	)
	if err != nil {
		writeError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func (handler *Handler) get(writer http.ResponseWriter, request *http.Request) {
	accountID, err := requireAccount(request)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	result, err := handler.service.Get(
		request.Context(), accountID, strings.TrimSpace(request.PathValue("requestId")),
	)
	if err != nil {
		writeError(writer, request, mapDomainError(err))
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func decode(writer http.ResponseWriter, request *http.Request, value any) error {
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, maxBodyBytes))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(value); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("request body must contain exactly one JSON value")
		}
		return err
	}
	return nil
}

func requireAccount(request *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if ok && strings.TrimSpace(principal.Actor.AccountID) != "" {
		return strings.TrimSpace(principal.Actor.AccountID), nil
	}
	return "", datacontrolerrors.AppErrorFromSkillDataControlUnauthorized(
		"verified account principal is required",
	)
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalidArgument):
		return datacontrolerrors.AppErrorFromSkillDataControlInvalidArgument(err.Error())
	case errors.Is(err, model.ErrNotFound):
		return datacontrolerrors.AppErrorFromSkillDataControlNotFound(err.Error())
	case errors.Is(err, model.ErrRevisionConflict):
		return datacontrolerrors.AppErrorFromSkillDataControlRevisionConflict(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return datacontrolerrors.AppErrorFromSkillDataControlIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrStorageUnavailable):
		return datacontrolerrors.AppErrorFromSkillDataControlUnavailable(err.Error())
	default:
		var appError *rterr.AppError
		if errors.As(err, &appError) {
			return err
		}
		return datacontrolerrors.AppErrorFromSkillDataControlUnavailable(err.Error())
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
