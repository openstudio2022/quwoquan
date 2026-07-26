package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	policyerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_policy_release"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
)

const stagePolicyReleaseOperation = "assistant.assistant_policy_release.StageAssistantPolicyRelease"

type Handler struct {
	service *application.Service
}

func NewHandler(service *application.Service) *Handler {
	return &Handler{service: service}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	descriptor := mustOperationDescriptor(stagePolicyReleaseOperation)
	mux.HandleFunc(
		descriptor.Method+" "+descriptor.PathTemplate,
		handler.handleStage,
	)
}

func (handler *Handler) handleStage(writer http.ResponseWriter, request *http.Request) {
	if handler == nil || handler.service == nil {
		writeHTTPError(
			writer,
			request,
			policyerrors.AppErrorFromPolicyReleaseStorageUnavailable(
				"policy release service is not configured",
			),
		)
		return
	}
	var input model.Release
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		writeHTTPError(
			writer,
			request,
			policyerrors.AppErrorFromPolicyReleaseInvalid(err.Error()),
		)
		return
	}
	result, err := handler.service.Stage(
		request.Context(),
		strings.TrimSpace(request.Header.Get("Idempotency-Key")),
		input,
	)
	if err != nil {
		writeHTTPError(writer, request, mapPolicyReleaseError(err))
		return
	}
	writeJSON(writer, http.StatusOK, result.Release)
}

func mapPolicyReleaseError(err error) error {
	switch {
	case errors.Is(err, model.ErrDigestMismatch):
		return policyerrors.AppErrorFromPolicyReleaseDigestMismatch(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return policyerrors.AppErrorFromPolicyReleaseIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrInvalidArgument):
		return policyerrors.AppErrorFromPolicyReleaseInvalid(err.Error())
	default:
		return policyerrors.AppErrorFromPolicyReleaseStorageUnavailable(err.Error())
	}
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
