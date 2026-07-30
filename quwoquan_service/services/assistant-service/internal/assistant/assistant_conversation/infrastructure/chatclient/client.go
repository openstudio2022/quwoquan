// Package chatclient implements assistant-service egress to chat-service.
package chatclient

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/generated/serviceclients"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
)

const responseBodyLimit = 1 << 20

type AuthorizationProvider interface {
	AuthorizationHeader(context.Context) (string, error)
}

type Client struct {
	baseURL       string
	http          *http.Client
	authorization AuthorizationProvider
}

func NewClient(
	httpClient *http.Client,
	baseURL string,
	authorization AuthorizationProvider,
) (*Client, error) {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	parsed, err := url.Parse(baseURL)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" ||
		parsed.User != nil {
		return nil, errors.New(
			"chat service base URL must be absolute http or https",
		)
	}
	if httpClient == nil || authorization == nil {
		return nil, errors.New(
			"chat observed client and authorization are required",
		)
	}
	return &Client{
		baseURL:       baseURL,
		http:          httpClient,
		authorization: authorization,
	}, nil
}

func (c *Client) ResolveAssistantDeliveryMembership(
	ctx context.Context,
	conversationID string,
	creatorPersonaID string,
	assistantMemberID string,
	assistantSkillID string,
) (bool, error) {
	if c == nil || c.http == nil || c.baseURL == "" {
		return false, fmt.Errorf("chat grounding client not configured")
	}
	query := url.Values{}
	query.Set("creatorPersonaId", strings.TrimSpace(creatorPersonaID))
	if assistantMemberID = strings.TrimSpace(assistantMemberID); assistantMemberID != "" {
		query.Set("assistantMemberId", assistantMemberID)
	}
	query.Set("assistantSkillId", strings.TrimSpace(assistantSkillID))
	endpoint := c.baseURL +
		serviceclients.ChatResolveAssistantDeliveryMembershipPath(
			conversationID,
		) + "?" + query.Encode()
	var payload assistantDeliveryMembershipWire
	if err := c.doJSON(
		ctx,
		http.MethodGet,
		endpoint,
		nil,
		func(raw []byte) error {
			return decodeStrict(raw, &payload)
		},
	); err != nil {
		return false, err
	}
	return payload.CreatorMember && payload.AssistantSkillMember, nil
}

func (c *Client) ListMessages(
	ctx context.Context,
	conversationID string,
	creatorPersonaID string,
	assistantSkillID string,
	beforeSeq int64,
	limit int,
) ([]ports.ChatGroundingMessage, error) {
	if c == nil || c.http == nil || c.baseURL == "" {
		return nil, fmt.Errorf("chat grounding client not configured")
	}
	query := url.Values{}
	query.Set("creatorPersonaId", strings.TrimSpace(creatorPersonaID))
	query.Set("assistantSkillId", strings.TrimSpace(assistantSkillID))
	if beforeSeq > 0 {
		query.Set("beforeSeq", strconv.FormatInt(beforeSeq, 10))
	}
	if limit > 0 {
		query.Set("limit", strconv.Itoa(limit))
	}
	endpoint := c.baseURL +
		serviceclients.ChatListAssistantGroundingMessagesPath(conversationID)
	if encoded := query.Encode(); encoded != "" {
		endpoint += "?" + encoded
	}
	var payload struct {
		Items []messageWire `json:"items"`
	}
	if err := c.doJSON(
		ctx,
		http.MethodGet,
		endpoint,
		nil,
		func(raw []byte) error {
			return decodeStrict(raw, &payload)
		},
	); err != nil {
		return nil, err
	}
	out := make([]ports.ChatGroundingMessage, 0, len(payload.Items))
	for _, item := range payload.Items {
		out = append(out, ports.ChatGroundingMessage{
			MessageID:  firstNonEmpty(item.MessageID, item.ID),
			Seq:        item.Seq,
			SenderID:   firstNonEmpty(item.SenderID, item.SenderPersonaID),
			SenderName: item.SenderDisplayNameSnapshot,
			Type:       item.Type,
			Content:    item.Content,
			Mentions:   item.Mentions,
		})
	}
	return out, nil
}

func (c *Client) SendMessage(
	ctx context.Context,
	req ports.ChatGroundingSendMessageRequest,
) error {
	if c == nil || c.http == nil || c.baseURL == "" {
		return fmt.Errorf("chat grounding client not configured")
	}
	body, err := json.Marshal(sendMessageWire{
		Type:        req.Type,
		Content:     req.Content,
		ClientMsgID: req.ClientMsgID,
	})
	if err != nil {
		return fmt.Errorf("chat client marshal body: %w", err)
	}
	query := url.Values{}
	query.Set(
		"creatorPersonaId",
		strings.TrimSpace(req.CreatorPersonaID),
	)
	query.Set("assistantSkillId", strings.TrimSpace(req.AssistantSkillID))
	endpoint := c.baseURL +
		serviceclients.ChatSendAssistantDeliveryMessagePath(
			req.ConversationID,
		) + "?" + query.Encode()
	return c.doJSON(ctx, http.MethodPost, endpoint, body, nil)
}

func (c *Client) doJSON(
	ctx context.Context,
	method string,
	endpoint string,
	body []byte,
	decode func([]byte) error,
) error {
	reader := bytes.NewReader(body)
	req, err := http.NewRequestWithContext(ctx, method, endpoint, reader)
	if err != nil {
		return fmt.Errorf("chat client build request: %w", err)
	}
	authorization, err := c.authorization.AuthorizationHeader(ctx)
	if err != nil {
		return fmt.Errorf("authorize chat client request: %w", err)
	}
	req.Header.Set("Authorization", authorization)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("chat client request: %w", err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, responseBodyLimit+1))
	if err != nil {
		return fmt.Errorf("chat client read response: %w", err)
	}
	if len(raw) > responseBodyLimit {
		return fmt.Errorf(
			"chat client response exceeds %d bytes",
			responseBodyLimit,
		)
	}
	if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
		return fmt.Errorf("chat client status %d", resp.StatusCode)
	}
	if decode == nil {
		return nil
	}
	if err := decode(raw); err != nil {
		return fmt.Errorf("chat client decode response: %w", err)
	}
	return nil
}

func decodeStrict[T any](raw []byte, target *T) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("trailing JSON content")
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
	ID                        string    `json:"id"`
	MessageID                 string    `json:"messageId"`
	Seq                       int64     `json:"seq"`
	SenderID                  string    `json:"senderId"`
	SenderPersonaID           string    `json:"senderPersonaId"`
	SenderDisplayNameSnapshot string    `json:"senderDisplayNameSnapshot"`
	Type                      string    `json:"type"`
	Content                   string    `json:"content"`
	Mentions                  []string  `json:"mentions"`
	Timestamp                 time.Time `json:"timestamp"`
}

type assistantDeliveryMembershipWire struct {
	CreatorMember        bool `json:"creatorMember"`
	AssistantSkillMember bool `json:"assistantSkillMember"`
}

type sendMessageWire struct {
	Type        string `json:"type"`
	Content     string `json:"content"`
	ClientMsgID string `json:"clientMsgId"`
}
