package external

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

const defaultChatCommandTimeout = 2 * time.Second

type ChatConversationPort struct {
	baseURL     *url.URL
	httpClient  *http.Client
	credentials rtauth.ServiceAuthorizationProvider
}

func NewChatConversationPort(
	rawBaseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
	httpClient *http.Client,
) (*ChatConversationPort, error) {
	baseURL, err := requireHTTPBaseURL("CHAT_SERVICE_BASE_URL", rawBaseURL)
	if err != nil {
		return nil, err
	}
	if credentials == nil {
		return nil, fmt.Errorf("Gathering Chat port requires service authorization")
	}
	if httpClient == nil {
		httpClient = &http.Client{Timeout: defaultChatCommandTimeout}
	}
	return &ChatConversationPort{
		baseURL: baseURL, httpClient: httpClient, credentials: credentials,
	}, nil
}

func (port *ChatConversationPort) EnsureGroupConversation(
	ctx context.Context,
	gatheringID string,
	title string,
	ownerPersonaID string,
	maxGroupSize int64,
	operationKey string,
) (string, error) {
	var response struct {
		ConversationID string `json:"conversationId"`
	}
	err := port.put(ctx, "/internal/chat/gathering-conversations/"+url.PathEscape(strings.TrimSpace(gatheringID)), operationKey, map[string]any{
		"sourceEventId": operationKey, "ownerPersonaId": ownerPersonaID,
		"title": title, "maxGroupSize": maxGroupSize,
	}, &response)
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(response.ConversationID) == "" {
		return "", fmt.Errorf("Chat Gathering projection returned no conversationId")
	}
	return strings.TrimSpace(response.ConversationID), nil
}

func (port *ChatConversationPort) ProjectParticipant(
	ctx context.Context,
	gatheringID string,
	ownerPersonaID string,
	personaID string,
	state string,
	sourceVersion int64,
	operationKey string,
) error {
	path := "/internal/chat/gathering-conversations/" + url.PathEscape(strings.TrimSpace(gatheringID)) +
		"/members/" + url.PathEscape(strings.TrimSpace(personaID))
	return port.put(ctx, path, operationKey, map[string]any{
		"sourceEventId": operationKey, "sourceVersion": sourceVersion,
		"ownerPersonaId": ownerPersonaID, "state": state,
	}, nil)
}

func (port *ChatConversationPort) put(
	ctx context.Context,
	path string,
	operationKey string,
	body any,
	responseTarget any,
) error {
	encoded, err := json.Marshal(body)
	if err != nil {
		return err
	}
	targetURL := *port.baseURL
	escapedPath := strings.TrimRight(targetURL.EscapedPath(), "/") + path
	decodedPath, err := url.PathUnescape(escapedPath)
	if err != nil {
		return err
	}
	targetURL.Path = decodedPath
	targetURL.RawPath = escapedPath
	request, err := http.NewRequestWithContext(ctx, http.MethodPut, targetURL.String(), bytes.NewReader(encoded))
	if err != nil {
		return err
	}
	authorization, err := port.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return err
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", strings.TrimSpace(operationKey))
	response, err := port.httpClient.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		payload, _ := io.ReadAll(io.LimitReader(response.Body, 4096))
		return fmt.Errorf("Chat Gathering projection returned status %d: %s", response.StatusCode, strings.TrimSpace(string(payload)))
	}
	if responseTarget == nil || response.StatusCode == http.StatusNoContent {
		return nil
	}
	if err := json.NewDecoder(io.LimitReader(response.Body, 1<<20)).Decode(responseTarget); err != nil {
		return fmt.Errorf("decode Chat Gathering projection response: %w", err)
	}
	return nil
}

var _ ports.ConversationPort = (*ChatConversationPort)(nil)
