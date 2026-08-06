package user

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	serviceclients "quwoquan_service/generated/serviceclients"
	rtauth "quwoquan_service/runtime/auth"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

const pushDestinationResponseLimit = 1 << 20

type PushDestinationClientConfig struct {
	BaseURL     string
	Credentials rtauth.ServiceAuthorizationProvider
	Timeout     time.Duration
}

type PushDestinationClient struct {
	baseURL     string
	credentials rtauth.ServiceAuthorizationProvider
	timeout     time.Duration
	client      *http.Client
}

func NewPushDestinationClient(
	config PushDestinationClientConfig,
	client *http.Client,
) (*PushDestinationClient, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(config.BaseURL), "/")
	parsed, err := url.Parse(baseURL)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" ||
		parsed.User != nil {
		return nil, errors.New(
			"notification user-service base URL must be absolute http or https",
		)
	}
	if config.Credentials == nil {
		return nil, errors.New(
			"notification user-service credentials are required",
		)
	}
	if config.Timeout <= 0 || client == nil {
		return nil, errors.New(
			"notification user-service timeout and observed client are required",
		)
	}
	return &PushDestinationClient{
		baseURL:     baseURL,
		credentials: config.Credentials,
		timeout:     config.Timeout,
		client:      client,
	}, nil
}

func (c *PushDestinationClient) ListPushDestinations(
	ctx context.Context,
	personaID string,
) ([]notification.PushDestinationRef, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return nil, errors.New("personaId is required")
	}
	path := serviceclients.UserResolveIncomingCallPushDestinationsPath(
		personaID,
	)
	requestCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	authorization, err := c.credentials.AuthorizationHeader(requestCtx)
	if err != nil {
		return nil, fmt.Errorf("issue user-service credential: %w", err)
	}
	request, err := http.NewRequestWithContext(
		requestCtx,
		http.MethodGet,
		c.baseURL+path,
		nil,
	)
	if err != nil {
		return nil, err
	}
	request.Header.Set("Authorization", authorization)
	response, err := c.client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(
		response.Body,
		pushDestinationResponseLimit,
	))
	if err != nil {
		return nil, err
	}
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf(
			"user push destinations status=%d",
			response.StatusCode,
		)
	}
	var body struct {
		Destinations []notification.PushDestinationRef `json:"destinations"`
	}
	if err := json.Unmarshal(raw, &body); err != nil {
		return nil, err
	}
	return body.Destinations, nil
}
