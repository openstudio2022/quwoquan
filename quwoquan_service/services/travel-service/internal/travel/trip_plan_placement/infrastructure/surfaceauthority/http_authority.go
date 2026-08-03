package surfaceauthority

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_placement/domain/ports"
)

const maximumResponseBytes = 256 << 10

type DelegatedAuthorizationProvider interface {
	AuthorizationHeaderForPersona(context.Context, string) (string, error)
}

type HTTPAuthority struct {
	chatBaseURL   *url.URL
	circleBaseURL *url.URL
	chatClient    *http.Client
	circleClient  *http.Client
	authorization DelegatedAuthorizationProvider
}

type conversation struct {
	ID                    string `json:"id"`
	MembersRosterRevision int64  `json:"membersRosterRevision"`
	Status                string `json:"status"`
}

type conversationMemberPage struct {
	Items []struct {
		UserID string `json:"userId"`
		Role   string `json:"role"`
	} `json:"items"`
}

type circleMembership struct {
	Version   int64  `json:"version"`
	CircleID  string `json:"circleId"`
	PersonaID string `json:"personaId"`
	Role      string `json:"role"`
	State     string `json:"state"`
}

type circleDetailEnvelope struct {
	Data struct {
		CircleID string `json:"id"`
		Version  int64  `json:"version"`
		Status   string `json:"status"`
	} `json:"data"`
}

func NewHTTPAuthority(
	chatBaseURL string,
	circleBaseURL string,
	chatClient *http.Client,
	circleClient *http.Client,
	authorization DelegatedAuthorizationProvider,
) (*HTTPAuthority, error) {
	chat, err := parseBaseURL(chatBaseURL)
	if err != nil {
		return nil, fmt.Errorf("Chat surface base URL is invalid")
	}
	circle, err := parseBaseURL(circleBaseURL)
	if err != nil {
		return nil, fmt.Errorf("Circle surface base URL is invalid")
	}
	if chatClient == nil || circleClient == nil || authorization == nil {
		return nil, fmt.Errorf("surface authority clients and authorization are required")
	}
	return &HTTPAuthority{
		chatBaseURL: chat, circleBaseURL: circle,
		chatClient: chatClient, circleClient: circleClient, authorization: authorization,
	}, nil
}

func (authority *HTTPAuthority) RequireAdmin(
	ctx context.Context,
	kind model.SurfaceKind,
	surfaceID string,
	personaID string,
	sourceVersion int64,
) error {
	if sourceVersion <= 0 {
		return model.ErrInvalidArgument
	}
	switch kind {
	case model.SurfaceConversation:
		current, err := authority.readConversation(ctx, surfaceID, personaID)
		if err != nil {
			return err
		}
		if current.MembersRosterRevision != sourceVersion {
			return model.ErrInvalidArgument
		}
		return authority.requireConversationAdmin(ctx, surfaceID, personaID)
	case model.SurfaceCircle:
		circle, err := authority.readCircle(ctx, surfaceID, personaID)
		if err != nil {
			return err
		}
		if circle.Data.Version != sourceVersion {
			return model.ErrInvalidArgument
		}
		membership, err := authority.readCircleMembership(ctx, surfaceID, personaID)
		if err != nil {
			return err
		}
		role := strings.ToLower(strings.TrimSpace(membership.Role))
		if role != "owner" && role != "admin" {
			return model.ErrPermissionDenied
		}
		return nil
	default:
		return model.ErrInvalidArgument
	}
}

func (authority *HTTPAuthority) readCircle(
	ctx context.Context,
	circleID string,
	personaID string,
) (circleDetailEnvelope, error) {
	var result circleDetailEnvelope
	if err := authority.getDelegatedJSON(
		ctx, authority.circleBaseURL, authority.circleClient, personaID,
		"circles/"+url.PathEscape(strings.TrimSpace(circleID)), nil, &result,
	); err != nil {
		return circleDetailEnvelope{}, err
	}
	if strings.TrimSpace(result.Data.CircleID) != strings.TrimSpace(circleID) ||
		strings.ToLower(strings.TrimSpace(result.Data.Status)) != "active" {
		return circleDetailEnvelope{}, model.ErrPermissionDenied
	}
	return result, nil
}

func (authority *HTTPAuthority) RequireMember(
	ctx context.Context,
	kind model.SurfaceKind,
	surfaceID string,
	personaID string,
) error {
	switch kind {
	case model.SurfaceConversation:
		_, err := authority.readConversation(ctx, surfaceID, personaID)
		return err
	case model.SurfaceCircle:
		_, err := authority.readCircleMembership(ctx, surfaceID, personaID)
		return err
	default:
		return model.ErrInvalidArgument
	}
}

func (authority *HTTPAuthority) readConversation(
	ctx context.Context,
	conversationID string,
	personaID string,
) (conversation, error) {
	var result conversation
	err := authority.getDelegatedJSON(
		ctx, authority.chatBaseURL, authority.chatClient, personaID,
		"chat/conversations/"+url.PathEscape(strings.TrimSpace(conversationID)), nil, &result,
	)
	if err != nil {
		return conversation{}, err
	}
	if strings.TrimSpace(result.ID) != strings.TrimSpace(conversationID) ||
		strings.ToLower(strings.TrimSpace(result.Status)) != "active" {
		return conversation{}, model.ErrPermissionDenied
	}
	return result, nil
}

func (authority *HTTPAuthority) requireConversationAdmin(
	ctx context.Context,
	conversationID string,
	personaID string,
) error {
	query := url.Values{}
	query.Set("limit", strconv.Itoa(20))
	query.Set("query", strings.TrimSpace(personaID))
	query.Set("sort", "joined_asc")
	var page conversationMemberPage
	if err := authority.getDelegatedJSON(
		ctx, authority.chatBaseURL, authority.chatClient, personaID,
		"chat/conversations/"+url.PathEscape(strings.TrimSpace(conversationID))+"/members",
		query,
		&page,
	); err != nil {
		return err
	}
	for _, member := range page.Items {
		role := strings.ToLower(strings.TrimSpace(member.Role))
		if strings.TrimSpace(member.UserID) == strings.TrimSpace(personaID) &&
			(role == "owner" || role == "admin") {
			return nil
		}
	}
	return model.ErrPermissionDenied
}

func (authority *HTTPAuthority) readCircleMembership(
	ctx context.Context,
	circleID string,
	personaID string,
) (circleMembership, error) {
	var result circleMembership
	if err := authority.getDelegatedJSON(
		ctx, authority.circleBaseURL, authority.circleClient, personaID,
		"circles/"+url.PathEscape(strings.TrimSpace(circleID))+"/memberships/self", nil, &result,
	); err != nil {
		return circleMembership{}, err
	}
	if strings.TrimSpace(result.CircleID) != strings.TrimSpace(circleID) ||
		strings.TrimSpace(result.PersonaID) != strings.TrimSpace(personaID) ||
		strings.ToLower(strings.TrimSpace(result.State)) != "active" {
		return circleMembership{}, model.ErrPermissionDenied
	}
	return result, nil
}

func (authority *HTTPAuthority) getDelegatedJSON(
	ctx context.Context,
	baseURL *url.URL,
	client *http.Client,
	personaID string,
	path string,
	query url.Values,
	destination any,
) error {
	if authority == nil || baseURL == nil || client == nil || authority.authorization == nil ||
		strings.TrimSpace(personaID) == "" || strings.TrimSpace(path) == "" {
		return ports.ErrSurfaceUnavailable
	}
	header, err := authority.authorization.AuthorizationHeaderForPersona(ctx, strings.TrimSpace(personaID))
	if err != nil || strings.TrimSpace(header) == "" {
		return ports.ErrSurfaceUnavailable
	}
	target := baseURL.ResolveReference(&url.URL{Path: path})
	if query != nil {
		target.RawQuery = query.Encode()
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return ports.ErrSurfaceUnavailable
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Authorization", header)
	response, err := client.Do(request)
	if err != nil {
		return ports.ErrSurfaceUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode >= http.StatusBadRequest && response.StatusCode < http.StatusInternalServerError {
		return model.ErrPermissionDenied
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return ports.ErrSurfaceUnavailable
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, maximumResponseBytes+1))
	if err != nil || len(body) == 0 || len(body) > maximumResponseBytes {
		return ports.ErrSurfaceUnavailable
	}
	if err := json.Unmarshal(body, destination); err != nil {
		return ports.ErrSurfaceUnavailable
	}
	return nil
}

func parseBaseURL(raw string) (*url.URL, error) {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || parsed == nil || parsed.Host == "" ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.User != nil ||
		parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, fmt.Errorf("invalid base URL")
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/") + "/"
	return parsed, nil
}

var _ ports.SurfaceAuthority = (*HTTPAuthority)(nil)
