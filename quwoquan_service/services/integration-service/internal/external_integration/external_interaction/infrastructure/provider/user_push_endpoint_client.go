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

	serviceclients "quwoquan_service/generated/serviceclients"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/integration-service/generated/external_integration/push_delivery"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

const userPushEndpointResponseLimit = 64 << 10

type UserPushEndpointClientConfig struct {
	BaseURL     string
	Credentials rtauth.ServiceAuthorizationProvider
	Timeout     time.Duration
}

type UserPushEndpointClient struct {
	baseURL     string
	credentials rtauth.ServiceAuthorizationProvider
	timeout     time.Duration
	client      *http.Client
}

func NewUserPushEndpointClient(
	cfg UserPushEndpointClientConfig,
	client *http.Client,
) (*UserPushEndpointClient, error) {
	baseURL, err := normalizeUserServiceBaseURL(cfg.BaseURL)
	if err != nil {
		return nil, err
	}
	if cfg.Credentials == nil {
		return nil, errors.New("user-service push endpoint credentials are required")
	}
	if cfg.Timeout <= 0 {
		return nil, errors.New("user-service push endpoint timeout must be positive")
	}
	if client == nil {
		return nil, errors.New("user-service push endpoint observed client is required")
	}
	return &UserPushEndpointClient{
		baseURL:     baseURL,
		credentials: cfg.Credentials,
		timeout:     cfg.Timeout,
		client:      pushHTTPClient(client),
	}, nil
}

func (c *UserPushEndpointClient) ResolvePushEndpointSecret(
	ctx context.Context,
	endpointRef string,
) (application.PushEndpointSecret, error) {
	normalizedRef := strings.TrimSpace(endpointRef)
	if normalizedRef == "" {
		return application.PushEndpointSecret{}, &application.PushEndpointAccessError{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Retryable: false,
			Cause:     errors.New("endpointRef is required"),
		}
	}
	endpoint := c.endpointURL(
		serviceclients.UserPushEndpointSecretPathTemplate,
		normalizedRef,
	)
	requestCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(requestCtx, http.MethodGet, endpoint, nil)
	if err != nil {
		return application.PushEndpointSecret{}, &application.PushEndpointAccessError{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Retryable: false,
			Cause:     errors.New("build push endpoint secret request"),
		}
	}
	if err := c.authorize(request); err != nil {
		return application.PushEndpointSecret{}, err
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Cache-Control", "no-store")
	request.Header.Set("Pragma", "no-cache")
	response, err := c.client.Do(request)
	if err != nil {
		return application.PushEndpointSecret{}, pushEndpointTransportError(err)
	}
	defer response.Body.Close()
	raw, readErr := io.ReadAll(io.LimitReader(response.Body, userPushEndpointResponseLimit))
	if readErr != nil {
		return application.PushEndpointSecret{}, &application.PushEndpointAccessError{
			Code:       generated.ErrPushEndpointResolutionFailed.Error(),
			StatusCode: response.StatusCode,
			Retryable:  true,
			Cause:      errors.New("read push endpoint secret response"),
		}
	}
	defer clear(raw)
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return application.PushEndpointSecret{}, classifyPushEndpointResponse(response.StatusCode, false)
	}
	var secret struct {
		EndpointRef  string `json:"endpointRef"`
		EndpointKind string `json:"endpointKind"`
		Token        string `json:"token"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	decodeErr := decoder.Decode(&secret)
	var trailing struct{}
	trailingErr := decoder.Decode(&trailing)
	if decodeErr != nil ||
		!errors.Is(trailingErr, io.EOF) ||
		strings.TrimSpace(secret.EndpointRef) != normalizedRef ||
		strings.TrimSpace(secret.Token) == "" ||
		(strings.TrimSpace(secret.EndpointKind) != application.PushEndpointKindAPNSVoIP &&
			strings.TrimSpace(secret.EndpointKind) != application.PushEndpointKindFCM) {
		secret.Token = ""
		return application.PushEndpointSecret{}, &application.PushEndpointAccessError{
			Code:       generated.ErrPushEndpointResolutionFailed.Error(),
			StatusCode: response.StatusCode,
			Retryable:  false,
			Cause:      errors.New("push endpoint secret response is invalid"),
		}
	}
	return application.PushEndpointSecret{
		EndpointRef:  strings.TrimSpace(secret.EndpointRef),
		EndpointKind: strings.TrimSpace(secret.EndpointKind),
		Token:        secret.Token,
	}, nil
}

func (c *UserPushEndpointClient) InvalidatePushEndpoint(
	ctx context.Context,
	endpointRef string,
	_ string,
	reasonCode string,
) error {
	normalizedRef := strings.TrimSpace(endpointRef)
	if normalizedRef == "" {
		return &application.PushEndpointAccessError{
			Code:      generated.ErrPushDeliveryInvalidRequest.Error(),
			Retryable: false,
			Cause:     errors.New("endpointRef is required"),
		}
	}
	body, err := json.Marshal(struct {
		Reason string `json:"reason"`
	}{
		Reason: strings.TrimSpace(reasonCode),
	})
	if err != nil {
		return &application.PushEndpointAccessError{
			Code:      generated.ErrPushEndpointInvalidationFailed.Error(),
			Retryable: false,
			Cause:     errors.New("encode push endpoint invalidation"),
		}
	}
	endpoint := c.endpointURL(
		serviceclients.UserPushEndpointInvalidatePathTemplate,
		normalizedRef,
	)
	requestCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		requestCtx,
		http.MethodPost,
		endpoint,
		bytes.NewReader(body),
	)
	if err != nil {
		return &application.PushEndpointAccessError{
			Code:      generated.ErrPushEndpointInvalidationFailed.Error(),
			Retryable: false,
			Cause:     errors.New("build push endpoint invalidation request"),
		}
	}
	if err := c.authorize(request); err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := c.client.Do(request)
	if err != nil {
		accessErr := pushEndpointTransportError(err)
		accessErr.Code = generated.ErrPushEndpointInvalidationFailed.Error()
		return accessErr
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, userPushEndpointResponseLimit))
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return classifyPushEndpointResponse(response.StatusCode, true)
	}
	return nil
}

func (c *UserPushEndpointClient) authorize(request *http.Request) error {
	authorization, err := c.credentials.AuthorizationHeader(request.Context())
	if err != nil {
		return &application.PushEndpointAccessError{
			Code:      generated.ErrPushProviderCredentialsInvalid.Error(),
			Retryable: false,
			Cause:     errors.New("issue user-service credential"),
		}
	}
	request.Header.Set("Authorization", authorization)
	return nil
}

func (c *UserPushEndpointClient) endpointURL(template string, endpointRef string) string {
	path := strings.ReplaceAll(
		template,
		"{endpointRef}",
		url.PathEscape(endpointRef),
	)
	return c.baseURL + path
}

func normalizeUserServiceBaseURL(raw string) (string, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(raw), "/")
	parsed, err := url.Parse(baseURL)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" ||
		parsed.User != nil ||
		parsed.RawQuery != "" ||
		parsed.Fragment != "" ||
		parsed.Path != "" {
		return "", errors.New(
			"user-service push endpoint base URL must be an absolute HTTP(S) origin without credentials, path, query, or fragment",
		)
	}
	if parsed.Scheme == "http" && !isTrustedUserServiceHTTPHost(parsed.Hostname()) {
		return "", errors.New(
			"user-service push endpoint plain HTTP is only allowed for trusted internal service discovery or loopback",
		)
	}
	return parsed.String(), nil
}

func isTrustedUserServiceHTTPHost(rawHost string) bool {
	host := strings.ToLower(strings.TrimSuffix(strings.TrimSpace(rawHost), "."))
	if host == "localhost" {
		return true
	}
	if address := net.ParseIP(host); address != nil {
		return address.IsLoopback()
	}
	if host == "user-service" || host == "user-service.internal" {
		return true
	}
	labels := strings.Split(host, ".")
	if len(labels) < 3 || labels[0] != "user-service" {
		return false
	}
	if labels[len(labels)-1] == "svc" {
		return true
	}
	return len(labels) >= 5 &&
		strings.Join(labels[len(labels)-3:], ".") == "svc.cluster.local"
}

func pushEndpointTransportError(err error) *application.PushEndpointAccessError {
	code := generated.ErrPushEndpointResolutionFailed.Error()
	return &application.PushEndpointAccessError{
		Code:      code,
		Retryable: true,
		Cause:     sanitizeHTTPError(err),
	}
}

func classifyPushEndpointResponse(
	status int,
	invalidation bool,
) *application.PushEndpointAccessError {
	code := generated.ErrPushEndpointResolutionFailed.Error()
	if invalidation {
		code = generated.ErrPushEndpointInvalidationFailed.Error()
	}
	retryable := status == http.StatusRequestTimeout ||
		status == http.StatusTooEarly ||
		status == http.StatusTooManyRequests ||
		status >= http.StatusInternalServerError
	if status == http.StatusUnauthorized || status == http.StatusForbidden {
		code = generated.ErrPushProviderCredentialsInvalid.Error()
		retryable = false
	}
	if status == http.StatusNotFound && !invalidation {
		code = generated.ErrPushEndpointPermanentlyInvalid.Error()
		retryable = false
	}
	return &application.PushEndpointAccessError{
		Code:       code,
		StatusCode: status,
		Retryable:  retryable,
		Cause:      fmt.Errorf("user-service push endpoint status %d", status),
	}
}
