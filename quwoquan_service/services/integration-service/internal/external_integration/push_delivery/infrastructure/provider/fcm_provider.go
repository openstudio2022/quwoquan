package provider

import (
	"bytes"
	"context"
	"crypto/rsa"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"

	"quwoquan_service/services/integration-service/generated/external_integration/push_delivery"
	"quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
)

const (
	fcmAPIBaseURL        = "https://fcm.googleapis.com"
	fcmMessagingScope    = "https://www.googleapis.com/auth/firebase.messaging"
	fcmResponseBodyLimit = 256 << 10
)

type FCMConfig struct {
	ServiceAccountFile string
	ProjectID          string
	Timeout            time.Duration
	APIBaseURL         string
	Now                func() time.Time
}

type FCMProvider struct {
	client       *http.Client
	timeout      time.Duration
	projectID    string
	apiBaseURL   string
	clientEmail  string
	privateKeyID string
	privateKey   *rsa.PrivateKey
	tokenURI     string
	now          func() time.Time

	tokenMu      sync.Mutex
	accessToken  string
	tokenExpires time.Time
}

type fcmServiceAccount struct {
	Type         string `json:"type"`
	ProjectID    string `json:"project_id"`
	PrivateKeyID string `json:"private_key_id"`
	PrivateKey   string `json:"private_key"`
	ClientEmail  string `json:"client_email"`
	TokenURI     string `json:"token_uri"`
}

func NewFCMProvider(cfg FCMConfig, client *http.Client) (*FCMProvider, error) {
	if client == nil {
		return nil, errors.New("FCM observed HTTP/2 client is required")
	}
	if cfg.Timeout <= 0 {
		return nil, errors.New("FCM timeout must be positive")
	}
	raw, err := readSecretFile(cfg.ServiceAccountFile)
	if err != nil {
		return nil, fmt.Errorf("load FCM service-account file: %w", err)
	}
	var account fcmServiceAccount
	decodeErr := json.Unmarshal(raw, &account)
	clear(raw)
	if decodeErr != nil {
		return nil, fmt.Errorf("parse FCM service-account JSON: %w", decodeErr)
	}
	if account.Type != "service_account" ||
		strings.TrimSpace(account.ClientEmail) == "" ||
		strings.TrimSpace(account.PrivateKey) == "" ||
		strings.TrimSpace(account.TokenURI) == "" {
		return nil, errors.New("FCM service-account JSON is incomplete")
	}
	privateKeyPEM := []byte(account.PrivateKey)
	account.PrivateKey = ""
	privateKey, err := parseRSAPrivateKeyPEM(privateKeyPEM)
	clear(privateKeyPEM)
	if err != nil {
		return nil, err
	}
	projectID := strings.TrimSpace(cfg.ProjectID)
	if projectID == "" {
		projectID = strings.TrimSpace(account.ProjectID)
	}
	if projectID == "" {
		return nil, errors.New("FCM project ID is required")
	}
	if account.ProjectID != "" && strings.TrimSpace(account.ProjectID) != projectID {
		return nil, errors.New("FCM configured project ID does not match service account")
	}
	tokenURI, err := url.Parse(strings.TrimSpace(account.TokenURI))
	if err != nil || tokenURI.Scheme != "https" || tokenURI.Host == "" || tokenURI.User != nil {
		return nil, errors.New("FCM token URI must be absolute HTTPS")
	}
	apiBaseURL := strings.TrimRight(strings.TrimSpace(cfg.APIBaseURL), "/")
	if apiBaseURL == "" {
		apiBaseURL = fcmAPIBaseURL
	}
	apiURL, err := url.Parse(apiBaseURL)
	if err != nil || apiURL.Scheme != "https" || apiURL.Host == "" || apiURL.User != nil {
		return nil, errors.New("FCM API base URL must be absolute HTTPS")
	}
	now := cfg.Now
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &FCMProvider{
		client:       pushHTTPClient(client),
		timeout:      cfg.Timeout,
		projectID:    projectID,
		apiBaseURL:   apiURL.String(),
		clientEmail:  strings.TrimSpace(account.ClientEmail),
		privateKeyID: strings.TrimSpace(account.PrivateKeyID),
		privateKey:   privateKey,
		tokenURI:     tokenURI.String(),
		now:          now,
	}, nil
}

func (p *FCMProvider) SendPush(
	ctx context.Context,
	token string,
	message application.PushDeliveryMessage,
) (application.PushSendReceipt, error) {
	return p.sendPush(ctx, token, message, true)
}

func (p *FCMProvider) sendPush(
	ctx context.Context,
	token string,
	message application.PushDeliveryMessage,
	allowAuthRefresh bool,
) (application.PushSendReceipt, error) {
	if p == nil || p.client == nil || p.privateKey == nil {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      generated.ErrPushProviderCredentialsInvalid.Error(),
			Provider:  application.PushEndpointKindFCM,
			Retryable: false,
			Cause:     errors.New("FCM provider is not initialized"),
		}
	}
	deviceToken := strings.TrimSpace(token)
	if deviceToken == "" {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:              generated.ErrPushEndpointPermanentlyInvalid.Error(),
			Provider:          application.PushEndpointKindFCM,
			Retryable:         false,
			PermanentEndpoint: true,
			Cause:             errors.New("FCM registration token is empty"),
		}
	}
	ttl := message.ExpiresAt.Sub(p.now().UTC())
	if ttl <= 0 {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Provider:  application.PushEndpointKindFCM,
			Retryable: false,
			Cause:     errors.New("FCM message is expired"),
		}
	}
	ttlSeconds := int64((ttl + time.Second - 1) / time.Second)
	accessToken, err := p.oauthAccessToken(ctx)
	if err != nil {
		return application.PushSendReceipt{}, err
	}
	body, err := json.Marshal(fcmSendRequest{
		Message: fcmMessage{
			Token: deviceToken,
			Data: map[string]string{
				"action":          message.Action,
				"deliveryKey":     message.DeliveryKey,
				"callId":          message.CallID,
				"targetPersonaId": message.TargetPersonaID,
				"callType":        message.CallType,
				"callerName":      message.CallerName,
				"sourceLabel":     message.SourceLabel,
				"trustRelation":   message.TrustRelation,
				"expiresAt":       message.ExpiresAt.Format(time.RFC3339),
				"occurredAt":      message.OccurredAt.Format(time.RFC3339),
			},
			Android: fcmAndroidConfig{
				Priority:    "high",
				TTL:         strconv.FormatInt(ttlSeconds, 10) + "s",
				CollapseKey: providerCollapseKey(message.DeliveryKey),
			},
		},
	})
	if err != nil {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Provider:  application.PushEndpointKindFCM,
			Retryable: false,
			Cause:     err,
		}
	}
	defer clear(body)
	requestCtx, cancel := context.WithTimeout(ctx, p.timeout)
	defer cancel()
	endpoint := p.apiBaseURL + "/v1/projects/" +
		url.PathEscape(p.projectID) + "/messages:send"
	request, err := http.NewRequestWithContext(
		requestCtx,
		http.MethodPost,
		endpoint,
		bytes.NewReader(body),
	)
	if err != nil {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Provider:  application.PushEndpointKindFCM,
			Retryable: false,
			Cause:     errors.New("build FCM request"),
		}
	}
	request.Header.Set("Authorization", "Bearer "+accessToken)
	request.Header.Set("Content-Type", "application/json")
	response, err := p.client.Do(request)
	if err != nil {
		code := generated.ErrPushProviderRejected.Error()
		if isPushTimeout(err) {
			code = generated.ErrPushProviderTimeout.Error()
		}
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:      code,
			Provider:  application.PushEndpointKindFCM,
			Retryable: true,
			Cause:     sanitizeHTTPError(err),
		}
	}
	defer response.Body.Close()
	raw, readErr := io.ReadAll(io.LimitReader(response.Body, fcmResponseBodyLimit))
	if readErr != nil {
		return application.PushSendReceipt{}, &application.PushProviderFailure{
			Code:       generated.ErrPushProviderRejected.Error(),
			Provider:   application.PushEndpointKindFCM,
			StatusCode: response.StatusCode,
			Retryable:  true,
			Cause:      errors.New("read FCM response"),
		}
	}
	defer clear(raw)
	if response.StatusCode >= http.StatusOK && response.StatusCode < http.StatusMultipleChoices {
		var accepted struct {
			Name string `json:"name"`
		}
		if json.Unmarshal(raw, &accepted) != nil || strings.TrimSpace(accepted.Name) == "" {
			return application.PushSendReceipt{}, &application.PushProviderFailure{
				Code:       generated.ErrPushProviderRejected.Error(),
				Provider:   application.PushEndpointKindFCM,
				StatusCode: response.StatusCode,
				Retryable:  true,
				Cause:      errors.New("FCM response is missing message name"),
			}
		}
		return application.PushSendReceipt{
			ProviderRequestID: strings.TrimSpace(accepted.Name),
		}, nil
	}
	if response.StatusCode == http.StatusUnauthorized && allowAuthRefresh {
		p.clearOAuthToken()
		return p.sendPush(ctx, deviceToken, message, false)
	}
	return application.PushSendReceipt{}, classifyFCMFailure(response.StatusCode, raw)
}

func (p *FCMProvider) oauthAccessToken(ctx context.Context) (string, error) {
	p.tokenMu.Lock()
	defer p.tokenMu.Unlock()
	now := p.now().UTC()
	if p.accessToken != "" && p.tokenExpires.After(now.Add(time.Minute)) {
		return p.accessToken, nil
	}
	assertion, err := signRS256JWT(
		p.privateKey,
		struct {
			Algorithm string `json:"alg"`
			Type      string `json:"typ"`
			KeyID     string `json:"kid,omitempty"`
		}{Algorithm: "RS256", Type: "JWT", KeyID: p.privateKeyID},
		struct {
			Issuer   string `json:"iss"`
			Scope    string `json:"scope"`
			Audience string `json:"aud"`
			IssuedAt int64  `json:"iat"`
			Expires  int64  `json:"exp"`
		}{
			Issuer:   p.clientEmail,
			Scope:    fcmMessagingScope,
			Audience: p.tokenURI,
			IssuedAt: now.Unix(),
			Expires:  now.Add(time.Hour).Unix(),
		},
	)
	if err != nil {
		return "", &application.PushProviderFailure{
			Code:      generated.ErrPushProviderCredentialsInvalid.Error(),
			Provider:  application.PushEndpointKindFCM,
			Retryable: false,
			Cause:     err,
		}
	}
	form := url.Values{
		"grant_type": {"urn:ietf:params:oauth:grant-type:jwt-bearer"},
		"assertion":  {assertion},
	}
	requestCtx, cancel := context.WithTimeout(ctx, p.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		requestCtx,
		http.MethodPost,
		p.tokenURI,
		strings.NewReader(form.Encode()),
	)
	if err != nil {
		return "", &application.PushProviderFailure{
			Code:      generated.ErrPushProviderCredentialsInvalid.Error(),
			Provider:  application.PushEndpointKindFCM,
			Retryable: false,
			Cause:     errors.New("build FCM OAuth request"),
		}
	}
	request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	response, err := p.client.Do(request)
	if err != nil {
		code := generated.ErrPushProviderRejected.Error()
		if isPushTimeout(err) {
			code = generated.ErrPushProviderTimeout.Error()
		}
		return "", &application.PushProviderFailure{
			Code:      code,
			Provider:  application.PushEndpointKindFCM,
			Retryable: true,
			Cause:     sanitizeHTTPError(err),
		}
	}
	defer response.Body.Close()
	raw, readErr := io.ReadAll(io.LimitReader(response.Body, fcmResponseBodyLimit))
	if readErr != nil {
		return "", &application.PushProviderFailure{
			Code:       generated.ErrPushProviderRejected.Error(),
			Provider:   application.PushEndpointKindFCM,
			StatusCode: response.StatusCode,
			Retryable:  true,
			Cause:      errors.New("read FCM OAuth response"),
		}
	}
	defer clear(raw)
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		failure := classifyFCMFailure(response.StatusCode, raw)
		var providerFailure *application.PushProviderFailure
		if errors.As(failure, &providerFailure) && response.StatusCode < http.StatusInternalServerError &&
			response.StatusCode != http.StatusTooManyRequests {
			providerFailure.Code = generated.ErrPushProviderCredentialsInvalid.Error()
			providerFailure.PermanentEndpoint = false
		}
		return "", failure
	}
	var tokenResponse struct {
		AccessToken string `json:"access_token"`
		TokenType   string `json:"token_type"`
		ExpiresIn   int64  `json:"expires_in"`
	}
	if json.Unmarshal(raw, &tokenResponse) != nil ||
		strings.TrimSpace(tokenResponse.AccessToken) == "" ||
		!strings.EqualFold(strings.TrimSpace(tokenResponse.TokenType), "Bearer") ||
		tokenResponse.ExpiresIn <= 0 {
		return "", &application.PushProviderFailure{
			Code:       generated.ErrPushProviderCredentialsInvalid.Error(),
			Provider:   application.PushEndpointKindFCM,
			StatusCode: response.StatusCode,
			Retryable:  false,
			Cause:      errors.New("FCM OAuth response is invalid"),
		}
	}
	p.accessToken = strings.TrimSpace(tokenResponse.AccessToken)
	p.tokenExpires = now.Add(time.Duration(tokenResponse.ExpiresIn) * time.Second)
	return p.accessToken, nil
}

func (p *FCMProvider) clearOAuthToken() {
	p.tokenMu.Lock()
	p.accessToken = ""
	p.tokenExpires = time.Time{}
	p.tokenMu.Unlock()
}

type fcmSendRequest struct {
	Message fcmMessage `json:"message"`
}

type fcmMessage struct {
	Token   string            `json:"token"`
	Data    map[string]string `json:"data"`
	Android fcmAndroidConfig  `json:"android"`
}

type fcmAndroidConfig struct {
	Priority    string `json:"priority"`
	TTL         string `json:"ttl"`
	CollapseKey string `json:"collapse_key"`
}

type fcmErrorResponse struct {
	Error struct {
		Status  string `json:"status"`
		Details []struct {
			ErrorCode string `json:"errorCode"`
		} `json:"details"`
	} `json:"error"`
}

func classifyFCMFailure(status int, raw []byte) error {
	var decoded fcmErrorResponse
	_ = json.Unmarshal(raw, &decoded)
	errorCode := strings.TrimSpace(decoded.Error.Status)
	for _, detail := range decoded.Error.Details {
		if strings.TrimSpace(detail.ErrorCode) != "" {
			errorCode = strings.TrimSpace(detail.ErrorCode)
			break
		}
	}
	failure := &application.PushProviderFailure{
		Code:       generated.ErrPushDeliveryInvalidRequest.Error(),
		Provider:   application.PushEndpointKindFCM,
		StatusCode: status,
		Retryable:  false,
		Cause:      fmt.Errorf("FCM rejected request reason=%s", safeProviderReason(errorCode)),
	}
	if errorCode == "UNREGISTERED" {
		failure.Code = generated.ErrPushEndpointPermanentlyInvalid.Error()
		failure.PermanentEndpoint = true
		return failure
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
	if status == http.StatusUnauthorized || status == http.StatusForbidden {
		failure.Code = generated.ErrPushProviderCredentialsInvalid.Error()
	}
	return failure
}
