// Package authority implements the typed Chat/Circle authority boundary for
// SkillSurfacePlacement. It never mirrors membership state into Assistant.
package authority

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	bindingdescriptor "quwoquan_service/services/assistant-service/generated/assistant/skill_surface_placement"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
)

const (
	FirstPartyHTTPAuthorityAdapterID = "ext.first_party.http_authority"
	chatMemberOperation              = "chat.conversation_membership.ListMembers"
	circleMemberOperation            = "circle.circle_membership.GetMyCircleMembership"
	authorityResponseLimit           = 1 << 20
	conversationMemberLimit          = 100
)

var requiredAuthorityBindings = map[string]string{
	"chat.conversation.membership.read": "ASSISTANT_CHAT_BASE_URL",
	"circle.membership.self.read":       "ASSISTANT_CIRCLE_BASE_URL",
}

// RequireEnvironmentBindings keeps the production wiring on the generated
// Capability/Adapter/Binding track. The typed client still consumes canonical
// service runtime configuration; this preflight only validates the selected
// adapter and its endpoint ownership and never introduces a second resolver.
func RequireEnvironmentBindings(environment string) error {
	for capabilityID, endpointKey := range requiredAuthorityBindings {
		binding, found := bindingdescriptor.CompiledBindingFor(capabilityID)
		if !found || binding.State != "enabled" {
			return fmt.Errorf("authority binding %s is not enabled for %s", capabilityID, environment)
		}
		if binding.AdapterID != FirstPartyHTTPAuthorityAdapterID {
			return fmt.Errorf("authority binding %s selected an unsupported adapter", capabilityID)
		}
		if binding.EndpointEnvironmentKeys["base"] != endpointKey ||
			len(binding.EndpointEnvironmentKeys) != 1 ||
			len(binding.SecretEnvironmentKeys) != 0 ||
			binding.TimeoutMilliseconds <= 0 {
			return fmt.Errorf("authority binding %s is incomplete", capabilityID)
		}
	}
	return nil
}

type Client struct {
	chatBaseURL      *url.URL
	circleBaseURL    *url.URL
	chatHTTP         *http.Client
	circleHTTP       *http.Client
	authorization    rtauth.DelegatedPersonaAuthorizationProvider
	chatMemberPath   string
	circleMemberPath string
}

func NewClient(
	chatBaseURL string,
	circleBaseURL string,
	chatHTTP *http.Client,
	circleHTTP *http.Client,
	authorization rtauth.DelegatedPersonaAuthorizationProvider,
) (*Client, error) {
	chatURL, err := parseBaseURL(chatBaseURL, "chat-service")
	if err != nil {
		return nil, err
	}
	circleURL, err := parseBaseURL(circleBaseURL, "circle-service")
	if err != nil {
		return nil, err
	}
	if chatHTTP == nil || circleHTTP == nil || authorization == nil {
		return nil, errors.New("surface authority HTTP clients and delegated authorization are required")
	}
	chatPath, err := operationPath(chatMemberOperation)
	if err != nil {
		return nil, err
	}
	circlePath, err := operationPath(circleMemberOperation)
	if err != nil {
		return nil, err
	}
	return &Client{
		chatBaseURL:      chatURL,
		circleBaseURL:    circleURL,
		chatHTTP:         chatHTTP,
		circleHTTP:       circleHTTP,
		authorization:    authorization,
		chatMemberPath:   chatPath,
		circleMemberPath: circlePath,
	}, nil
}

func (client *Client) RequireMember(
	ctx context.Context,
	personaID string,
	surfaceKind string,
	surfaceID string,
) error {
	authority, err := client.resolve(ctx, personaID, surfaceKind, surfaceID)
	if err != nil {
		return err
	}
	if !authority.member {
		return model.ErrForbidden
	}
	return nil
}

func (client *Client) RequireAdmin(
	ctx context.Context,
	personaID string,
	surfaceKind string,
	surfaceID string,
) error {
	authority, err := client.resolve(ctx, personaID, surfaceKind, surfaceID)
	if err != nil {
		return err
	}
	if !authority.member || !authority.admin {
		return model.ErrForbidden
	}
	return nil
}

type resolvedAuthority struct {
	member bool
	admin  bool
}

func (client *Client) resolve(
	ctx context.Context,
	personaID string,
	surfaceKind string,
	surfaceID string,
) (resolvedAuthority, error) {
	personaID = strings.TrimSpace(personaID)
	surfaceKind = strings.TrimSpace(surfaceKind)
	surfaceID = strings.TrimSpace(surfaceID)
	if client == nil || personaID == "" || surfaceID == "" {
		return resolvedAuthority{}, model.ErrAuthorityUnavailable
	}
	switch surfaceKind {
	case model.SurfaceConversation:
		return client.resolveConversation(ctx, personaID, surfaceID)
	case model.SurfaceCircle:
		return client.resolveCircle(ctx, personaID, surfaceID)
	default:
		return resolvedAuthority{}, model.ErrForbidden
	}
}

func (client *Client) resolveConversation(
	ctx context.Context,
	personaID string,
	conversationID string,
) (resolvedAuthority, error) {
	requestURL, err := buildOperationURL(
		client.chatBaseURL,
		client.chatMemberPath,
		map[string]string{"conversationId": conversationID},
	)
	if err != nil {
		return resolvedAuthority{}, model.ErrAuthorityUnavailable
	}
	query := requestURL.Query()
	query.Set("query", personaID)
	query.Set("limit", strconv.Itoa(conversationMemberLimit))
	requestURL.RawQuery = query.Encode()
	var response conversationMembersWire
	if err := client.getJSON(ctx, client.chatHTTP, requestURL, personaID, &response); err != nil {
		return resolvedAuthority{}, err
	}
	for _, member := range response.Items {
		if strings.TrimSpace(member.UserID) != personaID ||
			strings.TrimSpace(member.MemberType) == "assistant" {
			continue
		}
		role := strings.TrimSpace(member.Role)
		return resolvedAuthority{
			member: true,
			admin:  role == "owner" || role == "admin",
		}, nil
	}
	return resolvedAuthority{}, model.ErrForbidden
}

func (client *Client) resolveCircle(
	ctx context.Context,
	personaID string,
	circleID string,
) (resolvedAuthority, error) {
	requestURL, err := buildOperationURL(
		client.circleBaseURL,
		client.circleMemberPath,
		map[string]string{"circleId": circleID},
	)
	if err != nil {
		return resolvedAuthority{}, model.ErrAuthorityUnavailable
	}
	var response circleMembershipWire
	if err := client.getJSON(ctx, client.circleHTTP, requestURL, personaID, &response); err != nil {
		return resolvedAuthority{}, err
	}
	if strings.TrimSpace(response.CircleID) != circleID ||
		strings.TrimSpace(response.PersonaID) != personaID ||
		strings.TrimSpace(response.State) != "active" {
		return resolvedAuthority{}, model.ErrForbidden
	}
	role := strings.TrimSpace(response.Role)
	return resolvedAuthority{
		member: true,
		admin:  role == "owner" || role == "admin",
	}, nil
}

func (client *Client) getJSON(
	ctx context.Context,
	httpClient *http.Client,
	target *url.URL,
	personaID string,
	destination any,
) error {
	authorization, err := client.authorization.AuthorizationHeaderForPersona(ctx, personaID)
	if err != nil {
		return model.ErrAuthorityUnavailable
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return model.ErrAuthorityUnavailable
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	response, err := httpClient.Do(request)
	if err != nil {
		return model.ErrAuthorityUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusForbidden ||
		response.StatusCode == http.StatusUnauthorized ||
		response.StatusCode == http.StatusNotFound {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 8<<10))
		return model.ErrForbidden
	}
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 8<<10))
		return model.ErrAuthorityUnavailable
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, authorityResponseLimit+1))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		return model.ErrAuthorityUnavailable
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return model.ErrAuthorityUnavailable
	}
	return nil
}

type conversationMembersWire struct {
	Items      []conversationMemberWire `json:"items"`
	NextCursor string                   `json:"nextCursor,omitempty"`
}

type conversationMemberWire struct {
	UserID        string          `json:"userId"`
	UserHandle    string          `json:"userHandle"`
	DisplayName   string          `json:"displayName"`
	AvatarURL     string          `json:"avatarUrl"`
	Role          string          `json:"role"`
	MemberType    string          `json:"memberType"`
	JoinedAt      json.RawMessage `json:"joinedAt"`
	IsCurrentUser bool            `json:"isCurrentUser"`
}

type circleMembershipWire struct {
	MembershipID string          `json:"membershipId"`
	Version      int64           `json:"version"`
	CircleID     string          `json:"circleId"`
	PersonaID    string          `json:"personaId"`
	Role         string          `json:"role"`
	State        string          `json:"state"`
	JoinedAt     json.RawMessage `json:"joinedAt"`
	LeftAt       json.RawMessage `json:"leftAt"`
	LastActiveAt json.RawMessage `json:"lastActiveAt"`
	Contribution int64           `json:"contribution"`
	CreatedAt    json.RawMessage `json:"createdAt"`
	UpdatedAt    json.RawMessage `json:"updatedAt"`
}

func parseBaseURL(raw string, service string) (*url.URL, error) {
	parsed, err := url.Parse(strings.TrimRight(strings.TrimSpace(raw), "/"))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") {
		return nil, fmt.Errorf("%s base URL must be absolute http or https", service)
	}
	return parsed, nil
}

func operationPath(operationID string) (string, error) {
	domain := strings.SplitN(operationID, ".", 2)[0]
	for _, descriptor := range operationsecurity.ForDomain(domain) {
		if descriptor.CanonicalOperationID != operationID {
			continue
		}
		if descriptor.Method != http.MethodGet ||
			!strings.HasPrefix(descriptor.PathTemplate, "/") {
			return "", fmt.Errorf("surface authority operation %s is not a GET route", operationID)
		}
		return descriptor.PathTemplate, nil
	}
	return "", fmt.Errorf("surface authority operation %s is absent", operationID)
}

func buildOperationURL(
	base *url.URL,
	pathTemplate string,
	pathValues map[string]string,
) (*url.URL, error) {
	if base == nil {
		return nil, errors.New("surface authority base URL is required")
	}
	path := pathTemplate
	for name, value := range pathValues {
		value = strings.TrimSpace(value)
		if value == "" {
			return nil, errors.New("surface authority path identity is required")
		}
		path = strings.ReplaceAll(path, "{"+name+"}", url.PathEscape(value))
	}
	if strings.Contains(path, "{") || !strings.HasPrefix(path, "/") {
		return nil, errors.New("surface authority path template is invalid")
	}
	target := *base
	target.Path = strings.TrimRight(target.Path, "/") + path
	target.RawQuery = ""
	return &target, nil
}
