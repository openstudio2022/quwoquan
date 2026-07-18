package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/product-ops-service/internal/application"
	productopsgenerated "quwoquan_service/services/product-ops-service/internal/generated"
)

const maxTelemetryRequestBytes = 128 << 10

func (s *productService) handleReportEventBatch(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	result := "rejected"
	eventCount := 0
	defer func() {
		recordTelemetryIngestMetrics(result, eventCount, time.Since(startedAt))
	}()
	if _, ok := verifiedTelemetryActorHash(r); !ok {
		result = "unauthorized"
		writeRuntimeError(w, r, http.StatusUnauthorized, "请先登录", "verified telemetry actor is required")
		return
	}
	raw, err := io.ReadAll(io.LimitReader(r.Body, maxTelemetryRequestBytes+1))
	if err != nil || len(raw) == 0 || len(raw) > maxTelemetryRequestBytes {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", "request body exceeds telemetry limit")
		return
	}
	canonical, err := canonicalJSON(raw)
	if err != nil {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", err.Error())
		return
	}
	digest := sha256.Sum256(canonical)
	batchKey := hex.EncodeToString(digest[:])
	if !strings.EqualFold(strings.TrimSpace(r.Header.Get("Idempotency-Key")), batchKey) {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromIdempotencyKeyInvalid("idempotency digest mismatch"))
		return
	}
	var body struct {
		Events []application.EventRecordInput `json:"events"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", err.Error())
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", "request body must contain exactly one JSON object")
		return
	}
	eventCount = len(body.Events)
	ack, err := s.telemetry.ReportEventBatch(r.Context(), batchKey, body.Events)
	if err != nil {
		switch {
		case errors.Is(err, application.ErrInvalidEventBatch):
			result = "invalid"
			writeEventAppError(w, r, productopsgenerated.AppErrorFromEventBatchInvalid(err.Error()))
		case errors.Is(err, application.ErrBatchInProgress):
			result = "unavailable"
			writeEventAppError(w, r, productopsgenerated.AppErrorFromLogstoreUnavailable(err.Error()))
		default:
			result = "unavailable"
			writeEventAppError(w, r, productopsgenerated.AppErrorFromLogstoreUnavailable(err.Error()))
		}
		return
	}
	if ack.DuplicateBatch {
		result = "duplicate"
	} else {
		result = "accepted"
	}
	writeJSON(w, http.StatusOK, ack)
}

func (s *productService) handleGetEventSummary(w http.ResponseWriter, r *http.Request) {
	from, err := parseOptionalTime(r.URL.Query().Get("from"))
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
	}
	to, err := parseOptionalTime(r.URL.Query().Get("to"))
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
	}
	query := application.EventSummaryQuery{
		LogType:      strings.TrimSpace(r.URL.Query().Get("logType")),
		EventType:    strings.TrimSpace(r.URL.Query().Get("eventType")),
		PageName:     strings.TrimSpace(r.URL.Query().Get("pageName")),
		AppVersion:   strings.TrimSpace(r.URL.Query().Get("appVersion")),
		NetworkClass: strings.TrimSpace(r.URL.Query().Get("networkClass")),
		ErrorCode:    strings.TrimSpace(r.URL.Query().Get("errorCode")),
		From:         from,
		To:           to,
	}
	out, err := s.telemetry.GetEventSummary(r.Context(), query)
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *productService) handleGetEventDrilldown(w http.ResponseWriter, r *http.Request) {
	limit := 50
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil {
			writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid("limit must be an integer"))
			return
		}
		limit = parsed
	}
	from, err := parseOptionalTime(r.URL.Query().Get("from"))
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
	}
	to, err := parseOptionalTime(r.URL.Query().Get("to"))
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
	}
	revealRequested := strings.EqualFold(r.URL.Query().Get("revealSession"), "true")
	revealAllowed := revealRequested && hasTelemetrySensitivePermission(r)
	if revealRequested && !revealAllowed {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromEventDrilldownForbidden("sensitive session reveal permission is required"))
		return
	}
	query := application.EventDrilldownQuery{
		LogType:       strings.TrimSpace(r.URL.Query().Get("logType")),
		EventType:     strings.TrimSpace(r.URL.Query().Get("eventType")),
		PageName:      strings.TrimSpace(r.URL.Query().Get("pageName")),
		AppVersion:    strings.TrimSpace(r.URL.Query().Get("appVersion")),
		NetworkClass:  strings.TrimSpace(r.URL.Query().Get("networkClass")),
		ErrorCode:     strings.TrimSpace(r.URL.Query().Get("errorCode")),
		SessionID:     strings.TrimSpace(r.URL.Query().Get("sessionId")),
		From:          from,
		To:            to,
		Limit:         limit,
		RevealSession: revealAllowed,
	}
	out, err := s.telemetry.GetEventDrilldown(r.Context(), query)
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
	}
	if revealAllowed {
		principal, _ := rtauth.PrincipalFromContext(r.Context())
		log.Printf("audit telemetry_sensitive_drilldown actor=%s from=%s to=%s rows=%d", principal.Actor.AccountID, out.ActualFrom, out.ActualTo, len(out.Items))
	}
	writeJSON(w, http.StatusOK, out)
}

func canonicalJSON(raw []byte) ([]byte, error) {
	var value any
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return nil, errors.New("request body must contain exactly one JSON value")
	}
	return json.Marshal(value)
}

func hasTelemetrySensitivePermission(r *http.Request) bool {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return false
	}
	for _, permission := range principal.Permissions {
		if permission == "ops.event.drilldown.sensitive" {
			return true
		}
	}
	for _, role := range principal.Roles {
		if role == "ops_admin" || role == "security_auditor" {
			return true
		}
	}
	return false
}

func writeEventAppError(w http.ResponseWriter, r *http.Request, appError *rterr.AppError) {
	rterr.WriteHTTPError(w, appError, rterr.HTTPWriteOptionsFromRequest(r))
}

func parseOptionalTime(raw string) (time.Time, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return time.Time{}, nil
	}
	if parsed, err := time.Parse(time.RFC3339Nano, trimmed); err == nil {
		return parsed, nil
	}
	if parsed, err := time.Parse("2006-01-02", trimmed); err == nil {
		return parsed, nil
	}
	return time.Time{}, errors.New("time must be RFC3339 or YYYY-MM-DD")
}
