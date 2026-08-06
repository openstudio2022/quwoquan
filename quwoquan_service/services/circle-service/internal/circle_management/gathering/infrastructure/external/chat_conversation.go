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

func (port *ChatConversationPort) EnsureGatheringConversation(
	ctx context.Context,
	command ports.EnsureGatheringConversationCommand,
) (string, error) {
	var response struct {
		ConversationID string `json:"conversationId"`
	}
	err := port.put(
		ctx,
		"/internal/chat/gathering-conversations/"+
			url.PathEscape(strings.TrimSpace(command.GatheringID)),
		command.SourceEventID,
		map[string]any{
			"sourceEventId":  command.SourceEventID,
			"sourceVersion":  command.SourceVersion,
			"ownerPersonaId": command.OwnerPersonaID,
			"title":          command.Title,
			"accessMode":     command.AccessMode,
			"postingPolicy":  command.PostingPolicy,
		},
		&response,
	)
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(response.ConversationID) == "" {
		return "", fmt.Errorf("Chat Gathering projection returned no conversationId")
	}
	return strings.TrimSpace(response.ConversationID), nil
}

func (port *ChatConversationPort) ProjectGatheringMembership(
	ctx context.Context,
	command ports.ProjectGatheringMembershipCommand,
) error {
	path := "/internal/chat/gathering-conversations/" +
		url.PathEscape(strings.TrimSpace(command.GatheringID)) +
		"/members/" + url.PathEscape(strings.TrimSpace(command.PersonaID))
	return port.put(ctx, path, command.SourceEventID, map[string]any{
		"sourceEventId": command.SourceEventID,
		"sourceVersion": command.SourceVersion,
		"sourceType":    command.SourceType,
		"state":         command.State,
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
