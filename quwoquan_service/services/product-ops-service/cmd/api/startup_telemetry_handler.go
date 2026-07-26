package main

import (
	"encoding/json"
	"io"
	"net"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	productopsgenerated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
)

const (
	startupTelemetryProofHeader  = "X-Qwq-Startup-Proof"
	startupTelemetryMaxBatch     = 32
	startupTelemetryMaxPerMinute = 120
	startupTelemetryMaxRateKeys  = 2048
)

var (
	startupTelemetryIdentifierPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{16,128}$`)
	startupTelemetryProofPattern      = regexp.MustCompile(`^[A-Za-z0-9_-]{24,192}$`)
	startupTelemetryAppVersionPattern = regexp.MustCompile(
		`^v?[0-9]+(?:\.[0-9]+){1,3}(?:[-.][A-Za-z0-9]+)*$`,
	)
	startupTelemetryLimiter = newStartupTelemetryLimiter()
)

var allowedStartupTelemetryPhases = map[string]struct{}{
	"native_pre_flutter":       {},
	"dart_bootstrap":           {},
	"configuration_validation": {},
	"flutter_first_frame":      {},
	"router_preload":           {},
	"router_ready":             {},
	"router_failure":           {},
	"shell_first_paint":        {},
	"home_feed_first_usable":   {},
	"terminal":                 {},
	"recovery":                 {},
}

// 所有会进入 Prometheus label 的值必须是有限 allowlist；不能接受“看似枚举”的任意
// 字符串，否则匿名入口可制造高基数指标。
var allowedStartupTelemetryOutcomes = map[string]struct{}{
	"observed":                    {},
	"started":                     {},
	"validated":                   {},
	"skipped":                     {},
	"painted":                     {},
	"ready":                       {},
	"retry":                       {},
	"failed":                      {},
	"entered":                     {},
	"degraded":                    {},
	"usable":                      {},
	"success":                     {},
	"recovery":                    {},
	"shown":                       {},
	"bootstrap_failure":           {},
	"native_first_frame_timeout":  {},
	"startup_deadline":            {},
	"bootstrap_error":             {},
	"unhandled_rejection":         {},
	"pagehide_before_first_frame": {},
	"journal_drop":                {},
	"unknown":                     {},
}

var allowedStartupTelemetryPlatforms = map[string]struct{}{
	"android": {},
	"ios":     {},
	"ohos":    {},
	"web":     {},
	"desktop": {},
	"unknown": {},
}

var allowedStartupTelemetryRuntimeEnvs = map[string]struct{}{
	"alpha":   {},
	"beta":    {},
	"gamma":   {},
	"prod":    {},
	"unknown": {},
}

var allowedStartupTelemetryNetworkClasses = map[string]struct{}{
	"":         {},
	"offline":  {},
	"wifi":     {},
	"cellular": {},
	"ethernet": {},
	"unknown":  {},
}

var allowedStartupTelemetryRecoverySurfaces = map[string]struct{}{
	"":                 {},
	"flutter_recovery": {},
	"safe_recovery":    {},
	"native_recovery":  {},
}

var allowedStartupTelemetryFailureSources = map[string]struct{}{
	"":                        {},
	"bootstrap":               {},
	"router":                  {},
	"startup_deadline":        {},
	"native_watchdog":         {},
	"web_error":               {},
	"web_unhandled_rejection": {},
	"web_pagehide":            {},
}

var allowedStartupTelemetryFailureCodes = map[string]struct{}{
	"": {},
	"OPS.SYSTEM.startup_configuration_invalid":      {},
	"OPS.SYSTEM.startup_initialization_failed":      {},
	"OPS.SYSTEM.startup_router_unavailable":         {},
	"OPS.SYSTEM.startup_native_first_frame_timeout": {},
}

var allowedStartupTelemetryDeadlineOrigins = map[string]struct{}{
	"":                {},
	"fallbackDart":    {},
	"android_process": {},
	"ios_process":     {},
	"web_bootstrap":   {},
}

type startupTelemetryBatchRequest struct {
	Events []startupTelemetryEventInput `json:"events"`
}

// startupTelemetryEventInput 是匿名入口的固定 schema。故意不复用通用 EventRecord
// 的大 payload，确保请求体无法携带账户、内容、原始异常或堆栈。
type startupTelemetryEventInput struct {
	EventID         string `json:"eventId"`
	AttemptID       string `json:"attemptId"`
	Sequence        int    `json:"sequence"`
	Phase           string `json:"phase"`
	PhaseDurationMs int    `json:"phaseDurationMs"`
	ElapsedMs       int    `json:"elapsedMs"`
	Outcome         string `json:"outcome"`
	OccurredAt      string `json:"occurredAt"`
	Platform        string `json:"platform"`
	RuntimeEnv      string `json:"runtimeEnv"`
	AppVersion      string `json:"appVersion,omitempty"`
	NetworkClass    string `json:"networkClass,omitempty"`
	RecoverySurface string `json:"recoverySurface,omitempty"`
	FailureCode     string `json:"failureCode,omitempty"`
	FailureSource   string `json:"failureSource,omitempty"`
	DeadlineOrigin  string `json:"deadlineOrigin,omitempty"`
}

type startupTelemetryRateWindow struct {
	StartedAt time.Time
	Count     int
}

type startupTelemetryRateLimiter struct {
	mu      sync.Mutex
	windows map[string]startupTelemetryRateWindow
}

func newStartupTelemetryLimiter() *startupTelemetryRateLimiter {
	return &startupTelemetryRateLimiter{windows: map[string]startupTelemetryRateWindow{}}
}

func (l *startupTelemetryRateLimiter) allow(key string, count int, now time.Time) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	window, exists := l.windows[key]
	if !exists && len(l.windows) >= startupTelemetryMaxRateKeys {
		for existingKey, existingWindow := range l.windows {
			if now.Sub(existingWindow.StartedAt) >= time.Minute {
				delete(l.windows, existingKey)
			}
		}
		if len(l.windows) >= startupTelemetryMaxRateKeys {
			for existingKey := range l.windows {
				delete(l.windows, existingKey)
				break
			}
		}
	}
	if window.StartedAt.IsZero() || now.Sub(window.StartedAt) >= time.Minute {
		window = startupTelemetryRateWindow{StartedAt: now}
	}
	if window.Count+count > startupTelemetryMaxPerMinute {
		l.windows[key] = window
		return false
	}
	window.Count += count
	l.windows[key] = window
	return true
}

func (s *productService) handleReportStartupEventBatch(w http.ResponseWriter, r *http.Request) {
	var body startupTelemetryBatchRequest
	decoder := json.NewDecoder(io.LimitReader(r.Body, 128<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeStartupTelemetryInvalid(w, r, err.Error())
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		writeStartupTelemetryInvalid(w, r, "request body must contain exactly one JSON object")
		return
	}
	proof := strings.TrimSpace(r.Header.Get(startupTelemetryProofHeader))
	if !startupTelemetryProofPattern.MatchString(proof) {
		writeStartupTelemetryInvalid(w, r, "startup proof is required")
		return
	}
	if len(body.Events) == 0 || len(body.Events) > startupTelemetryMaxBatch {
		writeStartupTelemetryInvalid(w, r, "event batch size is invalid")
		return
	}
	if !startupTelemetryLimiter.allow(startupTelemetryRateLimitKey(r, proof), len(body.Events), time.Now()) {
		writeStartupTelemetryUnavailable(w, r, "startup telemetry rate limit exceeded")
		return
	}

	records := make([]application.StartupDiagnosticRecord, 0, len(body.Events))
	byID := make(map[string]startupTelemetryEventInput, len(body.Events))
	for _, event := range body.Events {
		if err := event.validate(); err != nil {
			writeStartupTelemetryInvalid(w, r, err.Error())
			return
		}
		if _, exists := byID[event.EventID]; exists {
			writeStartupTelemetryInvalid(w, r, "eventId must be unique within a batch")
			return
		}
		byID[event.EventID] = event
		records = append(records, event.toDiagnosticRecord())
	}

	ack, err := s.telemetry.ReportStartupDiagnostics(r.Context(), proof, records)
	if err != nil {
		writeStartupTelemetryUnavailable(w, r, err.Error())
		return
	}
	if !ack.DuplicateBatch {
		for _, event := range body.Events {
			recordStartupTelemetryMetrics(event)
		}
	}
	writeJSON(w, http.StatusOK, ack)
}

func writeStartupTelemetryInvalid(w http.ResponseWriter, r *http.Request, debugMessage string) {
	writeStartupTelemetryError(
		w,
		r,
		productopsgenerated.AppErrorFromStartupEventInvalid(debugMessage),
	)
}

func writeStartupTelemetryUnavailable(w http.ResponseWriter, r *http.Request, debugMessage string) {
	writeStartupTelemetryError(
		w,
		r,
		productopsgenerated.AppErrorFromStartupTelemetryUnavailable(debugMessage),
	)
}

func writeStartupTelemetryError(w http.ResponseWriter, r *http.Request, appError *rterr.AppError) {
	rterr.WriteHTTPError(w, appError, rterr.HTTPWriteOptionsFromRequest(r))
}

func startupTelemetryRateLimitKey(r *http.Request, _ string) string {
	host, _, err := net.SplitHostPort(strings.TrimSpace(r.RemoteAddr))
	if err != nil || host == "" {
		host = strings.TrimSpace(r.RemoteAddr)
	}
	// proof 可关联匿名启动尝试，但不是服务端签发的认证凭据；若将它拼进限流键，
	// 同一来源可以不断更换 proof 绕过保护。因此匿名入口至少按来源 IP 收敛。
	return host
}

func (event startupTelemetryEventInput) validate() error {
	if !startupTelemetryIdentifierPattern.MatchString(event.EventID) ||
		!startupTelemetryIdentifierPattern.MatchString(event.AttemptID) {
		return errStartupTelemetryInvalid
	}
	if event.Sequence < 0 || event.Sequence > 10000 ||
		event.PhaseDurationMs < 0 || event.PhaseDurationMs > 60000 ||
		event.ElapsedMs < 0 || event.ElapsedMs > 86400000 {
		return errStartupTelemetryInvalid
	}
	if event.EventID != event.AttemptID+"_"+strconv.Itoa(event.Sequence) {
		return errStartupTelemetryInvalid
	}
	if _, ok := allowedStartupTelemetryPhases[event.Phase]; !ok ||
		!isStartupTelemetryAllowed(event.Outcome, allowedStartupTelemetryOutcomes) ||
		!isStartupTelemetryAllowed(event.Platform, allowedStartupTelemetryPlatforms) ||
		!isStartupTelemetryAllowed(event.RuntimeEnv, allowedStartupTelemetryRuntimeEnvs) {
		return errStartupTelemetryInvalid
	}
	if _, err := time.Parse(time.RFC3339Nano, event.OccurredAt); err != nil ||
		!isStartupTelemetryAppVersion(event.AppVersion) ||
		!isStartupTelemetryAllowed(
			event.NetworkClass,
			allowedStartupTelemetryNetworkClasses,
		) ||
		!isStartupTelemetryAllowed(
			event.RecoverySurface,
			allowedStartupTelemetryRecoverySurfaces,
		) ||
		!isStartupTelemetryAllowed(
			event.FailureCode,
			allowedStartupTelemetryFailureCodes,
		) ||
		!isStartupTelemetryAllowed(
			event.FailureSource,
			allowedStartupTelemetryFailureSources,
		) ||
		!isStartupTelemetryAllowed(
			event.DeadlineOrigin,
			allowedStartupTelemetryDeadlineOrigins,
		) {
		return errStartupTelemetryInvalid
	}
	return nil
}

func (event startupTelemetryEventInput) toDiagnosticRecord() application.StartupDiagnosticRecord {
	return application.StartupDiagnosticRecord{
		EventID:         event.EventID,
		AttemptID:       event.AttemptID,
		Sequence:        event.Sequence,
		Phase:           event.Phase,
		PhaseDurationMS: event.PhaseDurationMs,
		ElapsedMS:       event.ElapsedMs,
		Outcome:         event.Outcome,
		OccurredAt:      event.OccurredAt,
		Platform:        event.Platform,
		RuntimeEnv:      event.RuntimeEnv,
		AppVersion:      event.AppVersion,
		NetworkClass:    event.NetworkClass,
		RecoverySurface: event.RecoverySurface,
		FailureCode:     event.FailureCode,
		FailureSource:   event.FailureSource,
		DeadlineOrigin:  event.DeadlineOrigin,
	}
}

func isStartupTelemetryAllowed(value string, allowed map[string]struct{}) bool {
	trimmed := strings.TrimSpace(value)
	if trimmed != value {
		return false
	}
	_, ok := allowed[trimmed]
	return ok
}

func isStartupTelemetryAppVersion(value string) bool {
	trimmed := strings.TrimSpace(value)
	return trimmed == value &&
		(trimmed == "" || startupTelemetryAppVersionPattern.MatchString(trimmed))
}

var errStartupTelemetryInvalid = &startupTelemetryValidationError{}

type startupTelemetryValidationError struct{}

func (*startupTelemetryValidationError) Error() string { return "startup telemetry event is invalid" }
