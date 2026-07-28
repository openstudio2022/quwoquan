package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

type ChatServiceClient struct {
	baseURL       string
	client        *http.Client
	authorization rtauth.DelegatedPersonaAuthorizationProvider
}

func NewChatServiceClient(baseURL string, client *http.Client) *ChatServiceClient {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if client == nil {
		client = &http.Client{Timeout: 3 * time.Second}
	}
	return &ChatServiceClient{baseURL: baseURL, client: client}
}

// NewAuthorizedChatServiceClient creates the production boundary for direct
// conversation queries. The delegated persona binds the requested member to a
// verified user-service principal; raw identity headers are not authorization.
func NewAuthorizedChatServiceClient(
	baseURL string,
	client *http.Client,
	authorization rtauth.DelegatedPersonaAuthorizationProvider,
) (*ChatServiceClient, error) {
	if authorization == nil {
		return nil, fmt.Errorf("delegated chat authorization is required")
	}
	resolver := NewChatServiceClient(baseURL, client)
	resolver.authorization = authorization
	return resolver, nil
}

func (c *ChatServiceClient) CreateOrReuseDirect(ctx context.Context, creatorID, peerID string) (string, error) {
	if c == nil || c.baseURL == "" {
		return "", fmt.Errorf("chat service client unavailable")
	}
	payload := map[string]any{
		"creatorId": creatorID,
		"peerId":    peerID,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		c.baseURL+"/internal/chat/conversations/direct",
		bytes.NewReader(body),
	)
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if err := c.authorizeRequest(ctx, req, creatorID); err != nil {
		return "", err
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("create direct conversation: status %d", resp.StatusCode)
	}
	var result struct {
		ConversationID string `json:"conversationId"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return "", err
	}
	if strings.TrimSpace(result.ConversationID) == "" {
		return "", fmt.Errorf("create direct conversation: empty conversationId")
	}
	return result.ConversationID, nil
}

func (c *ChatServiceClient) HasDirectBetween(ctx context.Context, subAccountA, subAccountB string) (bool, error) {
	if c == nil || c.baseURL == "" {
		return false, nil
	}
	query := url.Values{}
	query.Set("memberA", subAccountA)
	query.Set("memberB", subAccountB)
	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		c.baseURL+"/internal/chat/conversations/direct?"+query.Encode(),
		nil,
	)
	if err != nil {
		return false, err
	}
	if err := c.authorizeRequest(ctx, req, subAccountA); err != nil {
		return false, err
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return false, nil
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return false, fmt.Errorf("lookup direct conversation: status %d", resp.StatusCode)
	}
	var result struct {
		Exists bool `json:"exists"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return false, err
	}
	return result.Exists, nil
}

func (c *ChatServiceClient) authorizeRequest(
	ctx context.Context,
	request *http.Request,
	personaID string,
) error {
	if c == nil || c.authorization == nil {
		return fmt.Errorf("chat service delegated authorization unavailable")
	}
	header, err := c.authorization.AuthorizationHeaderForPersona(ctx, personaID)
	if err != nil {
		return fmt.Errorf("authorize direct conversation request: %w", err)
	}
	request.Header.Set("Authorization", header)
	return nil
}

var _ application.ConversationGateway = (*ChatServiceClient)(nil)
