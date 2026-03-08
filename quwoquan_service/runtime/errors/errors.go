package runtimeerrors

import (
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"strings"
)

type Module string
type Kind string

const (
	ModuleGateway   Module = "GATEWAY"
	ModuleOrch      Module = "ORCH"
	ModuleContent     Module = "CONTENT"
	ModuleCircle      Module = "CIRCLE"
	ModuleIntegration Module = "INTEGRATION"
	ModuleUser        Module = "USER"
	ModuleChat      Module = "CHAT"
	ModuleRTC       Module = "RTC"
	ModuleOps       Module = "OPS"
	ModuleAssistant Module = "ASSISTANT"
	ModuleDB        Module = "DB"
	ModuleMQ        Module = "MQ"
	ModuleCache     Module = "CACHE"
	ModuleOSS       Module = "OSS"
	ModuleCDN       Module = "CDN"
	ModuleUnknown   Module = "UNKNOWN"
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
	Retryable    bool
	Details      map[string]any
}

type ErrorResponse struct {
	Code         string         `json:"code"`
	UserMessage  string         `json:"userMessage"`
	DebugMessage string         `json:"debugMessage"`
	Module       string         `json:"module"`
	Kind         string         `json:"kind"`
	Reason       string         `json:"reason"`
	Message      string         `json:"message,omitempty"`
	RequestID    string         `json:"requestId,omitempty"`
	TraceID      string         `json:"traceId,omitempty"`
	Retryable    bool           `json:"retryable"`
	Details      map[string]any `json:"details,omitempty"`
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

var reasonPattern = regexp.MustCompile(`^[a-z0-9_]+$`)

var allowedModules = map[Module]struct{}{
	ModuleGateway:     {},
	ModuleOrch:        {},
	ModuleContent:     {},
	ModuleCircle:      {},
	ModuleIntegration: {},
	ModuleUser:        {},
	ModuleChat:      {},
	ModuleRTC:       {},
	ModuleOps:       {},
	ModuleAssistant: {},
	ModuleDB:        {},
	ModuleMQ:        {},
	ModuleCache:     {},
	ModuleOSS:       {},
	ModuleCDN:       {},
	ModuleUnknown:   {},
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

func NewAppError(code ErrorCode, userMessage string, debugMessage string, retryable bool) *AppError {
	if userMessage == "" {
		userMessage = DefaultUserMessage
	}
	return &AppError{
		Code:         code,
		UserMessage:  userMessage,
		DebugMessage: debugMessage,
		Retryable:    retryable,
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
		UserMessage:  err.UserMessage,
		DebugMessage: debugMessage,
		Module:       string(err.Code.Module),
		Kind:         string(err.Code.Kind),
		Reason:       err.Code.Reason,
		Message:      debugMessage,
		RequestID:    opts.RequestID,
		TraceID:      opts.TraceID,
		Retryable:    err.Retryable,
		Details:      err.Details,
	}
}

func NormalizeError(err error) *AppError {
	if err == nil {
		return NewAppError(NewCode(ModuleUnknown, KindSystem, DefaultInternalReason), DefaultUserMessage, "nil error", false)
	}
	if appErr, ok := err.(*AppError); ok {
		if appErr.UserMessage == "" {
			appErr.UserMessage = DefaultUserMessage
		}
		if validateErr := appErr.Code.Validate(); validateErr != nil {
			return NewAppError(NewCode(ModuleUnknown, KindSystem, DefaultInternalReason), DefaultUserMessage, "invalid app error code: "+validateErr.Error(), false)
		}
		return appErr
	}
	return NewAppError(NewCode(ModuleUnknown, KindSystem, DefaultInternalReason), DefaultUserMessage, err.Error(), false)
}

func NewInvalidArgument(module Module, userMessage string, debugMessage string) *AppError {
	return NewAppError(NewCode(module, KindUser, DefaultInvalidReason), userMessage, debugMessage, false)
}

func NewUnavailable(module Module, userMessage string, debugMessage string) *AppError {
	return NewAppError(NewCode(module, KindMiddleware, DefaultUnavailableReason), userMessage, debugMessage, true)
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
		case "not_found":
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
