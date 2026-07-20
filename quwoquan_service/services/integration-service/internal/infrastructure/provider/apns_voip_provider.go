package provider

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"quwoquan_service/services/integration-service/internal/application"
	"quwoquan_service/services/integration-service/internal/generated"
)

const (
	APNsEnvironmentSandbox    = "sandbox"
	APNsEnvironmentProduction = "production"

	apnsSandboxBaseURL    = "https://api.sandbox.push.apple.com"
	apnsProductionBaseURL = "https://api.push.apple.com"
	apnsResponseBodyLimit = 64 << 10
	apnsTokenTTL          = 50 * time.Minute
)

type APNsVoIPConfig struct {
	Environment string
	KeyFile     string
	KeyID       string
	TeamID      string
	Topic       string
	Timeout     time.Duration
	BaseURL     string
	Now         func() time.Time
}

type APNsVoIPProvider struct {
	environment string
	keyID       string
	teamID      string
	topic       string
	timeout     time.Duration
	baseURL     string
	privateKey  *ecdsa.PrivateKey
	client      *http.Client
	now         func() time.Time

	tokenMu       sync.Mutex
	cachedToken   string
	tokenIssuedAt time.Time
}

func NewAPNsVoIPProvider(
	cfg APNsVoIPConfig,
	client *http.Client,
) (*APNsVoIPProvider, error) {
	environment := strings.TrimSpace(cfg.Environment)
	if environment != APNsEnvironmentSandbox && environment != APNsEnvironmentProduction {
		return nil, errors.New("APNs environment must be sandbox or production")
	}
	if strings.TrimSpace(cfg.KeyID) == "" ||
		strings.TrimSpace(cfg.TeamID) == "" ||
		strings.TrimSpace(cfg.Topic) == "" {
		return nil, errors.New("APNs key ID, team ID and VoIP topic are required")
	}
	if !strings.HasSuffix(strings.TrimSpace(cfg.Topic), ".voip") {
		return nil, errors.New("APNs VoIP topic must end with .voip")
	}
	if cfg.Timeout <= 0 {
		return nil, errors.New("APNs timeout must be positive")
	}
	if client == nil {
		return nil, errors.New("APNs observed HTTP/2 client is required")
	}
	privateKey, err := loadP256PrivateKeyFile(cfg.KeyFile)
	if err != nil {
		return nil, fmt.Errorf("load APNs token key: %w", err)
	}
	baseURL := strings.TrimRight(strings.TrimSpace(cfg.BaseURL), "/")
	if baseURL == "" {
		if environment == APNsEnvironmentSandbox {
			baseURL = apnsSandboxBaseURL
		} else {
			baseURL = apnsProductionBaseURL
		}
	}
	parsed, err := url.Parse(baseURL)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" || parsed.User != nil {
		return nil, errors.New("APNs base URL must be absolute HTTPS")
	}
	now := cfg.Now
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &APNsVoIPProvider{
		environment: environment,
		keyID:       strings.TrimSpace(cfg.KeyID),
		teamID:      strings.TrimSpace(cfg.TeamID),
		topic:       strings.TrimSpace(cfg.Topic),
		timeout:     cfg.Timeout,
		baseURL:     parsed.String(),
		privateKey:  privateKey,
		client:      pushHTTPClient(client),
		now:         now,
	}, nil
}

func (p *APNsVoIPProvider) SendPush(
	ctx context.Context,
	token string,
	message application.PushDeliveryMessage,
) (application.PushSendReceipt, error) {
	return p.sendPush(ctx, token, message, true)
}

func (p *APNsVoIPProvider) sendPush(
	ctx context.Context,
	token string,
	message application.PushDeliveryMessage,
	allowExpiredTokenRefresh bool,
) (application.PushSendReceipt, error) {
	if p == nil || p.client == nil || p.privateKey == nil {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      generated.ErrPushProviderCredentialsInvalid.Error(),
			Provider:  application.PushEndpointKindAPNSVoIP,
			Retryable: false,
			Cause:     errors.New("APNs provider is not initialized"),
		}
	}
	if !message.ExpiresAt.After(p.now().UTC()) {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Provider:  application.PushEndpointKindAPNSVoIP,
			Retryable: false,
			Cause:     errors.New("APNs VoIP message is expired"),
		}
	}
	deviceToken := strings.TrimSpace(token)
	if deviceToken == "" {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:              generated.ErrPushEndpointPermanentlyInvalid.Error(),
			Provider:          application.PushEndpointKindAPNSVoIP,
			Retryable:         false,
			PermanentEndpoint: true,
			Cause:             errors.New("APNs device token is empty"),
		}
	}
	authorization, err := p.providerToken()
	if err != nil {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      generated.ErrPushProviderCredentialsInvalid.Error(),
			Provider:  application.PushEndpointKindAPNSVoIP,
			Retryable: false,
			Cause:     err,
		}
	}
	body, err := json.Marshal(apnsVoipPayload{
		APS:             apnsAPS{ContentAvailable: 1},
		Action:          message.Action,
		DeliveryKey:     message.DeliveryKey,
		CallID:          message.CallID,
		TargetPersonaID: message.TargetPersonaID,
		CallType:        message.CallType,
		CallerName:      message.CallerName,
		SourceLabel:     message.SourceLabel,
		TrustRelation:   message.TrustRelation,
		ExpiresAt:       message.ExpiresAt.Format(time.RFC3339),
		OccurredAt:      message.OccurredAt.Format(time.RFC3339),
	})
	if err != nil {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Provider:  application.PushEndpointKindAPNSVoIP,
			Retryable: false,
			Cause:     err,
		}
	}
	defer clear(body)
	requestCtx, cancel := context.WithTimeout(ctx, p.timeout)
	defer cancel()
	endpoint := p.baseURL + "/3/device/" + url.PathEscape(deviceToken)
	request, err := http.NewRequestWithContext(
		requestCtx,
		http.MethodPost,
		endpoint,
		bytes.NewReader(body),
	)
	if err != nil {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Provider:  application.PushEndpointKindAPNSVoIP,
			Retryable: false,
			Cause:     errors.New("build APNs request"),
		}
	}
	request.Header.Set("Authorization", "bearer "+authorization)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("apns-push-type", "voip")
	request.Header.Set("apns-topic", p.topic)
	request.Header.Set("apns-priority", "10")
	request.Header.Set("apns-expiration", fmt.Sprintf("%d", message.ExpiresAt.Unix()))
	request.Header.Set("apns-collapse-id", providerCollapseKey(message.DeliveryKey))

	response, err := p.client.Do(request)
	if err != nil {
		code := generated.ErrPushProviderRejected.Error()
		if isPushTimeout(err) {
			code = generated.ErrPushProviderTimeout.Error()
		}
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      code,
			Provider:  application.PushEndpointKindAPNSVoIP,
			Retryable: true,
			Cause:     sanitizeHTTPError(err),
		}
	}
	defer response.Body.Close()
	raw, readErr := io.ReadAll(io.LimitReader(response.Body, apnsResponseBodyLimit))
	if readErr != nil {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:       generated.ErrPushProviderRejected.Error(),
			Provider:   application.PushEndpointKindAPNSVoIP,
			StatusCode: response.StatusCode,
			Retryable:  true,
			Cause:      errors.New("read APNs response"),
		}
	}
	defer clear(raw)
	if response.StatusCode >= http.StatusOK && response.StatusCode < http.StatusMultipleChoices {
		requestID := strings.TrimSpace(response.Header.Get("apns-id"))
		if requestID == "" {
			return application.PushSendReceipt{}, &application.PushProviderFailure{
				Code:       generated.ErrPushProviderRejected.Error(),
				Provider:   application.PushEndpointKindAPNSVoIP,
				StatusCode: response.StatusCode,
				Retryable:  true,
				Cause:      errors.New("APNs response is missing apns-id"),
			}
		}
		return application.PushSendReceipt{ProviderRequestID: requestID}, nil
	}
	reason := decodeAPNsReason(raw)
	if reason == "ExpiredProviderToken" && allowExpiredTokenRefresh {
		p.clearProviderToken()
		return p.sendPush(ctx, deviceToken, message, false)
	}
	return application.PushSendReceipt{}, classifyAPNsFailure(response.StatusCode, reason)
}

func (p *APNsVoIPProvider) providerToken() (string, error) {
	p.tokenMu.Lock()
	defer p.tokenMu.Unlock()
	now := p.now().UTC()
	if p.cachedToken != "" &&
		!now.Before(p.tokenIssuedAt) &&
		now.Sub(p.tokenIssuedAt) < apnsTokenTTL {
		return p.cachedToken, nil
	}
	token, err := signES256JWT(
		p.privateKey,
		struct {
			Algorithm string `json:"alg"`
			KeyID     string `json:"kid"`
		}{Algorithm: "ES256", KeyID: p.keyID},
		struct {
			Issuer   string `json:"iss"`
			IssuedAt int64  `json:"iat"`
		}{Issuer: p.teamID, IssuedAt: now.Unix()},
	)
	if err != nil {
		return "", err
	}
	p.cachedToken = token
	p.tokenIssuedAt = now
	return token, nil
}

func (p *APNsVoIPProvider) clearProviderToken() {
	p.tokenMu.Lock()
	p.cachedToken = ""
	p.tokenIssuedAt = time.Time{}
	p.tokenMu.Unlock()
}

type apnsVoipPayload struct {
	APS             apnsAPS `json:"aps"`
	Action          string  `json:"action"`
	DeliveryKey     string  `json:"deliveryKey"`
	CallID          string  `json:"callId"`
	TargetPersonaID string  `json:"targetPersonaId"`
	CallType        string  `json:"callType"`
	CallerName      string  `json:"callerName"`
	SourceLabel     string  `json:"sourceLabel"`
	TrustRelation   string  `json:"trustRelation"`
	ExpiresAt       string  `json:"expiresAt"`
	OccurredAt      string  `json:"occurredAt"`
}

type apnsAPS struct {
	ContentAvailable int `json:"content-available"`
}

func decodeAPNsReason(raw []byte) string {
	var payload struct {
		Reason string `json:"reason"`
	}
	if json.Unmarshal(raw, &payload) != nil {
		return ""
	}
	return strings.TrimSpace(payload.Reason)
}

func classifyAPNsFailure(status int, reason string) error {
	failure := &application.PushProviderFailure{
		Code:       generated.ErrPushDeliveryInvalidRequest.Error(),
		Provider:   application.PushEndpointKindAPNSVoIP,
		StatusCode: status,
		Retryable:  false,
		Cause:      fmt.Errorf("APNs rejected request reason=%s", safeProviderReason(reason)),
	}
	if status == http.StatusTooManyRequests {
		failure.Code = generated.ErrPushProviderRateLimited.Error()
		failure.Retryable = true
		return failure
	}
	if status >= http.StatusInternalServerError {
		failure.Code = generated.ErrPushProviderRejected.Error()
		failure.Retryable = true
		return failure
	}
	if status == http.StatusGone ||
		reason == "BadDeviceToken" ||
		reason == "DeviceTokenNotForTopic" ||
		reason == "Unregistered" {
		failure.Code = generated.ErrPushEndpointPermanentlyInvalid.Error()
		failure.PermanentEndpoint = true
		return failure
	}
	if status == http.StatusForbidden ||
		status == http.StatusUnauthorized ||
		reason == "InvalidProviderToken" ||
		reason == "MissingProviderToken" ||
		reason == "BadCertificate" ||
		reason == "BadCertificateEnvironment" ||
		reason == "ExpiredProviderToken" {
		failure.Code = generated.ErrPushProviderCredentialsInvalid.Error()
		return failure
	}
	return failure
}

func isPushTimeout(err error) bool {
	if errors.Is(err, context.DeadlineExceeded) {
		return true
	}
	var netErr net.Error
	return errors.As(err, &netErr) && netErr.Timeout()
}

func safeProviderReason(reason string) string {
	normalized := strings.TrimSpace(reason)
	if normalized == "" {
		return "unknown"
	}
	if len(normalized) > 64 {
		return "unsupported"
	}
	for _, char := range normalized {
		if (char < 'A' || char > 'Z') &&
			(char < 'a' || char > 'z') &&
			(char < '0' || char > '9') &&
			char != '_' {
			return "unsupported"
		}
	}
	return normalized
}
