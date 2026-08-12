package provider

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
)

const (
	externalProviderResponseLimit = 1 << 20

	externalProviderTimeoutCode  = "INTEGRATION.MIDDLEWARE.provider_timeout"
	externalProviderRejectedCode = "INTEGRATION.MIDDLEWARE.provider_rejected"
	smsProviderTimeoutCode       = "INTEGRATION.MIDDLEWARE.sms_provider_timeout"
	smsProviderRejectedCode      = "INTEGRATION.MIDDLEWARE.sms_provider_rejected"
	smsOTPCodeRefInvalidCode     = "INTEGRATION.SYSTEM.sms_otp_code_ref_invalid"
)

type HTTPExternalProviderConfig struct {
	Name              string
	Operation         string
	Endpoint          string
	BearerToken       string
	Timeout           time.Duration
	OTPCodeSealer     *otpseal.Sealer
	OTPCodeReferences otpseal.ReferenceStore
}

type HTTPExternalProvider struct {
	name              string
	operation         string
	endpoint          string
	bearerToken       string
	timeout           time.Duration
	client            *http.Client
	otpCodeSealer     *otpseal.Sealer
	otpCodeReferences otpseal.ReferenceStore
}

type ExternalProviderError struct {
	Code       string
	Provider   string
	StatusCode int
	Retryable  bool
	Cause      error
}

func (e *ExternalProviderError) Error() string {
	if e == nil {
		return ""
	}
	if e.StatusCode > 0 {
		return fmt.Sprintf(
			"external provider %s failed with %s (status=%d retryable=%t)",
			e.Provider,
			e.Code,
			e.StatusCode,
			e.Retryable,
		)
	}
	return fmt.Sprintf(
		"external provider %s failed with %s (retryable=%t)",
		e.Provider,
		e.Code,
		e.Retryable,
	)
}

func (e *ExternalProviderError) Unwrap() error {
	if e == nil {
		return nil
	}
	return e.Cause
}

func NewHTTPExternalProvider(
	cfg HTTPExternalProviderConfig,
	client *http.Client,
) (*HTTPExternalProvider, error) {
	name := strings.TrimSpace(cfg.Name)
	operation := strings.TrimSpace(cfg.Operation)
	endpoint := strings.TrimSpace(cfg.Endpoint)
	token := strings.TrimSpace(cfg.BearerToken)
	if err := validateProviderName(operation, name); err != nil {
		return nil, err
	}
	parsed, err := url.Parse(endpoint)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" || parsed.User != nil {
		return nil, fmt.Errorf("external provider %s endpoint must be an absolute https URL", name)
	}
	if token == "" {
		return nil, fmt.Errorf("external provider %s bearer token is required", name)
	}
	if cfg.Timeout <= 0 {
		return nil, fmt.Errorf("external provider %s timeout must be positive", name)
	}
	if client == nil {
		return nil, fmt.Errorf("external provider %s observed HTTP client is required", name)
	}
	if operation == reliabletask.ExternalInteractionOperationSmsOTP &&
		(cfg.OTPCodeSealer == nil || cfg.OTPCodeReferences == nil) {
		return nil, fmt.Errorf("external provider %s otp code reference dependencies are required", name)
	}
	return &HTTPExternalProvider{
		name:              name,
		operation:         operation,
		endpoint:          parsed.String(),
		bearerToken:       token,
		timeout:           cfg.Timeout,
		client:            client,
		otpCodeSealer:     cfg.OTPCodeSealer,
		otpCodeReferences: cfg.OTPCodeReferences,
	}, nil
}

func (p *HTTPExternalProvider) Send(
	ctx context.Context,
	request reliabletask.ExternalInteractionRequest,
	_ reliabletask.ReliableAsyncTask,
) (reliabletask.ExternalInteractionResult, error) {
	if p == nil || p.client == nil {
		return reliabletask.ExternalInteractionResult{}, errors.New("external HTTP provider is not initialized")
	}
	if request.Operation != p.operation {
		return p.failedResult(request, p.rejectedCode(), false), &ExternalProviderError{
			Code:      p.rejectedCode(),
			Provider:  p.name,
			Retryable: false,
			Cause: fmt.Errorf(
				"configured operation %s does not match request operation %s",
				p.operation,
				request.Operation,
			),
		}
	}
	payload, err := p.providerPayload(ctx, request)
	if err != nil {
		return p.failedResult(request, smsOTPCodeRefInvalidCode, false), &ExternalProviderError{
			Code:      smsOTPCodeRefInvalidCode,
			Provider:  p.name,
			Retryable: false,
			Cause:     err,
		}
	}
	if err := validateProviderPayload(request.Operation, payload); err != nil {
		return p.failedResult(request, p.rejectedCode(), false), &ExternalProviderError{
			Code:      p.rejectedCode(),
			Provider:  p.name,
			Retryable: false,
			Cause:     err,
		}
	}
	payloadRef := request.PayloadRef
	payloadDigest := request.PayloadDigest
	if request.Operation == reliabletask.ExternalInteractionOperationSmsOTP {
		payloadRef = ""
		payloadDigest = ""
	}
	body, err := json.Marshal(providerRequest{
		RequestID:      request.RequestID,
		Operation:      request.Operation,
		Tenant:         request.Tenant,
		Environment:    request.Env,
		IdempotencyKey: request.IdempotencyKey,
		PayloadRef:     payloadRef,
		PayloadDigest:  payloadDigest,
		Sensitivity:    request.Sensitivity,
		ExpiresAt:      request.ExpiresAt.UTC().Format(time.RFC3339),
		Payload:        payload,
	})
	if err != nil {
		return p.failedResult(request, p.rejectedCode(), false), &ExternalProviderError{
			Code:      p.rejectedCode(),
			Provider:  p.name,
			Retryable: false,
			Cause:     err,
		}
	}
	requestCtx, cancel := context.WithTimeout(ctx, p.timeout)
	defer cancel()
	httpRequest, err := http.NewRequestWithContext(
		requestCtx,
		http.MethodPost,
		p.endpoint,
		bytes.NewReader(body),
	)
	if err != nil {
		return p.failedResult(request, p.rejectedCode(), false), &ExternalProviderError{
			Code:      p.rejectedCode(),
			Provider:  p.name,
			Retryable: false,
			Cause:     err,
		}
	}
	httpRequest.Header.Set("Authorization", "Bearer "+p.bearerToken)
	httpRequest.Header.Set("Content-Type", "application/json")
	httpRequest.Header.Set("Idempotency-Key", request.IdempotencyKey)
	httpRequest.Header.Set("X-QWQ-Request-ID", request.RequestID)

	response, err := p.client.Do(httpRequest)
	if err != nil {
		code := p.rejectedCode()
		if isTimeout(err) {
			code = p.timeoutCode()
		}
		return p.failedResult(request, code, true), &ExternalProviderError{
			Code:      code,
			Provider:  p.name,
			Retryable: true,
			Cause:     err,
		}
	}
	defer response.Body.Close()
	raw, readErr := io.ReadAll(io.LimitReader(response.Body, externalProviderResponseLimit))
	if readErr != nil {
		return p.failedResult(request, p.rejectedCode(), true), &ExternalProviderError{
			Code:       p.rejectedCode(),
			Provider:   p.name,
			StatusCode: response.StatusCode,
			Retryable:  true,
			Cause:      readErr,
		}
	}
	var decoded providerResponse
	if len(bytes.TrimSpace(raw)) > 0 {
		if err := json.Unmarshal(raw, &decoded); err != nil {
			return p.failedResult(request, p.rejectedCode(), true), &ExternalProviderError{
				Code:       p.rejectedCode(),
				Provider:   p.name,
				StatusCode: response.StatusCode,
				Retryable:  true,
				Cause:      err,
			}
		}
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		retryable := retryableStatus(response.StatusCode)
		if decoded.Retryable != nil {
			retryable = *decoded.Retryable
		}
		return p.failedResult(request, p.rejectedCode(), retryable), &ExternalProviderError{
			Code:       p.rejectedCode(),
			Provider:   p.name,
			StatusCode: response.StatusCode,
			Retryable:  retryable,
		}
	}
	providerRequestID := firstNonEmpty(
		decoded.ProviderRequestID,
		decoded.MessageID,
		decoded.RequestID,
		response.Header.Get("X-Request-ID"),
	)
	if providerRequestID == "" {
		return p.failedResult(request, p.rejectedCode(), true), &ExternalProviderError{
			Code:       p.rejectedCode(),
			Provider:   p.name,
			StatusCode: response.StatusCode,
			Retryable:  true,
			Cause:      errors.New("provider response is missing a traceable request identifier"),
		}
	}
	status, retryable, statusErr := normalizeProviderStatus(decoded.Status, decoded.Retryable)
	if statusErr != nil {
		return p.failedResult(request, p.rejectedCode(), retryable), &ExternalProviderError{
			Code:       p.rejectedCode(),
			Provider:   p.name,
			StatusCode: response.StatusCode,
			Retryable:  retryable,
			Cause:      statusErr,
		}
	}
	if request.Operation == reliabletask.ExternalInteractionOperationSmsOTP {
		_ = p.otpCodeReferences.Delete(ctx, request.RequestID, request.Payload["challengeId"])
	}
	return reliabletask.ExternalInteractionResult{
		RequestID:         request.RequestID,
		Operation:         request.Operation,
		Status:            status,
		Provider:          p.name,
		ProviderRequestID: providerRequestID,
		Retryable:         false,
		OccurredAt:        time.Now().UTC(),
	}, nil
}

type providerRequest struct {
	RequestID      string            `json:"requestId"`
	Operation      string            `json:"operation"`
	Tenant         string            `json:"tenant"`
	Environment    string            `json:"env"`
	IdempotencyKey string            `json:"idempotencyKey"`
	PayloadRef     string            `json:"payloadRef,omitempty"`
	PayloadDigest  string            `json:"payloadDigest,omitempty"`
	Sensitivity    string            `json:"sensitivity"`
	ExpiresAt      string            `json:"expiresAt"`
	Payload        map[string]string `json:"payload"`
}

type providerResponse struct {
	RequestID         string `json:"requestId"`
	ProviderRequestID string `json:"providerRequestId"`
	MessageID         string `json:"messageId"`
	Status            string `json:"status"`
	Retryable         *bool  `json:"retryable"`
}

func (p *HTTPExternalProvider) failedResult(
	request reliabletask.ExternalInteractionRequest,
	code string,
	retryable bool,
) reliabletask.ExternalInteractionResult {
	return reliabletask.ExternalInteractionResult{
		RequestID:       request.RequestID,
		Operation:       request.Operation,
		Status:          reliabletask.ExternalInteractionStatusFailed,
		Provider:        p.name,
		NormalizedError: code,
		Retryable:       retryable,
		OccurredAt:      time.Now().UTC(),
	}
}

func (p *HTTPExternalProvider) timeoutCode() string {
	switch p.operation {
	case reliabletask.ExternalInteractionOperationSmsOTP:
		return smsProviderTimeoutCode
	default:
		return externalProviderTimeoutCode
	}
}

func (p *HTTPExternalProvider) rejectedCode() string {
	switch p.operation {
	case reliabletask.ExternalInteractionOperationSmsOTP:
		return smsProviderRejectedCode
	default:
		return externalProviderRejectedCode
	}
}

func validateProviderName(operation string, name string) error {
	allowed := map[string]map[string]struct{}{
		reliabletask.ExternalInteractionOperationSmsOTP: {
			"aliyun_sms":        {},
			"tencent_sms":       {},
			"local_capture_sms": {},
		},
	}
	providers, ok := allowed[operation]
	if !ok {
		return fmt.Errorf("HTTP external provider operation %q is not supported", operation)
	}
	if _, ok := providers[name]; !ok {
		return fmt.Errorf("provider %q is not valid for operation %q", name, operation)
	}
	return nil
}

func providerPayload(operation string, source map[string]string) map[string]string {
	var allowlist []string
	switch operation {
	case reliabletask.ExternalInteractionOperationSmsOTP:
		allowlist = []string{
			"challengeId",
			"phoneHash",
			"maskedRecipient",
			"templateId",
			"platform",
			"requestRef",
		}
	default:
		return map[string]string{}
	}
	payload := make(map[string]string, len(allowlist))
	for _, key := range allowlist {
		if value := strings.TrimSpace(source[key]); value != "" {
			payload[key] = value
		}
	}
	return payload
}

func (p *HTTPExternalProvider) providerPayload(
	ctx context.Context,
	request reliabletask.ExternalInteractionRequest,
) (map[string]string, error) {
	if request.Operation != reliabletask.ExternalInteractionOperationSmsOTP {
		return providerPayload(request.Operation, request.Payload), nil
	}
	challengeID := strings.TrimSpace(request.Payload["challengeId"])
	if challengeID == "" || p.otpCodeReferences == nil || p.otpCodeSealer == nil {
		return nil, otpseal.ErrReferenceNotFound
	}
	reference, err := p.otpCodeReferences.Get(ctx, request.RequestID, challengeID)
	if err != nil {
		return nil, err
	}
	secret, err := p.otpCodeSealer.Open(reference.CodeRef, otpseal.Binding{
		RequestID:   request.RequestID,
		ChallengeID: challengeID,
		ExpiresAt:   request.ExpiresAt,
	})
	if err != nil {
		return nil, err
	}
	platform := strings.ToLower(strings.TrimSpace(request.Payload["platform"]))
	requestRef := strings.TrimSpace(request.Payload["requestRef"])
	if !validOTPClientPlatform(platform) || requestRef == "" || requestRef != request.RequestID {
		return nil, errors.New("sms otp platform or request reference is invalid")
	}
	return map[string]string{
		"recipient":  secret.Phone,
		"code":       secret.Code,
		"templateId": strings.TrimSpace(request.Payload["templateId"]),
		"platform":   platform,
		"requestRef": requestRef,
	}, nil
}

func validOTPClientPlatform(platform string) bool {
	switch platform {
	case "ios", "android", "web", "acceptance":
		return true
	default:
		return false
	}
}

func validateProviderPayload(operation string, payload map[string]string) error {
	var required []string
	switch operation {
	case reliabletask.ExternalInteractionOperationSmsOTP:
		required = []string{"recipient", "code", "templateId", "platform", "requestRef"}
	default:
		return fmt.Errorf("provider payload operation %q is not supported", operation)
	}
	for _, key := range required {
		if strings.TrimSpace(payload[key]) == "" {
			return fmt.Errorf("provider payload field %s is required for %s", key, operation)
		}
	}
	return nil
}

func normalizeProviderStatus(raw string, explicitRetryable *bool) (string, bool, error) {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "", "accepted", "queued", "pending", "sent", "sent_unconfirmed":
		return reliabletask.ExternalInteractionStatusSentUnconfirmed, false, nil
	case "delivered":
		// A provider's terminal label can only establish that the provider
		// accepted its own handoff. Device presentation remains a separate
		// NotificationDeliveryJob fact, so integration never emits delivered.
		return reliabletask.ExternalInteractionStatusSentUnconfirmed, false, nil
	case "failed", "rejected":
		retryable := false
		if explicitRetryable != nil {
			retryable = *explicitRetryable
		}
		return reliabletask.ExternalInteractionStatusFailed, retryable, errors.New("provider rejected request")
	default:
		return reliabletask.ExternalInteractionStatusFailed, true, fmt.Errorf(
			"provider returned unsupported status %q",
			raw,
		)
	}
}

func retryableStatus(status int) bool {
	return status == http.StatusRequestTimeout ||
		status == http.StatusTooEarly ||
		status == http.StatusTooManyRequests ||
		status >= http.StatusInternalServerError
}

func isTimeout(err error) bool {
	if errors.Is(err, context.DeadlineExceeded) {
		return true
	}
	var netErr net.Error
	return errors.As(err, &netErr) && netErr.Timeout()
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if normalized := strings.TrimSpace(value); normalized != "" {
			return normalized
		}
	}
	return ""
}
