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
	ModuleGateway      Module = "GATEWAY"
	ModuleOrch         Module = "ORCH"
	ModuleContent      Module = "CONTENT"
	ModuleCircle       Module = "CIRCLE"
	ModuleEntity       Module = "ENTITY"
	ModuleIntegration  Module = "INTEGRATION"
	ModuleUser         Module = "USER"
	ModuleChat         Module = "CHAT"
	ModuleRTC          Module = "RTC"
	ModuleRealtime     Module = "REALTIME"
	ModuleOps          Module = "OPS"
	ModuleAssistant    Module = "ASSISTANT"
	ModuleNotification Module = "NOTIFICATION"
	ModuleSearch       Module = "SEARCH"
	ModuleTag          Module = "TAG"
	ModuleDB           Module = "DB"
	ModuleMQ           Module = "MQ"
	ModuleCache        Module = "CACHE"
	ModuleOSS          Module = "OSS"
	ModuleCDN          Module = "CDN"
	ModuleUnknown      Module = "UNKNOWN"
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
	Code           ErrorCode
	SemanticReason string
	HTTPStatus     int
	UserMessage    string
	DebugMessage   string
	Location       RuntimeErrorLocation
	Context        RuntimeErrorContext
	Recovery       RuntimeErrorRecovery
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
	Recovery     RuntimeErrorRecovery `json:"recovery"`
}

// RuntimeErrorRecovery 是错误恢复指令，唯一真相源为 errors.yaml 的
// recovery_action / recovery_after_seconds，由 codegen 注入到 AppError 后随响应下发。
// Action ∈ {retry, surface, absorb, fallback, escalate, compensate}（对齐端侧
// RuntimeRecoveryAction）；DisruptionLevel ∈ {silent, passiveIndicator, snackbar,
// inlineCard, permissionCard}（对齐端侧 UserDisruptionLevel），本轮静态推导、不热配。
type RuntimeErrorRecovery struct {
	Action          string `json:"action"`
	AfterSeconds    int    `json:"afterSeconds,omitempty"`
	DisruptionLevel string `json:"disruptionLevel"`
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
	Locale       string
	IncludeDebug bool
}

type HTTPWriteOptions struct {
	RequestID    string
	TraceID      string
	Locale       string
	IncludeDebug bool
}

// UserMessageResolver 由运行时（control-plane sync loop）注入，按 code + locale 返回
// 运营态覆盖文案。返回 ok=false 或空串时回退到 codegen 静态 baseline（fail-safe）。
// runtime/errors 不依赖 control-plane，依赖反转由 SetUserMessageResolver 完成。
type UserMessageResolver func(code string, locale string) (string, bool)

//nolint:gochecknoglobals
var userMessageResolver UserMessageResolver

// SetUserMessageResolver 注册运营态文案 override 解析器。传 nil 可清空（恢复纯 baseline）。
func SetUserMessageResolver(resolver UserMessageResolver) {
	userMessageResolver = resolver
}

func resolveUserMessage(code ErrorCode, baseline string, locale string) string {
	resolver := userMessageResolver
	if resolver == nil {
		return baseline
	}
	if override, ok := resolver(code.String(), locale); ok {
		if trimmed := strings.TrimSpace(override); trimmed != "" {
			return trimmed
		}
	}
	return baseline
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
		Locale:    localeFromRequest(r),
	}
}

// localeFromRequest 解析客户端语言：优先 X-Client-Locale，回退 Accept-Language，默认 zh。
// 仅取主语言子标签（如 zh-CN -> zh，en-US -> en）。
func localeFromRequest(r *http.Request) string {
	raw := strings.TrimSpace(r.Header.Get("X-Client-Locale"))
	if raw == "" {
		raw = strings.TrimSpace(r.Header.Get("Accept-Language"))
	}
	if raw == "" {
		return "zh"
	}
	if idx := strings.IndexAny(raw, ",;"); idx >= 0 {
		raw = raw[:idx]
	}
	raw = strings.TrimSpace(raw)
	if idx := strings.IndexByte(raw, '-'); idx >= 0 {
		raw = raw[:idx]
	}
	raw = strings.ToLower(strings.TrimSpace(raw))
	if raw == "" {
		return "zh"
	}
	return raw
}

var reasonPattern = regexp.MustCompile(`^[a-z0-9_]+$`)

var allowedModules = map[Module]struct{}{
	ModuleGateway:      {},
	ModuleOrch:         {},
	ModuleContent:      {},
	ModuleCircle:       {},
	ModuleEntity:       {},
	ModuleIntegration:  {},
	ModuleUser:         {},
	ModuleChat:         {},
	ModuleRTC:          {},
	ModuleRealtime:     {},
	ModuleOps:          {},
	ModuleAssistant:    {},
	ModuleNotification: {},
	ModuleSearch:       {},
	ModuleTag:          {},
	ModuleDB:           {},
	ModuleMQ:           {},
	ModuleCache:        {},
	ModuleOSS:          {},
	ModuleCDN:          {},
	ModuleUnknown:      {},
}

var kindPattern = regexp.MustCompile(`^[A-Z][A-Z0-9_]*$`)

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
	if !kindPattern.MatchString(string(c.Kind)) {
		return fmt.Errorf("invalid kind: %s", c.Kind)
	}
	if !reasonPattern.MatchString(c.Reason) {
		return fmt.Errorf("invalid reason: %s", c.Reason)
	}
	return nil
}

func isUserLikeKind(kind Kind) bool {
	switch kind {
	case "", KindSystem, KindNetwork, KindMiddleware:
		return false
	default:
		return true
	}
}

func NewAppError(code ErrorCode, userMessage string, debugMessage string) *AppError {
	if userMessage == "" {
		userMessage = DefaultUserMessage
	}
	return &AppError{
		Code:         code,
		UserMessage:  userMessage,
		DebugMessage: debugMessage,
		Location: RuntimeErrorLocation{
			BusinessObject: "cloud_request",
			FunctionModule: "runtime_errors",
		},
		Context: RuntimeErrorContext{
			Attributes: []RuntimeErrorContextAttribute{
				{Key: "module", Value: string(code.Module)},
				{Key: "reason", Value: code.Reason},
			},
		},
	}
}

func (e *AppError) WithLocation(location RuntimeErrorLocation) *AppError {
	if e == nil {
		return e
	}
	if strings.TrimSpace(location.BusinessObject) != "" {
		e.Location.BusinessObject = strings.TrimSpace(location.BusinessObject)
	}
	if strings.TrimSpace(location.FunctionModule) != "" {
		e.Location.FunctionModule = strings.TrimSpace(location.FunctionModule)
	}
	e.Location.SourceFilePath = strings.TrimSpace(location.SourceFilePath)
	e.Location.SourceLineNumber = location.SourceLineNumber
	e.Location.SourceLineText = strings.TrimSpace(location.SourceLineText)
	return e
}

// WithRecovery 注入错误恢复指令。codegen 工厂据 errors.yaml 调用；
// 未调用时 ToResponseWithOptions 会按 kind/reason 静态推导默认恢复指令。
func (e *AppError) WithRecovery(action string, afterSeconds int) *AppError {
	if e == nil {
		return e
	}
	e.Recovery.Action = strings.TrimSpace(action)
	if afterSeconds > 0 {
		e.Recovery.AfterSeconds = afterSeconds
	}
	return e
}

// WithMetadata binds the stable public code to the semantic reason and HTTP
// status declared by errors.yaml. The public code remains MODULE.KIND.REASON;
// semantic reason is used only for transport classification and recovery.
func (e *AppError) WithMetadata(semanticReason string, httpStatus int) *AppError {
	if e == nil {
		return e
	}
	e.SemanticReason = strings.TrimSpace(semanticReason)
	if httpStatus >= 400 && httpStatus <= 599 {
		e.HTTPStatus = httpStatus
	}
	return e
}

// WithRecoveryDirective 注入 errors.yaml 的完整恢复指令。
func (e *AppError) WithRecoveryDirective(
	action string,
	disruptionLevel string,
	afterSeconds int,
) *AppError {
	if e == nil {
		return e
	}
	e.WithRecovery(action, afterSeconds)
	e.Recovery.DisruptionLevel = strings.TrimSpace(disruptionLevel)
	return e
}

func (e *AppError) WithContextAttributes(attributes ...RuntimeErrorContextAttribute) *AppError {
	if e == nil {
		return e
	}
	for _, attribute := range attributes {
		key := strings.TrimSpace(attribute.Key)
		if key == "" {
			continue
		}
		e.Context.Attributes = append(e.Context.Attributes, RuntimeErrorContextAttribute{
			Key:   key,
			Value: strings.TrimSpace(attribute.Value),
		})
	}
	return e
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
	semanticReason := effectiveSemanticReason(err)
	return ErrorResponse{
		Code:         err.Code.String(),
		Origin:       runtimeOriginFromCurrentKind(err.Code.Kind),
		Nature:       runtimeNatureFromCurrentKind(err.Code.Kind, semanticReason),
		UserMessage:  resolveUserMessage(err.Code, err.UserMessage, opts.Locale),
		DebugMessage: debugMessage,
		Module:       string(err.Code.Module),
		Kind:         runtimeKindFromCurrent(err.Code.Kind, semanticReason),
		Reason:       semanticReason,
		Message:      debugMessage,
		RequestID:    opts.RequestID,
		TraceID:      opts.TraceID,
		Location:     normalizeRuntimeErrorLocation(err.Location),
		Context:      normalizeRuntimeErrorContext(err.Context, err.Code, semanticReason),
		Recovery:     resolveRuntimeRecovery(err.Recovery, err.Code.Kind, semanticReason),
	}
}

func effectiveSemanticReason(err *AppError) string {
	if err == nil {
		return DefaultInternalReason
	}
	if reason := strings.TrimSpace(err.SemanticReason); reason != "" {
		return reason
	}
	return err.Code.Reason
}

// resolveRuntimeRecovery 以 AppError 携带的恢复指令为准（来自 errors.yaml/codegen）；
// 缺失时按 kind/reason 静态推导默认动作与提示强度，保证响应体始终携带可消费的 recovery。
func resolveRuntimeRecovery(recovery RuntimeErrorRecovery, kind Kind, reason string) RuntimeErrorRecovery {
	action := strings.TrimSpace(recovery.Action)
	if action == "" {
		action = defaultRecoveryAction(kind, reason)
	}
	disruption := strings.TrimSpace(recovery.DisruptionLevel)
	if disruption == "" {
		disruption = defaultDisruptionLevel(action, kind, reason)
	}
	afterSeconds := recovery.AfterSeconds
	if afterSeconds < 0 {
		afterSeconds = 0
	}
	return RuntimeErrorRecovery{
		Action:          action,
		AfterSeconds:    afterSeconds,
		DisruptionLevel: disruption,
	}
}

func defaultRecoveryAction(kind Kind, reason string) string {
	switch runtimeNatureFromCurrentKind(kind, reason) {
	case "transient":
		return "retry"
	default:
		return "surface"
	}
}

func defaultDisruptionLevel(action string, kind Kind, reason string) string {
	if runtimeNatureFromCurrentKind(kind, reason) == "requiresPermission" {
		return "permissionCard"
	}
	switch action {
	case "absorb":
		return "silent"
	case "retry":
		return "snackbar"
	default:
		return "inlineCard"
	}
}

func normalizeRuntimeErrorLocation(location RuntimeErrorLocation) RuntimeErrorLocation {
	location.BusinessObject = strings.TrimSpace(location.BusinessObject)
	location.FunctionModule = strings.TrimSpace(location.FunctionModule)
	location.SourceFilePath = strings.TrimSpace(location.SourceFilePath)
	location.SourceLineText = strings.TrimSpace(location.SourceLineText)
	if location.BusinessObject == "" {
		location.BusinessObject = "cloud_request"
	}
	if location.FunctionModule == "" {
		location.FunctionModule = "runtime_errors"
	}
	return location
}

func normalizeRuntimeErrorContext(
	context RuntimeErrorContext,
	code ErrorCode,
	semanticReason string,
) RuntimeErrorContext {
	out := RuntimeErrorContext{Attributes: make([]RuntimeErrorContextAttribute, 0, len(context.Attributes)+2)}
	seen := map[string]struct{}{}
	for _, attribute := range context.Attributes {
		key := strings.TrimSpace(attribute.Key)
		if key == "" {
			continue
		}
		seen[key] = struct{}{}
		out.Attributes = append(out.Attributes, RuntimeErrorContextAttribute{
			Key:   key,
			Value: strings.TrimSpace(attribute.Value),
		})
	}
	if _, ok := seen["module"]; !ok {
		out.Attributes = append(out.Attributes, RuntimeErrorContextAttribute{Key: "module", Value: string(code.Module)})
	}
	if _, ok := seen["reason"]; !ok {
		out.Attributes = append(out.Attributes, RuntimeErrorContextAttribute{Key: "reason", Value: semanticReason})
	}
	return out
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

func runtimeOriginFromCurrentKind(kind Kind) string {
	if isUserLikeKind(kind) {
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

func runtimeKindFromCurrent(kind Kind, reason string) string {
	if isUserLikeKind(kind) {
		switch reason {
		case "unauthorized",
			"token_expired",
			"otp_expired",
			"otp_mismatch",
			"credential_conflict",
			"last_credential",
			"login_locked",
			"wechat_auth_failed",
			"apple_auth_failed":
			return "auth"
		case "forbidden", "permission_denied", "location_permission_required", "target_blocked_sender":
			return "permission"
		case "not_found", "route_not_found", "strict_isolation":
			return "notFound"
		case "rate_limited", "daily_limit_exceeded":
			return "rateLimited"
		default:
			if strings.HasSuffix(reason, "_not_found") {
				return "notFound"
			}
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

func runtimeNatureFromCurrentKind(kind Kind, reason string) string {
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
	if err.HTTPStatus >= 400 && err.HTTPStatus <= 599 {
		return err.HTTPStatus
	}
	reason := effectiveSemanticReason(err)
	kind := err.Code.Kind
	if isUserLikeKind(kind) {
		switch reason {
		case "invalid_argument",
			"invalid_content_type",
			"invalid_call_ringtone",
			"invalid_appearance_scope",
			"invalid_code",
			"too_many_contacts",
			"otp_expired",
			"otp_mismatch",
			"last_credential",
			"last_sub_account",
			"quota_reached",
			"primary_guard",
			"active_guard",
			"retired_guard",
			"handle_readonly",
			"invalid_region",
			"invalid_tag_ref",
			"invalid_media_asset",
			"interaction_type_invalid",
			"interaction_cursor_invalid",
			"qr_token_invalid":
			return http.StatusBadRequest
		case "unauthorized", "token_expired":
			return http.StatusUnauthorized
		case "forbidden", "original_access_denied",
			"interaction_owner_forbidden",
			"not_participant", "not_mutual", "blocked", "recording_not_allowed":
			return http.StatusForbidden
		case "not_found", "route_not_found":
			return http.StatusNotFound
		case "target_blocked_sender":
			return http.StatusForbidden
		case "duplicate_pending",
			"already_contact",
			"invalid_status_transition",
			"conflict",
			"nickname_taken",
			"handle_taken",
			"credential_conflict",
			"already_accepted",
			"already_in_call",
			"call_full",
			"cannot_answer",
			"invalid_call_action",
			"screen_share_conflict":
			return http.StatusConflict
		case "expired", "call_ended", "qr_token_expired":
			return http.StatusGone
		case "media_not_ready":
			return http.StatusBadRequest
		case "rate_limited", "original_access_rate_limited", "daily_limit_exceeded":
			return http.StatusTooManyRequests
		case "location_unavailable":
			return http.StatusBadRequest
		case "permission_denied", "location_permission_required":
			return http.StatusForbidden
		case "login_locked":
			return http.StatusLocked
		case "wechat_auth_failed", "apple_auth_failed":
			return http.StatusBadGateway
		}
		if reason == "strict_isolation" || strings.HasSuffix(reason, "_not_found") {
			return http.StatusNotFound
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
		Locale:       opts.Locale,
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
