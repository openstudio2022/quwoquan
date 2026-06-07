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

	"quwoquan_service/services/user-service/internal/application"
)

type ChatServiceClient struct {
	baseURL string
	client  *http.Client
}

func NewChatServiceClient(baseURL string, client *http.Client) *ChatServiceClient {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if client == nil {
		client = &http.Client{Timeout: 3 * time.Second}
	}
	return &ChatServiceClient{baseURL: baseURL, client: client}
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
	req.Header.Set("X-Internal-Service", "user-service")
	req.Header.Set("X-Client-User-Id", creatorID)

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
	req.Header.Set("X-Internal-Service", "user-service")
	req.Header.Set("X-Client-User-Id", subAccountA)

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

var _ application.ConversationGateway = (*ChatServiceClient)(nil)
