package runtimeerrors

import (
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"strings"
	"time"
)

type Module string
type Kind string

const (
	ModuleGateway     Module = "GATEWAY"
	ModuleOrch        Module = "ORCH"
	ModuleContent     Module = "CONTENT"
	ModuleCircle      Module = "CIRCLE"
	ModuleEntity      Module = "ENTITY"
	ModuleIntegration Module = "INTEGRATION"
	ModuleUser        Module = "USER"
	ModuleChat        Module = "CHAT"
	ModuleRTC         Module = "RTC"
	ModuleOps         Module = "OPS"
	ModuleAssistant   Module = "ASSISTANT"
	ModuleDB          Module = "DB"
	ModuleMQ          Module = "MQ"
	ModuleCache       Module = "CACHE"
	ModuleOSS         Module = "OSS"
	ModuleCDN         Module = "CDN"
	ModuleUnknown     Module = "UNKNOWN"
)

const (
	KindUser       Kind = "USER"
	KindSystem     Kind = "SYSTEM"
	KindNetwork    Kind = "NETWORK"
	KindMiddleware Kind = "MIDDLEWARE"
)

type ErrorCode struct {
	Module Module
	Kind   Kind
	Reason string
}

const (
	DefaultUserMessage       = "系统开小差了，请稍后重试"
	RedactedDebugMessage     = "debug_message_redacted"
	DefaultInternalReason    = "internal_error"
	DefaultInvalidReason     = "invalid_argument"
	DefaultUnavailableReason = "unavailable"
)

type AppError struct {
	Code         ErrorCode
	UserMessage  string
	DebugMessage string
}

type ErrorResponse struct {
	Code         string               `json:"code"`
	Origin       string               `json:"origin"`
	Nature       string               `json:"nature"`
	UserMessage  string               `json:"userMessage"`
	DebugMessage string               `json:"debugMessage"`
	Module       string               `json:"module"`
	Kind         string               `json:"kind"`
	Reason       string               `json:"reason"`
	Message      string               `json:"message,omitempty"`
	RequestID    string               `json:"requestId,omitempty"`
	TraceID      string               `json:"traceId,omitempty"`
	Location     RuntimeErrorLocation `json:"location"`
	Context      RuntimeErrorContext  `json:"context"`
}

type RuntimeErrorLocation struct {
	BusinessObject   string `json:"businessObject"`
	FunctionModule   string `json:"functionModule"`
	SourceFilePath   string `json:"sourceFilePath,omitempty"`
	SourceLineNumber int    `json:"sourceLineNumber,omitempty"`
	SourceLineText   string `json:"sourceLineText,omitempty"`
}

type RuntimeErrorContext struct {
	Attributes []RuntimeErrorContextAttribute `json:"attributes"`
}

type RuntimeErrorContextAttribute struct {
	Key   string `json:"key"`
	Value string `json:"value"`
}

type ResponseOptions struct {
	RequestID    string
	TraceID      string
	IncludeDebug bool
}

type HTTPWriteOptions struct {
	RequestID    string
	TraceID      string
	IncludeDebug bool
}

func HTTPWriteOptionsFromRequest(r *http.Request) HTTPWriteOptions {
	if r == nil {
		return HTTPWriteOptions{}
	}
	requestID := strings.TrimSpace(r.Header.Get("X-Request-Id"))
	traceID := strings.TrimSpace(r.Header.Get("X-Trace-Id"))
	if traceID == "" {
		traceID = requestID
	}
	return HTTPWriteOptions{
		RequestID: requestID,
		TraceID:   traceID,
	}
}

var reasonPattern = regexp.MustCompile(`^[a-z0-9_]+$`)

var allowedModules = map[Module]struct{}{
	ModuleGateway:     {},
	ModuleOrch:        {},
	ModuleContent:     {},
	ModuleCircle:      {},
	ModuleEntity:      {},
	ModuleIntegration: {},
	ModuleUser:        {},
	ModuleChat:        {},
	ModuleRTC:         {},
	ModuleOps:         {},
	ModuleAssistant:   {},
	ModuleDB:          {},
	ModuleMQ:          {},
	ModuleCache:       {},
	ModuleOSS:         {},
	ModuleCDN:         {},
	ModuleUnknown:     {},
}

var allowedKinds = map[Kind]struct{}{
	KindUser:       {},
	KindSystem:     {},
	KindNetwork:    {},
	KindMiddleware: {},
}

func NewCode(module Module, kind Kind, reason string) ErrorCode {
	return ErrorCode{Module: module, Kind: kind, Reason: reason}
}

func (c ErrorCode) String() string {
	return fmt.Sprintf("%s.%s.%s", c.Module, c.Kind, c.Reason)
}

func ParseCode(raw string) (ErrorCode, error) {
	parts := strings.Split(raw, ".")
	if len(parts) != 3 {
		return ErrorCode{}, fmt.Errorf("invalid code format: %s", raw)
	}
	code := ErrorCode{
		Module: Module(parts[0]),
		Kind:   Kind(parts[1]),
		Reason: parts[2],
	}
	if err := code.Validate(); err != nil {
		return ErrorCode{}, err
	}
	return code, nil
}

func (c ErrorCode) Validate() error {
	if _, ok := allowedModules[c.Module]; !ok {
		return fmt.Errorf("invalid module: %s", c.Module)
	}
	if _, ok := allowedKinds[c.Kind]; !ok {
		return fmt.Errorf("invalid kind: %s", c.Kind)
	}
	if !reasonPattern.MatchString(c.Reason) {
		return fmt.Errorf("invalid reason: %s", c.Reason)
	}
	return nil
}

func NewAppError(code ErrorCode, userMessage string, debugMessage string) *AppError {
	if userMessage == "" {
		userMessage = DefaultUserMessage
	}
	return &AppError{
		Code:         code,
		UserMessage:  userMessage,
		DebugMessage: debugMessage,
	}
}

func (e *AppError) Error() string {
	return e.Code.String() + ": " + e.DebugMessage
}

func ToResponse(err *AppError, requestID string, traceID string) ErrorResponse {
	return ToResponseWithOptions(err, ResponseOptions{
		RequestID:    requestID,
		TraceID:      traceID,
		IncludeDebug: false,
	})
}

func ToResponseWithOptions(err *AppError, opts ResponseOptions) ErrorResponse {
	debugMessage := RedactedDebugMessage
	if opts.IncludeDebug {
		if err.DebugMessage != "" {
			debugMessage = err.DebugMessage
		}
	}
	return ErrorResponse{
		Code:         err.Code.String(),
		Origin:       runtimeOriginFromLegacyKind(err.Code.Kind),
		Nature:       runtimeNatureFromLegacyKind(err.Code.Kind, err.Code.Reason),
		UserMessage:  err.UserMessage,
		DebugMessage: debugMessage,
		Module:       string(err.Code.Module),
		Kind:         runtimeKindFromLegacy(err.Code.Kind, err.Code.Reason),
		Reason:       err.Code.Reason,
		Message:      debugMessage,
		RequestID:    opts.RequestID,
		TraceID:      opts.TraceID,
		Location: RuntimeErrorLocation{
			BusinessObject: "cloud_request",
			FunctionModule: "runtime_errors",
		},
		Context: RuntimeErrorContext{
			Attributes: []RuntimeErrorContextAttribute{
				{Key: "module", Value: string(err.Code.Module)},
				{Key: "reason", Value: err.Code.Reason},
			},
		},
	}
}

func NormalizeError(err error) *AppError {
	if err == nil {
		return NewAppError(NewCode(ModuleUnknown, KindSystem, DefaultInternalReason), DefaultUserMessage, "nil error")
	}
	if appErr, ok := err.(*AppError); ok {
		if appErr.UserMessage == "" {
			appErr.UserMessage = DefaultUserMessage
		}
		if validateErr := appErr.Code.Validate(); validateErr != nil {
			return NewAppError(NewCode(ModuleUnknown, KindSystem, DefaultInternalReason), DefaultUserMessage, "invalid app error code: "+validateErr.Error())
		}
		return appErr
	}
	return NewAppError(NewCode(ModuleUnknown, KindSystem, DefaultInternalReason), DefaultUserMessage, err.Error())
}

func runtimeOriginFromLegacyKind(kind Kind) string {
	if kind == KindUser {
		return "user"
	}
	if kind == KindNetwork {
		return "environment"
	}
	if kind == KindMiddleware {
		return "remoteDependency"
	}
	return "system"
}

func runtimeKindFromLegacy(kind Kind, reason string) string {
	if kind == KindUser {
		switch reason {
		case "unauthorized":
			return "auth"
		case "forbidden", "permission_denied", "location_permission_required":
			return "permission"
		case "not_found", "route_not_found":
			return "notFound"
		case "rate_limited":
			return "rateLimited"
		default:
			return "validation"
		}
	}
	if kind == KindNetwork {
		if reason == "timeout" {
			return "timeout"
		}
		return "network"
	}
	if kind == KindMiddleware {
		if reason == "timeout" || reason == "upstream_timeout" {
			return "timeout"
		}
		return "unavailable"
	}
	return "internal"
}

func runtimeNatureFromLegacyKind(kind Kind, reason string) string {
	if kind == KindNetwork || kind == KindMiddleware {
		return "transient"
	}
	if reason == "permission_denied" || reason == "location_permission_required" {
		return "requiresPermission"
	}
	if kind == KindSystem {
		return "bug"
	}
	return "permanent"
}

func NewInvalidArgument(module Module, userMessage string, debugMessage string) *AppError {
	return NewAppError(NewCode(module, KindUser, DefaultInvalidReason), userMessage, debugMessage)
}

func NewUnavailable(module Module, userMessage string, debugMessage string) *AppError {
	return NewAppError(NewCode(module, KindMiddleware, DefaultUnavailableReason), userMessage, debugMessage)
}

func HTTPStatusFromError(err *AppError) int {
	if err == nil {
		return http.StatusInternalServerError
	}
	reason := err.Code.Reason
	kind := err.Code.Kind
	if kind == KindUser {
		switch reason {
		case "invalid_argument", "invalid_content_type":
			return http.StatusBadRequest
		case "unauthorized":
			return http.StatusUnauthorized
		case "forbidden":
			return http.StatusForbidden
		case "not_found", "route_not_found":
			return http.StatusNotFound
		case "conflict":
			return http.StatusConflict
		case "rate_limited":
			return http.StatusTooManyRequests
		case "location_unavailable":
			return http.StatusBadRequest
		case "permission_denied", "location_permission_required":
			return http.StatusForbidden
		}
	}
	if kind == KindNetwork && reason == "timeout" {
		return http.StatusGatewayTimeout
	}
	if kind == KindMiddleware {
		switch reason {
		case "timeout", "upstream_timeout":
			return http.StatusGatewayTimeout
		case "unavailable":
			return http.StatusServiceUnavailable
		}
	}
	return http.StatusInternalServerError
}

func WriteHTTPError(w http.ResponseWriter, err error, opts HTTPWriteOptions) {
	appErr := NormalizeError(err)
	if opts.RequestID == "" {
		opts.RequestID = fmt.Sprintf("runtime.err.req.%d", time.Now().UnixNano())
	}
	if opts.TraceID == "" {
		opts.TraceID = opts.RequestID
	}
	resp := ToResponseWithOptions(appErr, ResponseOptions{
		RequestID:    opts.RequestID,
		TraceID:      opts.TraceID,
		IncludeDebug: opts.IncludeDebug,
	})
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	if opts.RequestID != "" {
		w.Header().Set("X-Request-Id", opts.RequestID)
	}
	if opts.TraceID != "" {
		w.Header().Set("X-Trace-Id", opts.TraceID)
	}
	w.WriteHeader(HTTPStatusFromError(appErr))
	_ = json.NewEncoder(w).Encode(resp)
}
