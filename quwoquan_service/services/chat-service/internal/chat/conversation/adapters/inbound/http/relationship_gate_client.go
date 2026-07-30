package http

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

type UserRelationshipGate struct {
	baseURL       string
	client        *http.Client
	authorization rtauth.DelegatedPersonaAuthorizationProvider
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

// NewAuthorizedUserRelationshipGate creates the production relationship
// boundary. The delegated credential binds every capability check to the
// caller's trusted persona; X-Client-User-Id alone is intentionally not a
// trusted cross-service identity.
func NewAuthorizedUserRelationshipGate(
	baseURL string,
	client *http.Client,
	authorization rtauth.DelegatedPersonaAuthorizationProvider,
) (*UserRelationshipGate, error) {
	if authorization == nil {
		return nil, fmt.Errorf("delegated relationship authorization is required")
	}
	gate := NewUserRelationshipGate(baseURL, client)
	gate.authorization = authorization
	return gate, nil
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
		"%s/user/personas/%s/relationship/capability",
		g.baseURL,
		url.PathEscape(strings.TrimSpace(targetID)),
	)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return application.RelationshipCapability{}, err
	}
	req.Header.Set("X-Client-User-Id", strings.TrimSpace(viewerID))
	if g.authorization != nil {
		header, err := g.authorization.AuthorizationHeaderForPersona(ctx, viewerID)
		if err != nil {
			return application.RelationshipCapability{}, fmt.Errorf(
				"authorize relationship capability request: %w",
				err,
			)
		}
		req.Header.Set("Authorization", header)
	}

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
