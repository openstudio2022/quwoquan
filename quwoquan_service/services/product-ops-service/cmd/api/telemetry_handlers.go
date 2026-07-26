package main

import (
	"bytes"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	productopsgenerated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
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
		recordAppExperienceEvents(body.Events)
	}
	writeJSON(w, http.StatusOK, ack)
}

// handleReportRuntimeLogBatch 是 App 诊断日志的独立入口。它不复用产品事件
// schema，避免 runtime/exception/access 信号退化为无级别埋点字段。
func (s *productService) handleReportRuntimeLogBatch(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	result := "rejected"
	recordCount := 0
	defer func() {
		recordTelemetryIngestMetrics(result, recordCount, time.Since(startedAt))
	}()
	if s.runtimeLogs == nil {
		result = "unavailable"
		writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogstoreUnavailable("runtime diagnostic ingestion is not configured"))
		return
	}
	actorHash, ok := verifiedTelemetryActorHash(r)
	if !ok {
		result = "unauthorized"
		writeRuntimeError(w, r, http.StatusUnauthorized, "请先登录", "verified runtime diagnostic actor is required")
		return
	}
	raw, err := io.ReadAll(io.LimitReader(r.Body, maxTelemetryRequestBytes+1))
	if err != nil || len(raw) == 0 || len(raw) > maxTelemetryRequestBytes {
		result = "invalid"
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", "request body exceeds runtime diagnostic limit")
		return
	}
	canonical, err := canonicalJSON(raw)
	if err != nil {
		result = "invalid"
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", err.Error())
		return
	}
	digest := sha256.Sum256(canonical)
	batchKey := hex.EncodeToString(digest[:])
	if !strings.EqualFold(strings.TrimSpace(r.Header.Get("Idempotency-Key")), batchKey) {
		result = "invalid"
		writeEventAppError(w, r, productopsgenerated.AppErrorFromIdempotencyKeyInvalid("runtime log idempotency digest mismatch"))
		return
	}
	var body struct {
		Records []map[string]any `json:"records"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		result = "invalid"
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", err.Error())
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		result = "invalid"
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", "request body must contain exactly one JSON object")
		return
	}
	recordCount = len(body.Records)
	// 服务端把已验证 actorHash 注入 correlation，作为"按用户查日志"的唯一
	// 可信用户维度；端侧自报的 actorHash 一律被覆盖，禁止伪造他人维度。
	for _, record := range body.Records {
		correlation, _ := record["correlation"].(map[string]any)
		if correlation == nil {
			correlation = map[string]any{}
		}
		correlation["actorHash"] = actorHash
		record["correlation"] = correlation
	}
	ack, err := s.runtimeLogs.ReportRuntimeLogBatch(r.Context(), batchKey, body.Records)
	if err != nil {
		switch {
		case errors.Is(err, application.ErrInvalidRuntimeLogBatch):
			result = "invalid"
			writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogBatchInvalid(err.Error()))
		case errors.Is(err, application.ErrBatchInProgress):
			result = "unavailable"
			writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogstoreUnavailable(err.Error()))
		default:
			result = "unavailable"
			writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogstoreUnavailable(err.Error()))
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

// handleInternalRuntimeLogIngest 是云侧服务日志上云的内部通道：各服务的
// RuntimeLogExportWriter 已在源头完成 canonical 校验与扁平化，这里以机器凭据
// fail-closed 接收，并经与 App 相同的 RuntimeLogService 幂等账本落库。app sourceType 禁止走本通道，
// 防止绕过端侧已验证 actor 的公共 ingest。
func (s *productService) handleInternalRuntimeLogIngest(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	result := "rejected"
	recordCount := 0
	defer func() {
		recordTelemetryIngestMetrics(result, recordCount, time.Since(startedAt))
	}()
	if s.runtimeLogs == nil || s.runtimeLogStore == nil {
		result = "unavailable"
		writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogstoreUnavailable("runtime diagnostic ingestion is not configured"))
		return
	}
	expectedToken := strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN"))
	provided := strings.TrimSpace(r.Header.Get("X-Runtime-Log-Ingest-Token"))
	if expectedToken == "" || provided == "" ||
		subtle.ConstantTimeCompare([]byte(expectedToken), []byte(provided)) != 1 {
		result = "unauthorized"
		writeRuntimeError(w, r, http.StatusUnauthorized, "请求未授权", "runtime log ingest token is required")
		return
	}
	raw, err := io.ReadAll(io.LimitReader(r.Body, maxTelemetryRequestBytes+1))
	if err != nil || len(raw) == 0 || len(raw) > maxTelemetryRequestBytes {
		result = "invalid"
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", "request body exceeds runtime diagnostic limit")
		return
	}
	digest := sha256.Sum256(raw)
	batchKey := hex.EncodeToString(digest[:])
	if !strings.EqualFold(strings.TrimSpace(r.Header.Get("Idempotency-Key")), batchKey) {
		result = "invalid"
		writeEventAppError(w, r, productopsgenerated.AppErrorFromIdempotencyKeyInvalid("runtime log idempotency digest mismatch"))
		return
	}
	var body struct {
		Records []map[string]string `json:"records"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		result = "invalid"
		writeRuntimeError(w, r, http.StatusBadRequest, "请求体无效", err.Error())
		return
	}
	recordCount = len(body.Records)
	if recordCount == 0 || recordCount > 50 {
		result = "invalid"
		writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogBatchInvalid("record count must be 1..50"))
		return
	}
	for index, fields := range body.Records {
		if fields["resourceSourceType"] == "app" {
			result = "invalid"
			writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogBatchInvalid(
				"record["+strconv.Itoa(index)+"] app records must use the verified public ingest"))
			return
		}
	}
	ack, err := s.runtimeLogs.ReportTrustedRuntimeLogBatch(r.Context(), batchKey, body.Records)
	if err != nil {
		if errors.Is(err, application.ErrInvalidRuntimeLogBatch) {
			result = "invalid"
			writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogBatchInvalid(err.Error()))
			return
		}
		result = "unavailable"
		writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogstoreUnavailable(err.Error()))
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
		Result:       strings.TrimSpace(r.URL.Query().Get("result")),
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

func (s *productService) handleGetRtcMediaQoeSummary(
	w http.ResponseWriter,
	r *http.Request,
) {
	out, err := s.telemetry.GetRtcMediaQoeSummary(r.Context())
	if err != nil {
		writeEventAppError(
			w,
			r,
			productopsgenerated.AppErrorFromLogstoreUnavailable(err.Error()),
		)
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
		Result:        strings.TrimSpace(r.URL.Query().Get("result")),
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

func (s *productService) handleGetRuntimeLogSummary(w http.ResponseWriter, r *http.Request) {
	if s.runtimeLogs == nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogstoreUnavailable("runtime diagnostic query is not configured"))
		return
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
	out, err := s.runtimeLogs.GetRuntimeLogSummary(r.Context(), application.RuntimeLogSummaryQuery{
		Signal:      strings.TrimSpace(r.URL.Query().Get("signal")),
		Severity:    strings.TrimSpace(r.URL.Query().Get("severity")),
		ErrorCode:   strings.TrimSpace(r.URL.Query().Get("errorCode")),
		Fingerprint: strings.TrimSpace(r.URL.Query().Get("fingerprint")),
		SourceType:  strings.TrimSpace(r.URL.Query().Get("sourceType")),
		Service:     strings.TrimSpace(r.URL.Query().Get("service")),
		AppVersion:  strings.TrimSpace(r.URL.Query().Get("appVersion")),
		From:        from,
		To:          to,
	})
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, out)
}

func (s *productService) handleGetRuntimeLogDrilldown(w http.ResponseWriter, r *http.Request) {
	if s.runtimeLogs == nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromRuntimeLogstoreUnavailable("runtime diagnostic query is not configured"))
		return
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
	limit := 50
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		limit, err = strconv.Atoi(raw)
		if err != nil {
			writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid("limit must be an integer"))
			return
		}
	}
	revealRequested := strings.EqualFold(r.URL.Query().Get("revealCorrelation"), "true")
	revealAllowed := revealRequested && hasRuntimeLogSensitivePermission(r)
	if revealRequested && !revealAllowed {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromEventDrilldownForbidden("sensitive runtime correlation permission is required"))
		return
	}
	actorHash := strings.TrimSpace(r.URL.Query().Get("actorHash"))
	if actorHash != "" && !hasRuntimeLogSensitivePermission(r) {
		// 按用户维度检索日志是合规敏感操作，与 revealCorrelation 同一权限门。
		writeEventAppError(w, r, productopsgenerated.AppErrorFromEventDrilldownForbidden("sensitive runtime correlation permission is required for actor queries"))
		return
	}
	out, err := s.runtimeLogs.GetRuntimeLogDrilldown(r.Context(), application.RuntimeLogDrilldownQuery{
		Signal:            strings.TrimSpace(r.URL.Query().Get("signal")),
		Severity:          strings.TrimSpace(r.URL.Query().Get("severity")),
		ErrorCode:         strings.TrimSpace(r.URL.Query().Get("errorCode")),
		Fingerprint:       strings.TrimSpace(r.URL.Query().Get("fingerprint")),
		SourceType:        strings.TrimSpace(r.URL.Query().Get("sourceType")),
		Service:           strings.TrimSpace(r.URL.Query().Get("service")),
		AppVersion:        strings.TrimSpace(r.URL.Query().Get("appVersion")),
		ActorHash:         actorHash,
		MessageContains:   strings.TrimSpace(r.URL.Query().Get("messageContains")),
		From:              from,
		To:                to,
		Limit:             limit,
		RevealCorrelation: revealAllowed,
	})
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid(err.Error()))
		return
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

func hasRuntimeLogSensitivePermission(r *http.Request) bool {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return false
	}
	for _, permission := range principal.Permissions {
		if permission == "ops.runtime_log.drilldown.sensitive" {
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
