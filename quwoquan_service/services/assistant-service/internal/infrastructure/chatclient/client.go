// Package chatclient implements assistant-service egress to chat-service.
package chatclient

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"quwoquan_service/services/assistant-service/internal/application"
)

type Client struct {
	baseURL string
	http    *http.Client
}

func NewClient(httpClient *http.Client, baseURL string) *Client {
	return &Client{
		baseURL: strings.TrimRight(strings.TrimSpace(baseURL), "/"),
		http:    httpClient,
	}
}

func (c *Client) ListMessages(ctx context.Context, conversationID string, beforeSeq int64, limit int) ([]application.ChatGroundingMessage, error) {
	if c == nil || c.http == nil || c.baseURL == "" {
		return nil, fmt.Errorf("chat grounding client not configured")
	}
	query := url.Values{}
	if beforeSeq > 0 {
		query.Set("beforeSeq", strconv.FormatInt(beforeSeq, 10))
	}
	if limit > 0 {
		query.Set("limit", strconv.Itoa(limit))
	}
	endpoint := c.baseURL + "/chat/conversations/" + url.PathEscape(strings.TrimSpace(conversationID)) + "/messages"
	if encoded := query.Encode(); encoded != "" {
		endpoint += "?" + encoded
	}
	var payload struct {
		Items []messageWire `json:"items"`
	}
	if err := c.doJSON(ctx, http.MethodGet, endpoint, nil, &payload, "assistant"); err != nil {
		return nil, err
	}
	out := make([]application.ChatGroundingMessage, 0, len(payload.Items))
	for _, item := range payload.Items {
		out = append(out, application.ChatGroundingMessage{
			MessageID:  firstNonEmpty(item.MessageID, item.ID),
			Seq:        item.Seq,
			SenderID:   firstNonEmpty(item.SenderID, item.SenderSubAccountID),
			SenderName: item.SenderDisplayNameSnapshot,
			Type:       item.Type,
			Content:    item.Content,
			Mentions:   item.Mentions,
		})
	}
	return out, nil
}

func (c *Client) ListMembers(ctx context.Context, conversationID string, limit int) ([]application.ChatGroundingMember, error) {
	if c == nil || c.http == nil || c.baseURL == "" {
		return nil, fmt.Errorf("chat grounding client not configured")
	}
	query := url.Values{}
	if limit > 0 {
		query.Set("limit", strconv.Itoa(limit))
	}
	endpoint := c.baseURL + "/chat/conversations/" + url.PathEscape(strings.TrimSpace(conversationID)) + "/members"
	if encoded := query.Encode(); encoded != "" {
		endpoint += "?" + encoded
	}
	var payload struct {
		Items []memberWire `json:"items"`
	}
	if err := c.doJSON(ctx, http.MethodGet, endpoint, nil, &payload, "assistant"); err != nil {
		return nil, err
	}
	out := make([]application.ChatGroundingMember, 0, len(payload.Items))
	for _, item := range payload.Items {
		out = append(out, application.ChatGroundingMember{
			UserID:           item.UserID,
			DisplayName:      item.DisplayName,
			MemberType:       item.MemberType,
			AssistantSkillID: item.AssistantSkillID,
		})
	}
	return out, nil
}

func (c *Client) SendMessage(ctx context.Context, req application.ChatGroundingSendMessageRequest) error {
	if c == nil || c.http == nil || c.baseURL == "" {
		return fmt.Errorf("chat grounding client not configured")
	}
	body := map[string]any{
		"type":               req.Type,
		"content":            req.Content,
		"clientMsgId":        req.ClientMsgID,
		"senderSubAccountId": req.SenderID,
	}
	endpoint := c.baseURL + "/chat/conversations/" + url.PathEscape(strings.TrimSpace(req.ConversationID)) + "/messages"
	return c.doJSON(ctx, http.MethodPost, endpoint, body, nil, req.SenderID)
}

func (c *Client) doJSON(ctx context.Context, method, endpoint string, body map[string]any, out any, actorID string) error {
	var reader *bytes.Reader
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("chat client marshal body: %w", err)
		}
		reader = bytes.NewReader(raw)
	} else {
		reader = bytes.NewReader(nil)
	}
	req, err := http.NewRequestWithContext(ctx, method, endpoint, reader)
	if err != nil {
		return fmt.Errorf("chat client build request: %w", err)
	}
	req.Header.Set("X-Client-User-Id", firstNonEmpty(actorID, "assistant"))
	req.Header.Set("X-Client-Sub-Account-Id", firstNonEmpty(actorID, "assistant"))
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("chat client request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return fmt.Errorf("chat client status %d", resp.StatusCode)
	}
	if out == nil {
		return nil
	}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return fmt.Errorf("chat client decode response: %w", err)
	}
	return nil
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

type messageWire struct {
	ID                        string   `json:"id"`
	MessageID                 string   `json:"messageId"`
	Seq                       int64    `json:"seq"`
	SenderID                  string   `json:"senderId"`
	SenderSubAccountID        string   `json:"senderSubAccountId"`
	SenderDisplayNameSnapshot string   `json:"senderDisplayNameSnapshot"`
	Type                      string   `json:"type"`
	Content                   string   `json:"content"`
	Mentions                  []string `json:"mentions"`
}

type memberWire struct {
	UserID           string `json:"userId"`
	DisplayName      string `json:"displayName"`
	MemberType       string `json:"memberType"`
	AssistantSkillID string `json:"assistantSkillId"`
}
