package orchestration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"quwoquan_service/generated/serviceclients"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
)

const maxAssistantDeliveryPolicyResponseBytes = 64 << 10

type AssistantDeliveryPolicyAuthorizationProvider interface {
	AuthorizationHeader(context.Context) (string, error)
}

type UserDeliveryPolicyClient struct {
	baseURL       string
	authorization AssistantDeliveryPolicyAuthorizationProvider
	client        *http.Client
}

func NewUserDeliveryPolicyClient(
	baseURL string,
	authorization AssistantDeliveryPolicyAuthorizationProvider,
	client *http.Client,
) (*UserDeliveryPolicyClient, error) {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if baseURL == "" {
		return nil, fmt.Errorf("user delivery policy endpoint is required")
	}
	if authorization == nil {
		return nil, fmt.Errorf(
			"user delivery policy authorization provider is required",
		)
	}
	if client == nil {
		client = &http.Client{Timeout: 600 * time.Millisecond}
	}
	return &UserDeliveryPolicyClient{
		baseURL:       baseURL,
		authorization: authorization,
		client:        client,
	}, nil
}

func (c *UserDeliveryPolicyClient) ResolveAssistantDeliveryPolicy(
	ctx context.Context,
	userID string,
) (ports.AssistantDeliveryPolicy, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"assistant delivery policy owner user id is required",
		)
	}
	path := serviceclients.UserResolveAssistantDeliveryPolicyPath(
		userID,
	)
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		c.baseURL+path,
		nil,
	)
	if err != nil {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"build assistant delivery policy request: %w",
			err,
		)
	}
	authorizationHeader, err := c.authorization.AuthorizationHeader(ctx)
	if err != nil {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"authorize assistant delivery policy request: %w",
			err,
		)
	}
	request.Header.Set("Authorization", authorizationHeader)
	response, err := c.client.Do(request)
	if err != nil {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"resolve assistant delivery policy: %w",
			err,
		)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(
		io.LimitReader(
			response.Body,
			maxAssistantDeliveryPolicyResponseBytes+1,
		),
	)
	if err != nil {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"read assistant delivery policy: %w",
			err,
		)
	}
	if len(body) > maxAssistantDeliveryPolicyResponseBytes {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"assistant delivery policy response exceeds %d bytes",
			maxAssistantDeliveryPolicyResponseBytes,
		)
	}
	if response.StatusCode != http.StatusOK {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"resolve assistant delivery policy status=%d body=%s",
			response.StatusCode,
			strings.TrimSpace(string(body)),
		)
	}
	var payload struct {
		UserID           string  `json:"userId"`
		AssistantEnabled *bool   `json:"assistantEnabled"`
		QuietHoursStart  *string `json:"quietHoursStart"`
		QuietHoursEnd    *string `json:"quietHoursEnd"`
		Version          *int64  `json:"version"`
		UpdatedAt        *string `json:"updatedAt"`
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"decode assistant delivery policy: %w",
			err,
		)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"decode assistant delivery policy: trailing JSON content",
		)
	}
	resolvedUserID := strings.TrimSpace(payload.UserID)
	if resolvedUserID != "" && resolvedUserID != userID {
		RecordAssistantWrongDestinationIncident()
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"assistant delivery policy owner mismatch",
		)
	}
	if resolvedUserID == "" ||
		payload.AssistantEnabled == nil ||
		payload.Version == nil ||
		payload.UpdatedAt == nil ||
		*payload.Version < 0 {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"assistant delivery policy response is incomplete",
		)
	}
	if _, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(*payload.UpdatedAt),
	); err != nil {
		return ports.AssistantDeliveryPolicy{}, fmt.Errorf(
			"assistant delivery policy updatedAt is invalid: %w",
			err,
		)
	}
	start, end, err := normalizeAssistantQuietHours(
		payload.QuietHoursStart,
		payload.QuietHoursEnd,
	)
	if err != nil {
		return ports.AssistantDeliveryPolicy{}, err
	}
	return ports.AssistantDeliveryPolicy{
		UserID:           resolvedUserID,
		AssistantEnabled: *payload.AssistantEnabled,
		QuietHoursStart:  start,
		QuietHoursEnd:    end,
		Version:          *payload.Version,
	}, nil
}

func normalizeAssistantQuietHours(
	rawStart *string,
	rawEnd *string,
) (*time.Duration, *time.Duration, error) {
	if rawStart == nil && rawEnd == nil {
		return nil, nil, nil
	}
	if rawStart == nil || rawEnd == nil {
		return nil, nil, fmt.Errorf(
			"assistant delivery policy quiet hours must include both bounds",
		)
	}
	start, err := parseAssistantTimeOfDay(*rawStart)
	if err != nil {
		return nil, nil, fmt.Errorf(
			"parse assistant delivery quietHoursStart: %w",
			err,
		)
	}
	end, err := parseAssistantTimeOfDay(*rawEnd)
	if err != nil {
		return nil, nil, fmt.Errorf(
			"parse assistant delivery quietHoursEnd: %w",
			err,
		)
	}
	return &start, &end, nil
}

func parseAssistantTimeOfDay(raw string) (time.Duration, error) {
	parsed, err := time.Parse("15:04", strings.TrimSpace(raw))
	if err != nil {
		return 0, err
	}
	return time.Duration(parsed.Hour())*time.Hour +
		time.Duration(parsed.Minute())*time.Minute, nil
}
