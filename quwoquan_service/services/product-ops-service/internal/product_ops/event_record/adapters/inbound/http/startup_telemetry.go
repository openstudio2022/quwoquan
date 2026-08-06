package httpadapter

import (
	"encoding/json"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	generated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	eventapp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

const (
	startupTelemetryProofHeader = "X-Qwq-Startup-Proof"
	startupTelemetryMaxBatch    = 32
)

var (
	startupTelemetryIdentifierPattern = regexp.MustCompile(`^[A-Za-z0-9_-]{16,128}$`)
	startupTelemetryProofPattern      = regexp.MustCompile(`^[A-Za-z0-9_-]{24,192}$`)
	startupTelemetryAppVersionPattern = regexp.MustCompile(
		`^v?[0-9]+(?:\.[0-9]+){1,3}(?:[-.][A-Za-z0-9]+)*$`,
	)
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

// 所有会进入 Prometheus label 的值必须是有限 allowlist；不能接受任意字符串，
// 否则匿名入口可以制造高基数指标。
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
	"":                          {},
	"page.app.startup_recovery": {},
}

var allowedStartupTelemetryRecoveryLifecycles = map[string]struct{}{
	"":                {},
	"enter":           {},
	"phase_change":    {},
	"external_action": {},
	"runtime_reentry": {},
	"exit":            {},
	"failure":         {},
}

var allowedStartupTelemetryRecoveryMounts = map[string]struct{}{
	"":                 {},
	"bootstrap":        {},
	"runtime_boundary": {},
	"safe_shell":       {},
	"router_error":     {},
}

var allowedStartupTelemetryRecoveryPhases = map[string]struct{}{
	"":                            {},
	"startup_checking":            {},
	"startup_update_required":     {},
	"startup_latest":              {},
	"startup_version_unavailable": {},
	"runtime_unavailable":         {},
	"runtime_reentering":          {},
	"runtime_version_checking":    {},
	"runtime_update_required":     {},
	"runtime_latest":              {},
	"runtime_version_unavailable": {},
}

var allowedStartupTelemetryRecoveryActions = map[string]struct{}{
	"":                {},
	"none":            {},
	"open_update":     {},
	"open_web":        {},
	"external_return": {},
	"runtime_reentry": {},
}

var allowedStartupTelemetryFailureSources = map[string]struct{}{
	"":                        {},
	"bootstrap":               {},
	"router":                  {},
	"startup_deadline":        {},
	"native_watchdog":         {},
	"runtime_boundary":        {},
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
	Events []StartupTelemetryEventInput `json:"events"`
}

// StartupTelemetryEventInput 是匿名入口的固定 wire schema。它故意不复用
// EventRecord 的通用 payload，确保请求体不能携带账户、内容、原始异常或堆栈。
type StartupTelemetryEventInput struct {
	EventID           string `json:"eventId"`
	AttemptID         string `json:"attemptId"`
	Sequence          int    `json:"sequence"`
	Phase             string `json:"phase"`
	PhaseDurationMs   int    `json:"phaseDurationMs"`
	ElapsedMs         int    `json:"elapsedMs"`
	Outcome           string `json:"outcome"`
	OccurredAt        string `json:"occurredAt"`
	Platform          string `json:"platform"`
	RuntimeEnv        string `json:"runtimeEnv"`
	AppVersion        string `json:"appVersion,omitempty"`
	NetworkClass      string `json:"networkClass,omitempty"`
	RecoverySurface   string `json:"recoverySurface,omitempty"`
	RecoveryLifecycle string `json:"recoveryLifecycle,omitempty"`
	RecoveryMount     string `json:"recoveryMount,omitempty"`
	RecoveryPhase     string `json:"recoveryPhase,omitempty"`
	RecoveryAction    string `json:"recoveryAction,omitempty"`
	FailureCode       string `json:"failureCode,omitempty"`
	FailureSource     string `json:"failureSource,omitempty"`
	DeadlineOrigin    string `json:"deadlineOrigin,omitempty"`
}

type StartupTelemetryAcceptedObserver func(StartupTelemetryEventInput)

type StartupTelemetryHandler struct {
	service    *eventapp.TelemetryService
	onAccepted StartupTelemetryAcceptedObserver
}

func NewStartupTelemetryHandler(
	service *eventapp.TelemetryService,
	onAccepted StartupTelemetryAcceptedObserver,
) *StartupTelemetryHandler {
	if service == nil {
		panic("startup telemetry HTTP handler requires telemetry service")
	}
	return &StartupTelemetryHandler{service: service, onAccepted: onAccepted}
}

func (handler *StartupTelemetryHandler) Register(mux *http.ServeMux) {
	mux.Handle("POST /ops/startup-events", handler)
}

func (handler *StartupTelemetryHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	var body startupTelemetryBatchRequest
	decoder := json.NewDecoder(io.LimitReader(r.Body, maxRequestBytes))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeError(w, r, generated.AppErrorFromStartupEventInvalid(err.Error()))
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		writeError(w, r, generated.AppErrorFromStartupEventInvalid(
			"request body must contain exactly one JSON object",
		))
		return
	}
	proof := strings.TrimSpace(r.Header.Get(startupTelemetryProofHeader))
	if !startupTelemetryProofPattern.MatchString(proof) {
		writeError(w, r, generated.AppErrorFromStartupEventInvalid("startup proof is required"))
		return
	}
	if len(body.Events) == 0 || len(body.Events) > startupTelemetryMaxBatch {
		writeError(w, r, generated.AppErrorFromStartupEventInvalid("event batch size is invalid"))
		return
	}
	records := make([]eventapp.StartupDiagnosticRecord, 0, len(body.Events))
	byID := make(map[string]StartupTelemetryEventInput, len(body.Events))
	for _, event := range body.Events {
		if err := event.validate(); err != nil {
			writeError(w, r, generated.AppErrorFromStartupEventInvalid(err.Error()))
			return
		}
		if _, exists := byID[event.EventID]; exists {
			writeError(w, r, generated.AppErrorFromStartupEventInvalid(
				"eventId must be unique within a batch",
			))
			return
		}
		byID[event.EventID] = event
		records = append(records, event.toDiagnosticRecord())
	}

	ack, err := handler.service.ReportStartupDiagnostics(r.Context(), proof, records)
	if err != nil {
		writeError(w, r, generated.AppErrorFromStartupTelemetryUnavailable(err.Error()))
		return
	}
	if !ack.DuplicateBatch && handler.onAccepted != nil {
		for _, event := range body.Events {
			handler.onAccepted(event)
		}
	}
	writeJSON(w, http.StatusOK, ack)
}

func (event StartupTelemetryEventInput) validate() error {
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
		!isStartupTelemetryAllowed(event.NetworkClass, allowedStartupTelemetryNetworkClasses) ||
		!isStartupTelemetryAllowed(event.RecoverySurface, allowedStartupTelemetryRecoverySurfaces) ||
		!isStartupTelemetryAllowed(event.RecoveryLifecycle, allowedStartupTelemetryRecoveryLifecycles) ||
		!isStartupTelemetryAllowed(event.RecoveryMount, allowedStartupTelemetryRecoveryMounts) ||
		!isStartupTelemetryAllowed(event.RecoveryPhase, allowedStartupTelemetryRecoveryPhases) ||
		!isStartupTelemetryAllowed(event.RecoveryAction, allowedStartupTelemetryRecoveryActions) ||
		!isStartupTelemetryAllowed(event.FailureCode, allowedStartupTelemetryFailureCodes) ||
		!isStartupTelemetryAllowed(event.FailureSource, allowedStartupTelemetryFailureSources) ||
		!isStartupTelemetryAllowed(event.DeadlineOrigin, allowedStartupTelemetryDeadlineOrigins) {
		return errStartupTelemetryInvalid
	}
	if !event.validRecoveryContract() {
		return errStartupTelemetryInvalid
	}
	return nil
}

func (event StartupTelemetryEventInput) validRecoveryContract() bool {
	isRecoveryPhase := event.Phase == "recovery"
	hasLifecycle := event.RecoveryLifecycle != ""
	if isRecoveryPhase != hasLifecycle {
		return false
	}
	if !isRecoveryPhase {
		return event.RecoverySurface == "" && event.RecoveryMount == "" &&
			event.RecoveryPhase == "" && event.RecoveryAction == ""
	}
	if event.RecoverySurface != "page.app.startup_recovery" ||
		event.RecoveryMount == "" || event.RecoveryPhase == "" ||
		event.RecoveryAction == "" {
		return false
	}
	switch event.RecoveryLifecycle {
	case "enter":
		return event.Outcome == "entered" && event.RecoveryAction == "none"
	case "phase_change":
		return event.Outcome == "observed" && event.RecoveryAction == "none"
	case "external_action":
		return oneOf(event.Outcome, "started", "success", "failed") &&
			oneOf(event.RecoveryAction, "open_update", "open_web", "external_return")
	case "runtime_reentry":
		return oneOf(event.Outcome, "started", "success", "failed") &&
			event.RecoveryAction == "runtime_reentry"
	case "exit":
		return oneOf(event.Outcome, "success", "failed") &&
			event.RecoveryAction == "none"
	case "failure":
		return event.Outcome == "failed" && event.RecoveryAction == "none" &&
			event.FailureSource != ""
	default:
		return false
	}
}

func oneOf(value string, allowed ...string) bool {
	for _, candidate := range allowed {
		if value == candidate {
			return true
		}
	}
	return false
}

func (event StartupTelemetryEventInput) toDiagnosticRecord() eventapp.StartupDiagnosticRecord {
	return eventapp.StartupDiagnosticRecord{
		EventID:           event.EventID,
		AttemptID:         event.AttemptID,
		Sequence:          event.Sequence,
		Phase:             event.Phase,
		PhaseDurationMS:   event.PhaseDurationMs,
		ElapsedMS:         event.ElapsedMs,
		Outcome:           event.Outcome,
		OccurredAt:        event.OccurredAt,
		Platform:          event.Platform,
		RuntimeEnv:        event.RuntimeEnv,
		AppVersion:        event.AppVersion,
		NetworkClass:      event.NetworkClass,
		RecoverySurface:   event.RecoverySurface,
		RecoveryLifecycle: event.RecoveryLifecycle,
		RecoveryMount:     event.RecoveryMount,
		RecoveryPhase:     event.RecoveryPhase,
		RecoveryAction:    event.RecoveryAction,
		FailureCode:       event.FailureCode,
		FailureSource:     event.FailureSource,
		DeadlineOrigin:    event.DeadlineOrigin,
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

func (*startupTelemetryValidationError) Error() string {
	return "startup telemetry event is invalid"
}
