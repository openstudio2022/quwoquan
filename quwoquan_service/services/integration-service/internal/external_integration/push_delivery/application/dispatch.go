package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"log/slog"
	"reflect"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/generated/external_integration/push_delivery"
)

const (
	PushEndpointKindAPNSVoIP  = "apns_voip"
	PushEndpointKindFCM       = "fcm"
	PushProviderLocalRecorder = "local_push_recorder"
	PushDeliveryActionRing    = "ring"
	PushDeliveryActionCancel  = "cancel"
	APNsEnvironmentSandbox    = "sandbox"
	APNsEnvironmentProduction = "production"
)

// PushDeliveryMessage 是 provider 消费的强类型来电推送负载。
type PushDeliveryMessage struct {
	Action          string
	EndpointRef     string
	DeliveryKey     string
	CallID          string
	TargetPersonaID string
	CallType        string
	CallerName      string
	SourceLabel     string
	TrustRelation   string
	ExpiresAt       time.Time
	OccurredAt      time.Time
}

func isNilDependency(value any) bool {
	if value == nil {
		return true
	}
	reflected := reflect.ValueOf(value)
	switch reflected.Kind() {
	case reflect.Chan, reflect.Func, reflect.Interface, reflect.Map, reflect.Pointer, reflect.Slice:
		return reflected.IsNil()
	default:
		return false
	}
}

// PushEndpointSecret 只允许在一次 worker 调用栈内存在。Token 禁止进入错误、日志或存储。
type PushEndpointSecret struct {
	EndpointRef  string
	EndpointKind string
	Token        string
}

type PushEndpointSecretResolver interface {
	ResolvePushEndpointSecret(ctx context.Context, endpointRef string) (PushEndpointSecret, error)
}

type PushEndpointInvalidator interface {
	InvalidatePushEndpoint(
		ctx context.Context,
		endpointRef string,
		endpointKind string,
		reasonCode string,
	) error
}

type PushChannelSender interface {
	SendPush(
		ctx context.Context,
		token string,
		message PushDeliveryMessage,
	) (PushSendReceipt, error)
}

type PushSendReceipt struct {
	ProviderRequestID string
}

// PushProviderFailure 是不会泄露 endpoint token 或 provider 响应正文的结构化错误。
type PushProviderFailure struct {
	Code              string
	Provider          string
	StatusCode        int
	Retryable         bool
	PermanentEndpoint bool
	Cause             error
}

func (e *PushProviderFailure) Error() string {
	if e == nil {
		return ""
	}
	if e.StatusCode > 0 {
		return fmt.Sprintf(
			"push provider %s failed with %s (status=%d retryable=%t permanentEndpoint=%t)",
			e.Provider,
			e.Code,
			e.StatusCode,
			e.Retryable,
			e.PermanentEndpoint,
		)
	}
	return fmt.Sprintf(
		"push provider %s failed with %s (retryable=%t permanentEndpoint=%t)",
		e.Provider,
		e.Code,
		e.Retryable,
		e.PermanentEndpoint,
	)
}

func (e *PushProviderFailure) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.Cause
}

// PushEndpointAccessError 归一化 user-service secret/invalidate 的临时失败。
type PushEndpointAccessError struct {
	Code       string
	StatusCode int
	Retryable  bool
	Cause      error
}

func (e *PushEndpointAccessError) Error() string {
	if e == nil {
		return ""
	}
	return fmt.Sprintf(
		"push endpoint access failed with %s (status=%d retryable=%t)",
		e.Code,
		e.StatusCode,
		e.Retryable,
	)
}

func (e *PushEndpointAccessError) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.Cause
}

// PushDispatchProvider 先临时解析 endpoint secret，再按 endpointKind 精确选择一个
// sender。它本身是 worker policy 中唯一的 push provider，因此不会跨 provider fallback。
type PushDispatchProvider struct {
	resolver    PushEndpointSecretResolver
	invalidator PushEndpointInvalidator
	senders     map[string]PushChannelSender
	logger      *slog.Logger
}

func NewPushDispatchProvider(
	resolver PushEndpointSecretResolver,
	invalidator PushEndpointInvalidator,
	apns PushChannelSender,
	fcm PushChannelSender,
	logger *slog.Logger,
) (*PushDispatchProvider, error) {
	if isNilDependency(resolver) {
		return nil, errors.New("push endpoint secret resolver is required")
	}
	if isNilDependency(invalidator) {
		return nil, errors.New("push endpoint invalidator is required")
	}
	if isNilDependency(apns) || isNilDependency(fcm) {
		return nil, errors.New("both APNs VoIP and FCM senders are required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &PushDispatchProvider{
		resolver:    resolver,
		invalidator: invalidator,
		senders: map[string]PushChannelSender{
			PushEndpointKindAPNSVoIP: apns,
			PushEndpointKindFCM:      fcm,
		},
		logger: logger,
	}, nil
}

func (p *PushDispatchProvider) Send(
	ctx context.Context,
	request reliabletask.ExternalInteractionRequest,
	_ reliabletask.ReliableAsyncTask,
) (result reliabletask.ExternalInteractionResult, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"integration.PushDeliveryDispatch",
		attribute.String("request.id", request.RequestID),
		attribute.String("push.endpoint_ref_hash", pushRefFingerprint(request.Payload["endpointRef"])),
	)
	defer func() {
		outcome := "sent_unconfirmed"
		errorCode := ""
		if err != nil {
			outcome = "failed"
			var failure *PushProviderFailure
			if errors.As(err, &failure) {
				errorCode = failure.Code
			}
		}
		span.SetAttributes(
			attribute.String("push.outcome", outcome),
			attribute.String("error.code", errorCode),
		)
		rtobs.EndSpan(span, err)
	}()

	message, parseErr := ParsePushDeliveryMessage(request)
	if parseErr != nil {
		err = &PushProviderFailure{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Provider:  "push_dispatch",
			Retryable: false,
			Cause:     parseErr,
		}
		return failedPushResult(request, "push_dispatch", err), err
	}
	secret, resolveErr := p.resolver.ResolvePushEndpointSecret(ctx, message.EndpointRef)
	if resolveErr != nil {
		retryable := true
		statusCode := 0
		code := generated.ErrPushEndpointResolutionFailed.Error()
		var endpointErr *PushEndpointAccessError
		if errors.As(resolveErr, &endpointErr) {
			retryable = endpointErr.Retryable
			statusCode = endpointErr.StatusCode
			if endpointErr.Code != "" {
				code = endpointErr.Code
			}
		}
		err = &PushProviderFailure{
			Code:       code,
			Provider:   "push_dispatch",
			StatusCode: statusCode,
			Retryable:  retryable,
			Cause:      resolveErr,
		}
		return failedPushResult(request, "push_dispatch", err), err
	}
	if secret.EndpointRef != message.EndpointRef ||
		strings.TrimSpace(secret.Token) == "" ||
		(secret.EndpointKind != PushEndpointKindAPNSVoIP &&
			secret.EndpointKind != PushEndpointKindFCM) {
		err = &PushProviderFailure{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Provider:  "push_dispatch",
			Retryable: false,
			Cause:     errors.New("resolved push endpoint secret is invalid"),
		}
		return failedPushResult(request, "push_dispatch", err), err
	}
	span.SetAttributes(attribute.String("push.endpoint_kind", secret.EndpointKind))
	sender := p.senders[secret.EndpointKind]
	if isNilDependency(sender) {
		err = &PushProviderFailure{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Provider:  secret.EndpointKind,
			Retryable: false,
			Cause:     errors.New("resolved endpoint kind has no configured sender"),
		}
		return failedPushResult(request, secret.EndpointKind, err), err
	}

	receipt, sendErr := sender.SendPush(ctx, secret.Token, message)
	secret.Token = ""
	if sendErr != nil {
		var providerFailure *PushProviderFailure
		if !errors.As(sendErr, &providerFailure) {
			providerFailure = &PushProviderFailure{
				Code:      generated.ErrPushProviderRejected.Error(),
				Provider:  secret.EndpointKind,
				Retryable: true,
				Cause:     sendErr,
			}
		}
		if providerFailure.Provider == "" {
			providerFailure.Provider = secret.EndpointKind
		}
		if providerFailure.PermanentEndpoint {
			invalidateErr := p.invalidator.InvalidatePushEndpoint(
				ctx,
				message.EndpointRef,
				secret.EndpointKind,
				providerFailure.Code,
			)
			if invalidateErr != nil {
				p.logger.ErrorContext(
					ctx,
					"push endpoint invalidation failed",
					"error_code", generated.ErrPushEndpointInvalidationFailed.Error(),
					"provider", secret.EndpointKind,
					"request_id", request.RequestID,
					"endpoint_ref_hash", pushRefFingerprint(message.EndpointRef),
				)
			}
		}
		p.logger.WarnContext(
			ctx,
			"push delivery provider failed",
			"error_code", providerFailure.Code,
			"provider", secret.EndpointKind,
			"request_id", request.RequestID,
			"retryable", providerFailure.Retryable,
			"permanent_endpoint", providerFailure.PermanentEndpoint,
			"endpoint_ref_hash", pushRefFingerprint(message.EndpointRef),
		)
		err = providerFailure
		return failedPushResult(request, secret.EndpointKind, err), err
	}
	if strings.TrimSpace(receipt.ProviderRequestID) == "" {
		err = &PushProviderFailure{
			Code:      generated.ErrPushProviderRejected.Error(),
			Provider:  secret.EndpointKind,
			Retryable: true,
			Cause:     errors.New("push provider response is missing request identifier"),
		}
		return failedPushResult(request, secret.EndpointKind, err), err
	}
	p.logger.InfoContext(
		ctx,
		"push delivery accepted by provider",
		"provider", secret.EndpointKind,
		"request_id", request.RequestID,
		"endpoint_ref_hash", pushRefFingerprint(message.EndpointRef),
	)
	return reliabletask.ExternalInteractionResult{
		RequestID:         request.RequestID,
		Operation:         request.Operation,
		Status:            reliabletask.ExternalInteractionStatusSentUnconfirmed,
		Provider:          secret.EndpointKind,
		ProviderRequestID: receipt.ProviderRequestID,
		OccurredAt:        time.Now().UTC(),
	}, nil
}

// LocalRecorderPushProvider 只用于 Alpha/Beta/Gamma 的 Port 对等替代装配。它执行完整
// payload 校验，但不会解析、持久化或记录 endpoint token。
type LocalRecorderPushProvider struct{}

func (LocalRecorderPushProvider) Send(
	_ context.Context,
	request reliabletask.ExternalInteractionRequest,
	_ reliabletask.ReliableAsyncTask,
) (reliabletask.ExternalInteractionResult, error) {
	if _, err := ParsePushDeliveryMessage(request); err != nil {
		failure := &PushProviderFailure{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Provider:  PushProviderLocalRecorder,
			Retryable: false,
			Cause:     err,
		}
		return failedPushResult(request, PushProviderLocalRecorder, failure), failure
	}
	return reliabletask.ExternalInteractionResult{
		RequestID:         request.RequestID,
		Operation:         request.Operation,
		Status:            reliabletask.ExternalInteractionStatusSentUnconfirmed,
		Provider:          PushProviderLocalRecorder,
		ProviderRequestID: "local-" + request.RequestID,
		OccurredAt:        time.Now().UTC(),
	}, nil
}

func ValidatePushDeliveryRequest(request reliabletask.ExternalInteractionRequest) error {
	if request.Operation != reliabletask.ExternalInteractionOperationPush {
		return errors.New("request operation is not push_delivery.send")
	}
	if len(request.Payload) != 11 {
		return errors.New("push delivery payload must contain exactly eleven fields")
	}
	for key := range request.Payload {
		if !allowedPushDeliveryPayloadField(key) {
			return fmt.Errorf("push delivery payload field %s is not allowed", key)
		}
	}
	message, err := ParsePushDeliveryMessage(request)
	if err != nil {
		return err
	}
	if !request.ExpiresAt.IsZero() && !message.ExpiresAt.Equal(request.ExpiresAt.UTC()) {
		return errors.New("push delivery payload expiresAt must match request expiresAt")
	}
	return nil
}

func ParsePushDeliveryMessage(
	request reliabletask.ExternalInteractionRequest,
) (PushDeliveryMessage, error) {
	if request.Operation != reliabletask.ExternalInteractionOperationPush {
		return PushDeliveryMessage{}, errors.New("request operation is not push_delivery.send")
	}
	message := PushDeliveryMessage{
		Action:          strings.TrimSpace(request.Payload["action"]),
		EndpointRef:     strings.TrimSpace(request.Payload["endpointRef"]),
		DeliveryKey:     strings.TrimSpace(request.Payload["deliveryKey"]),
		CallID:          strings.TrimSpace(request.Payload["callId"]),
		TargetPersonaID: strings.TrimSpace(request.Payload["targetPersonaId"]),
		CallType:        strings.TrimSpace(request.Payload["callType"]),
		CallerName:      strings.TrimSpace(request.Payload["callerName"]),
		SourceLabel:     strings.TrimSpace(request.Payload["sourceLabel"]),
		TrustRelation:   strings.TrimSpace(request.Payload["trustRelation"]),
	}
	rawExpiresAt := strings.TrimSpace(request.Payload["expiresAt"])
	expiresAt, err := time.Parse(time.RFC3339, rawExpiresAt)
	if err != nil {
		return PushDeliveryMessage{}, errors.New("push delivery expiresAt must be RFC3339")
	}
	message.ExpiresAt = expiresAt.UTC()
	rawOccurredAt := strings.TrimSpace(request.Payload["occurredAt"])
	occurredAt, err := time.Parse(time.RFC3339, rawOccurredAt)
	if err != nil {
		return PushDeliveryMessage{}, errors.New("push delivery occurredAt must be RFC3339")
	}
	message.OccurredAt = occurredAt.UTC()
	switch {
	case message.Action != PushDeliveryActionRing &&
		message.Action != PushDeliveryActionCancel:
		return PushDeliveryMessage{}, errors.New("push delivery action must be ring or cancel")
	case message.EndpointRef == "":
		return PushDeliveryMessage{}, errors.New("push delivery endpointRef is required")
	case !canonicalPushEndpointRef(message.EndpointRef):
		return PushDeliveryMessage{}, errors.New("push delivery endpointRef must be a canonical opaque reference")
	case message.DeliveryKey == "":
		return PushDeliveryMessage{}, errors.New("push delivery deliveryKey is required")
	case len(message.DeliveryKey) > 256:
		return PushDeliveryMessage{}, errors.New("push delivery deliveryKey is too long")
	case message.CallID == "":
		return PushDeliveryMessage{}, errors.New("push delivery callId is required")
	case message.TargetPersonaID == "":
		return PushDeliveryMessage{}, errors.New("push delivery targetPersonaId is required")
	case message.CallType != "audio" && message.CallType != "video":
		return PushDeliveryMessage{}, errors.New("push delivery callType must be audio or video")
	case message.CallerName == "":
		return PushDeliveryMessage{}, errors.New("push delivery callerName is required")
	case message.SourceLabel == "":
		return PushDeliveryMessage{}, errors.New("push delivery sourceLabel is required")
	case message.TrustRelation != "known" && message.TrustRelation != "possibly_unknown":
		return PushDeliveryMessage{}, errors.New("push delivery trustRelation is invalid")
	case !message.ExpiresAt.After(time.Now().UTC()):
		return PushDeliveryMessage{}, errors.New("push delivery expiresAt must be in the future")
	case message.OccurredAt.After(message.ExpiresAt):
		return PushDeliveryMessage{}, errors.New("push delivery occurredAt must not exceed expiresAt")
	case message.OccurredAt.After(time.Now().UTC().Add(5 * time.Minute)):
		return PushDeliveryMessage{}, errors.New("push delivery occurredAt is too far in the future")
	}
	return message, nil
}

func failedPushResult(
	request reliabletask.ExternalInteractionRequest,
	provider string,
	err error,
) reliabletask.ExternalInteractionResult {
	code := generated.ErrPushProviderRejected.Error()
	retryable := true
	var failure *PushProviderFailure
	if errors.As(err, &failure) {
		code = failure.Code
		retryable = failure.Retryable
	}
	return reliabletask.ExternalInteractionResult{
		RequestID:       request.RequestID,
		Operation:       request.Operation,
		Status:          reliabletask.ExternalInteractionStatusFailed,
		Provider:        provider,
		NormalizedError: code,
		Retryable:       retryable,
		OccurredAt:      time.Now().UTC(),
	}
}

func pushRefFingerprint(endpointRef string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(endpointRef)))
	return hex.EncodeToString(sum[:8])
}

func canonicalPushEndpointRef(value string) bool {
	if len(value) != sha256.Size*2 || strings.ToLower(value) != value {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}

func allowedPushDeliveryPayloadField(key string) bool {
	switch key {
	case "action",
		"endpointRef",
		"deliveryKey",
		"callId",
		"targetPersonaId",
		"callType",
		"callerName",
		"sourceLabel",
		"trustRelation",
		"expiresAt",
		"occurredAt":
		return true
	default:
		return false
	}
}
