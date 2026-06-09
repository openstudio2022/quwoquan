package httpadapter

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	rerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/application"
	"quwoquan_service/services/integration-service/internal/generated"
)

const (
	externalRequestsPath = "/v1/integrations/external-requests"
)

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
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "请求体格式错误", err.Error()),
			rerrors.HTTPWriteOptionsFromRequest(r),
		)
		return
	}
	expiresAt := time.Now().UTC().Add(5 * time.Minute)
	if raw := strings.TrimSpace(anyString(body["expiresAt"])); raw != "" {
		if parsed, err := time.Parse(time.RFC3339, raw); err == nil {
			expiresAt = parsed.UTC()
		}
	}
	requestID := strings.TrimSpace(anyString(body["requestId"]))
	if requestID == "" {
		requestID = "ext-" + time.Now().UTC().Format("20060102150405.000000000")
	}
	payload := stringMap(body["payload"])
	request := reliabletask.ExternalInteractionRequest{
		RequestID:      requestID,
		Operation:      strings.TrimSpace(anyString(body["operation"])),
		Tenant:         nonEmpty(anyString(body["tenant"]), "quwoquan"),
		Env:            nonEmpty(anyString(body["env"]), "alpha"),
		IdempotencyKey: nonEmpty(anyString(body["idempotencyKey"]), requestID),
		CallbackURL:    strings.TrimSpace(anyString(body["callbackUrl"])),
		CallbackEvent:  strings.TrimSpace(anyString(body["callbackEvent"])),
		PayloadRef:     strings.TrimSpace(anyString(body["payloadRef"])),
		PayloadDigest:  strings.TrimSpace(anyString(body["payloadDigest"])),
		Sensitivity:    nonEmpty(anyString(body["sensitivity"]), "private"),
		ExpiresAt:      expiresAt,
		Payload:        payload,
	}
	accepted, err := h.external.Submit(r.Context(), request)
	if err != nil {
		rerrors.WriteHTTPError(
			w,
			rerrors.NewInvalidArgument(rerrors.ModuleIntegration, "外部请求参数不完整", err.Error()),
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
	trimmed := strings.TrimPrefix(path, externalRequestsPath+"/")
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
