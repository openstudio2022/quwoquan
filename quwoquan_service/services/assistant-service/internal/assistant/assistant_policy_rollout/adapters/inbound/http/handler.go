package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	rollouterrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_policy_rollout"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
)

const (
	activatePolicyRolloutOperation = "assistant.assistant_policy_rollout.ActivateAssistantPolicyRollout"
	rollbackPolicyRolloutOperation = "assistant.assistant_policy_rollout.RollbackAssistantPolicyRollout"
)

type Handler struct {
	service *application.Service
}

func NewHandler(service *application.Service) *Handler {
	return &Handler{service: service}
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	for _, canonicalOperationID := range []string{
		activatePolicyRolloutOperation,
		rollbackPolicyRolloutOperation,
	} {
		descriptor := mustOperationDescriptor(canonicalOperationID)
		switch canonicalOperationID {
		case activatePolicyRolloutOperation:
			mux.HandleFunc(
				descriptor.Method+" "+descriptor.PathTemplate,
				handler.handleActivate,
			)
		case rollbackPolicyRolloutOperation:
			mux.HandleFunc(
				descriptor.Method+" "+descriptor.PathTemplate,
				handler.handleRollback,
			)
		}
	}
}

func (handler *Handler) handleActivate(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler == nil || handler.service == nil {
		writeHTTPError(
			writer,
			request,
			rollouterrors.AppErrorFromPolicyRolloutStorageUnavailable(
				"policy rollout service is not configured",
			),
		)
		return
	}
	var input application.ActivateInput
	if err := decodeJSON(writer, request, &input); err != nil {
		writeHTTPError(
			writer,
			request,
			rollouterrors.AppErrorFromPolicyRolloutInvalid(err.Error()),
		)
		return
	}
	policyID := strings.TrimSpace(request.PathValue("policyId"))
	if bodyPolicyID := strings.TrimSpace(input.PolicyID); bodyPolicyID != "" &&
		bodyPolicyID != policyID {
		writeHTTPError(
			writer,
			request,
			rollouterrors.AppErrorFromPolicyRolloutInvalid(
				"body policyId differs from route policyId",
			),
		)
		return
	}
	actorID, ok := verifiedActorID(request)
	if !ok {
		writeHTTPError(
			writer,
			request,
			rollouterrors.AppErrorFromPolicyRolloutInvalid(
				"verified service actor is required",
			),
		)
		return
	}
	input.PolicyID = policyID
	input.ActivatedBy = actorID
	result, err := handler.service.Activate(
		request.Context(),
		strings.TrimSpace(request.Header.Get("Idempotency-Key")),
		input,
	)
	if err != nil {
		writeHTTPError(writer, request, mapPolicyRolloutError(err))
		return
	}
	writeJSON(writer, http.StatusOK, result.Rollout)
}

func (handler *Handler) handleRollback(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler == nil || handler.service == nil {
		writeHTTPError(
			writer,
			request,
			rollouterrors.AppErrorFromPolicyRolloutStorageUnavailable(
				"policy rollout service is not configured",
			),
		)
		return
	}
	var input application.RollbackInput
	if err := decodeJSON(writer, request, &input); err != nil {
		writeHTTPError(
			writer,
			request,
			rollouterrors.AppErrorFromPolicyRolloutInvalid(err.Error()),
		)
		return
	}
	policyID := strings.TrimSpace(request.PathValue("policyId"))
	if bodyPolicyID := strings.TrimSpace(input.PolicyID); bodyPolicyID != "" &&
		bodyPolicyID != policyID {
		writeHTTPError(
			writer,
			request,
			rollouterrors.AppErrorFromPolicyRolloutInvalid(
				"body policyId differs from route policyId",
			),
		)
		return
	}
	actorID, ok := verifiedActorID(request)
	if !ok {
		writeHTTPError(
			writer,
			request,
			rollouterrors.AppErrorFromPolicyRolloutInvalid(
				"verified service actor is required",
			),
		)
		return
	}
	input.PolicyID = policyID
	input.ActivatedBy = actorID
	result, err := handler.service.Rollback(
		request.Context(),
		strings.TrimSpace(request.Header.Get("Idempotency-Key")),
		input,
	)
	if err != nil {
		writeHTTPError(writer, request, mapPolicyRolloutError(err))
		return
	}
	writeJSON(writer, http.StatusOK, result.Rollout)
}

func mapPolicyRolloutError(err error) error {
	switch {
	case errors.Is(err, model.ErrReleaseNotFound):
		return rollouterrors.AppErrorFromPolicyRolloutReleaseNotFound(err.Error())
	case errors.Is(err, model.ErrRolloutNotFound):
		return rollouterrors.AppErrorFromPolicyRolloutNotFound(err.Error())
	case errors.Is(err, model.ErrNoPreviousMapping):
		return rollouterrors.AppErrorFromPolicyRolloutNoPreviousMapping(err.Error())
	case errors.Is(err, model.ErrRevisionConflict):
		return rollouterrors.AppErrorFromPolicyRolloutRevisionConflict(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return rollouterrors.AppErrorFromPolicyRolloutIdempotencyConflict(err.Error())
	case errors.Is(err, model.ErrInvalidArgument):
		return rollouterrors.AppErrorFromPolicyRolloutInvalid(err.Error())
	default:
		return rollouterrors.AppErrorFromPolicyRolloutStorageUnavailable(err.Error())
	}
}

func verifiedActorID(request *http.Request) (string, bool) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	actorID := strings.TrimSpace(principal.Actor.AccountID)
	return actorID, ok && actorID != ""
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

func decodeJSON(
	writer http.ResponseWriter,
	request *http.Request,
	target any,
) error {
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 1<<20))
	decoder.DisallowUnknownFields()
	return decoder.Decode(target)
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
