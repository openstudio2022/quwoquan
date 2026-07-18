package http

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/services/chat-service/internal/application"
)

type UserRelationshipGate struct {
	baseURL string
	client  *http.Client
}

type relationshipCapabilityResponse struct {
	CanCreateDirectConversation bool `json:"canCreateDirectConversation"`
	CanSendMessage              bool `json:"canSendMessage"`
	HasFormalConversation       bool `json:"hasFormalConversation"`
	IsMutual                    bool `json:"isMutual"`
	IsBlocked                   bool `json:"isBlocked"`
	IsBlockedBy                 bool `json:"isBlockedBy"`
}

func NewUserRelationshipGate(baseURL string, client *http.Client) *UserRelationshipGate {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if client == nil {
		client = &http.Client{Timeout: 2 * time.Second}
	}
	return &UserRelationshipGate{baseURL: baseURL, client: client}
}

func (g *UserRelationshipGate) GetCapability(
	ctx context.Context,
	viewerID string,
	targetID string,
) (application.RelationshipCapability, error) {
	if g == nil || g.client == nil || g.baseURL == "" {
		return application.RelationshipCapability{}, nil
	}
	requestURL := fmt.Sprintf(
		"%s/user/sub-accounts/%s/relationship/capability",
		g.baseURL,
		url.PathEscape(strings.TrimSpace(targetID)),
	)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return application.RelationshipCapability{}, err
	}
	req.Header.Set("X-Client-User-Id", strings.TrimSpace(viewerID))

	resp, err := g.client.Do(req)
	if err != nil {
		return application.RelationshipCapability{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return application.RelationshipCapability{}, fmt.Errorf("get relationship capability: status %d", resp.StatusCode)
	}

	var payload relationshipCapabilityResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return application.RelationshipCapability{}, err
	}
	return application.RelationshipCapability{
		CanCreateDirectConversation: payload.CanCreateDirectConversation,
		CanSendMessage:              payload.CanSendMessage,
		HasFormalConversation:       payload.HasFormalConversation,
		IsMutual:                    payload.IsMutual,
		IsBlocked:                   payload.IsBlocked,
		IsBlockedBy:                 payload.IsBlockedBy,
	}, nil
}
