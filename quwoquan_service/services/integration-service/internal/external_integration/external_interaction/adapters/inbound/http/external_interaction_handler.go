package httpadapter

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	rerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

// submitExternalRequestWire 是 SubmitExternalInteractionRequest 的强类型
// wire 契约（ExternalInteractionRequest entity），未知字段 fail closed。
type submitExternalRequestWire struct {
	RequestID      string            `json:"requestId"`
	Operation      string            `json:"operation"`
	Tenant         string            `json:"tenant"`
	Env            string            `json:"env"`
	IdempotencyKey string            `json:"idempotencyKey"`
	PayloadRef     string            `json:"payloadRef"`
	PayloadDigest  string            `json:"payloadDigest"`
	Sensitivity    string            `json:"sensitivity"`
	ExpiresAt      string            `json:"expiresAt"`
	Payload        map[string]string `json:"payload"`
}

func (h *Handler) handleSubmitExternalRequest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "方法不支持", "only POST"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	if h.external == nil {
		rerrors.WriteHTTPError(
			w,
			generated.AppErrorFromInternalError("external interaction service unavailable"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	var body submitExternalRequestWire
	decoder := json.NewDecoder(io.LimitReader(r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		rerrors.WriteHTTPError(
			w,
			generated.AppErrorFromInvalidExternalRequest("request body must be a typed external interaction request: "+err.Error()),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		rerrors.WriteHTTPError(
			w,
			generated.AppErrorFromInvalidExternalRequest("request body contains trailing JSON"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	operation := strings.TrimSpace(body.Operation)
	requestID := strings.TrimSpace(body.RequestID)
	idempotencyKey := strings.TrimSpace(body.IdempotencyKey)
	if operation == "" || requestID == "" || idempotencyKey == "" {
		rerrors.WriteHTTPError(
			w,
			generated.AppErrorFromInvalidExternalRequest("operation, requestId and idempotencyKey are required"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	expiresAt := time.Now().UTC().Add(5 * time.Minute)
	if raw := strings.TrimSpace(body.ExpiresAt); raw != "" {
		parsed, err := time.Parse(time.RFC3339, raw)
		if err != nil {
			rerrors.WriteHTTPError(
				w,
				generated.AppErrorFromInvalidExternalRequest("expiresAt must be RFC3339"),
				rerrors.HTTPWriteOptionsFromRequest(r),
			)
			return
		}
		expiresAt = parsed.UTC()
	}
	payload := make(map[string]string, len(body.Payload))
	for key, value := range body.Payload {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			payload[key] = trimmed
		}
	}
	request := reliabletask.ExternalInteractionRequest{
		RequestID:      requestID,
		Operation:      operation,
		Tenant:         nonEmpty(body.Tenant, "quwoquan"),
		Env:            nonEmpty(body.Env, "alpha"),
		IdempotencyKey: idempotencyKey,
		PayloadRef:     strings.TrimSpace(body.PayloadRef),
		PayloadDigest:  strings.TrimSpace(body.PayloadDigest),
		Sensitivity:    nonEmpty(body.Sensitivity, "private"),
		ExpiresAt:      expiresAt,
		Payload:        payload,
	}
	accepted, err := h.external.Submit(r.Context(), request)
	if err != nil {
		rerrors.WriteHTTPError(
			w,
			mapExternalSubmitError(err),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{
		"requestId":  accepted.RequestID,
		"status":     accepted.Status,
		"acceptedAt": accepted.AcceptedAt.Format(time.RFC3339),
	})
}

// mapExternalSubmitError 把应用层受理失败映射为稳定错误码：不支持的
// operation 与参数问题分别对应 unsupported_operation / invalid_external_request。
func mapExternalSubmitError(err error) error {
	var appError *rerrors.AppError
	if errors.As(err, &appError) {
		return appError
	}
	message := err.Error()
	if strings.Contains(message, "disabled") || strings.Contains(message, "not supported") {
		return generated.AppErrorFromUnsupportedOperation(message)
	}
	return generated.AppErrorFromInvalidExternalRequest(message)
}

func (h *Handler) handleGetExternalRequest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "方法不支持", "only GET"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	requestID := strings.TrimPrefix(r.URL.Path, generated.ExternalRequestsPath+"/")
	state, found, err := h.external.GetRequest(r.Context(), requestID)
	if err != nil {
		rerrors.WriteHTTPError(w, err, rerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	if !found {
		rerrors.WriteHTTPError(
			w,
			generated.AppErrorFromInvalidExternalRequest("external interaction request not found"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	writeJSON(w, http.StatusOK, state)
}

func (h *Handler) handleExternalAttempts(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "方法不支持", "only GET"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	requestID := requestIDFromAttemptsPath(r.URL.Path)
	items, err := h.external.ListAttempts(r.Context(), requestID)
	if err != nil {
		rerrors.WriteHTTPError(w, err, rerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *Handler) handleExternalDeadLetters(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "方法不支持", "only GET"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	requestID := strings.TrimSpace(r.URL.Query().Get("requestId"))
	items, err := h.external.ListDeadLetters(r.Context(), requestID)
	if err != nil {
		rerrors.WriteHTTPError(w, err, rerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	if items == nil {
		items = []application.ExternalDeadLetter{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *Handler) handleRecoverExternalDeadLetter(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "方法不支持", "only POST"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	body := map[string]any{}
	_ = json.NewDecoder(r.Body).Decode(&body)
	taskID := strings.TrimSpace(anyString(body["taskId"]))
	if taskID == "" {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "taskId required", "missing taskId"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	if err := h.external.RecoverDeadTask(r.Context(), taskID); err != nil {
		rerrors.WriteHTTPError(w, err, rerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"taskId": taskID, "recovered": true})
}

func (h *Handler) handleExternalMetricsSnapshot(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "方法不支持", "only GET"),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	snapshot, err := h.external.Metrics(r.Context())
	if err != nil {
		rerrors.WriteHTTPError(w, err, rerrors.HTTPWriteOptionsFromRequest(r))
		return
	}
	writeJSON(w, http.StatusOK, snapshot)
}

func requestIDFromAttemptsPath(path string) string {
	trimmed := strings.TrimPrefix(path, generated.ExternalRequestsPath+"/")
	return strings.TrimSuffix(trimmed, "/attempts")
}

func anyString(value any) string {
	switch v := value.(type) {
	case string:
		return v
	case nil:
		return ""
	default:
		return strings.TrimSpace(fmt.Sprint(v))
	}
}

func stringMap(value any) map[string]string {
	out := map[string]string{}
	raw, ok := value.(map[string]any)
	if !ok {
		return out
	}
	for key, val := range raw {
		if s := strings.TrimSpace(anyString(val)); s != "" {
			out[key] = s
		}
	}
	return out
}

func nonEmpty(value string, fallback string) string {
	if strings.TrimSpace(value) != "" {
		return strings.TrimSpace(value)
	}
	return fallback
}
