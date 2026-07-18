// Package notificationclient implements Assistant's typed command egress to
// notification-service. It deliberately exposes no Notification query or
// lifecycle methods, so Assistant cannot regain aggregate ownership through
// this adapter.
package notificationclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/application"
)

const (
	createAppMessagePath = "/internal/app-messages"
	responseBodyLimit    = 1 << 20
)

type Client struct {
	endpoint    string
	http        *http.Client
	credentials rtauth.ServiceAuthorizationProvider
}

func NewClient(
	httpClient *http.Client,
	baseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
) (*Client, error) {
	parsed, err := url.Parse(strings.TrimRight(strings.TrimSpace(baseURL), "/"))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") {
		return nil, fmt.Errorf("notification service base URL must be absolute http or https")
	}
	if httpClient == nil {
		return nil, fmt.Errorf("notification service observed HTTP client is required")
	}
	if credentials == nil {
		return nil, fmt.Errorf("notification service credentials are required")
	}
	return &Client{
		endpoint:    strings.TrimRight(parsed.String(), "/") + createAppMessagePath,
		http:        httpClient,
		credentials: credentials,
	}, nil
}

func (c *Client) CreateAppMessage(
	ctx context.Context,
	command application.NotificationAppMessageCommand,
) (application.NotificationAppMessageReceipt, error) {
	if c == nil || c.http == nil || c.credentials == nil {
		return application.NotificationAppMessageReceipt{}, fmt.Errorf("notification command client is not initialized")
	}
	body, err := json.Marshal(createAppMessageRequest{
		UserID:      command.UserID,
		MessageType: command.MessageType,
		Source:      command.Source,
		SourceID:    command.SourceID,
		Destination: appMessageDestinationRequest(command.Destination),
		Title:       command.Title,
		Summary:     command.Summary,
		Target: appMessageTargetRequest{
			TargetType: command.Target.TargetType,
			TargetID:   command.Target.TargetID,
			RouteID:    command.Target.RouteID,
			RoutePath:  command.Target.RoutePath,
			Query: appMessageRouteQueryRequest{
				Dimension: command.Target.Dimension,
			},
		},
		Provenance: appMessageProvenanceRequest(command.Provenance),
	})
	if err != nil {
		return application.NotificationAppMessageReceipt{}, fmt.Errorf("encode notification command: %w", err)
	}
	authorization, err := c.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return application.NotificationAppMessageReceipt{}, fmt.Errorf("issue notification service credential: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint, bytes.NewReader(body))
	if err != nil {
		return application.NotificationAppMessageReceipt{}, fmt.Errorf("build notification command request: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", strings.TrimSpace(command.IdempotencyKey))
	response, err := c.http.Do(request)
	if err != nil {
		return application.NotificationAppMessageReceipt{}, fmt.Errorf("execute notification command: %w", err)
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, responseBodyLimit))
	if err != nil {
		return application.NotificationAppMessageReceipt{}, fmt.Errorf("read notification command response: %w", err)
	}
	if response.StatusCode != http.StatusCreated {
		return application.NotificationAppMessageReceipt{}, decodeRuntimeFailure(response.StatusCode, raw)
	}
	var message appMessageResponse
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&message); err != nil {
		return application.NotificationAppMessageReceipt{}, fmt.Errorf("decode notification command response: %w", err)
	}
	if strings.TrimSpace(message.MessageID) == "" {
		return application.NotificationAppMessageReceipt{}, fmt.Errorf("notification command response is missing messageId")
	}
	return application.NotificationAppMessageReceipt{MessageID: message.MessageID}, nil
}

func decodeRuntimeFailure(status int, raw []byte) error {
	var response rterr.ErrorResponse
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&response); err != nil {
		return fmt.Errorf("notification service status %d returned invalid RuntimeFailure: %w", status, err)
	}
	code, err := rterr.ParseCode(response.Code)
	if err != nil {
		return fmt.Errorf("notification service status %d returned invalid error code: %w", status, err)
	}
	return rterr.NewAppError(code, response.UserMessage, response.DebugMessage).
		WithRecovery(response.Recovery.Action, response.Recovery.AfterSeconds)
}

type createAppMessageRequest struct {
	UserID      string                       `json:"userId"`
	MessageType string                       `json:"messageType"`
	Source      string                       `json:"source"`
	SourceID    string                       `json:"sourceId"`
	Destination appMessageDestinationRequest `json:"destination"`
	Title       string                       `json:"title"`
	Summary     string                       `json:"summary"`
	Target      appMessageTargetRequest      `json:"target"`
	Provenance  appMessageProvenanceRequest  `json:"provenance"`
}

type appMessageDestinationRequest struct {
	Type string `json:"type"`
	ID   string `json:"id"`
}

type appMessageTargetRequest struct {
	TargetType string                      `json:"targetType"`
	TargetID   string                      `json:"targetId"`
	RouteID    string                      `json:"routeId,omitempty"`
	RoutePath  string                      `json:"routePath,omitempty"`
	Query      appMessageRouteQueryRequest `json:"query"`
}

type appMessageRouteQueryRequest struct {
	Dimension string `json:"dimension,omitempty"`
}

type appMessageProvenanceRequest struct {
	Personalized    bool     `json:"personalized"`
	InterestTags    []string `json:"interestTags"`
	MatchedSegments []string `json:"matchedSegments"`
	LifecycleStage  string   `json:"lifecycleStage"`
}

type appMessageResponse struct {
	MessageID   string                        `json:"messageId"`
	UserID      string                        `json:"userId"`
	MessageType string                        `json:"messageType"`
	Source      string                        `json:"source"`
	SourceID    string                        `json:"sourceId"`
	Destination appMessageDestinationResponse `json:"destination"`
	Title       string                        `json:"title"`
	Summary     string                        `json:"summary"`
	Target      appMessageTargetResponse      `json:"target"`
	Read        bool                          `json:"read"`
	CreatedAt   string                        `json:"createdAt"`
	DeliveredAt *string                       `json:"deliveredAt,omitempty"`
	AckedAt     *string                       `json:"ackedAt,omitempty"`
	ReadAt      *string                       `json:"readAt,omitempty"`
}

type appMessageDestinationResponse struct {
	Type string `json:"type"`
	ID   string `json:"id"`
}

type appMessageTargetResponse struct {
	TargetType string                       `json:"targetType"`
	TargetID   string                       `json:"targetId"`
	RouteID    string                       `json:"routeId,omitempty"`
	RoutePath  string                       `json:"routePath,omitempty"`
	Query      appMessageRouteQueryResponse `json:"query"`
}

type appMessageRouteQueryResponse struct {
	Dimension string `json:"dimension,omitempty"`
}
