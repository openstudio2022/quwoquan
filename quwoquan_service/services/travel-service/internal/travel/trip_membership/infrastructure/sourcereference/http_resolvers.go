package sourcereference

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/ports"
)

const maximumResponseBytes = 256 << 10

type DelegatedAuthorizationProvider interface {
	AuthorizationHeaderForPersona(context.Context, string) (string, error)
}

type ConversationResolver struct {
	baseURL       *url.URL
	client        *http.Client
	authorization DelegatedAuthorizationProvider
}

type CircleMembershipResolver struct {
	baseURL       *url.URL
	client        *http.Client
	authorization DelegatedAuthorizationProvider
}

type GatheringResolver struct {
	baseURL       *url.URL
	client        *http.Client
	authorization DelegatedAuthorizationProvider
}

func NewConversationResolver(
	baseURL string,
	client *http.Client,
	authorization DelegatedAuthorizationProvider,
) (*ConversationResolver, error) {
	parsed, err := parseBaseURL(baseURL)
	if err != nil || client == nil || authorization == nil {
		return nil, fmt.Errorf("Chat Conversation source reader is invalid")
	}
	return &ConversationResolver{baseURL: parsed, client: client, authorization: authorization}, nil
}

func NewCircleMembershipResolver(
	baseURL string,
	client *http.Client,
	authorization DelegatedAuthorizationProvider,
) (*CircleMembershipResolver, error) {
	parsed, err := parseBaseURL(baseURL)
	if err != nil || client == nil || authorization == nil {
		return nil, fmt.Errorf("Circle membership source reader is invalid")
	}
	return &CircleMembershipResolver{baseURL: parsed, client: client, authorization: authorization}, nil
}

func NewGatheringResolver(
	baseURL string,
	client *http.Client,
	authorization DelegatedAuthorizationProvider,
) (*GatheringResolver, error) {
	parsed, err := parseBaseURL(baseURL)
	if err != nil || client == nil || authorization == nil {
		return nil, fmt.Errorf("Gathering source reader is invalid")
	}
	return &GatheringResolver{baseURL: parsed, client: client, authorization: authorization}, nil
}

func (resolver *ConversationResolver) ValidateMembershipSource(
	ctx context.Context,
	ref model.SourceRef,
	sourceVersion int64,
	personaID string,
) error {
	if strings.TrimSpace(ref.ObjectTypeRef) != "chat.Conversation" {
		return model.ErrInvalidArgument
	}
	var result struct {
		ID                    string `json:"id"`
		MembersRosterRevision int64  `json:"membersRosterRevision"`
		Status                string `json:"status"`
	}
	if err := getDelegatedJSON(
		ctx, resolver.baseURL, resolver.client, resolver.authorization, personaID,
		"chat/conversations/"+url.PathEscape(strings.TrimSpace(ref.ObjectID)), &result,
	); err != nil {
		return err
	}
	if strings.TrimSpace(result.ID) != strings.TrimSpace(ref.ObjectID) ||
		result.MembersRosterRevision != sourceVersion ||
		strings.ToLower(strings.TrimSpace(result.Status)) != "active" {
		return model.ErrInvalidArgument
	}
	return nil
}

func (resolver *CircleMembershipResolver) ValidateMembershipSource(
	ctx context.Context,
	ref model.SourceRef,
	sourceVersion int64,
	personaID string,
) error {
	if strings.TrimSpace(ref.ObjectTypeRef) != "circle.Circle" {
		return model.ErrInvalidArgument
	}
	var result struct {
		Version   int64  `json:"version"`
		CircleID  string `json:"circleId"`
		PersonaID string `json:"personaId"`
		State     string `json:"state"`
	}
	if err := getDelegatedJSON(
		ctx, resolver.baseURL, resolver.client, resolver.authorization, personaID,
		"circles/"+url.PathEscape(strings.TrimSpace(ref.ObjectID))+"/memberships/self", &result,
	); err != nil {
		return err
	}
	if strings.TrimSpace(result.CircleID) != strings.TrimSpace(ref.ObjectID) ||
		strings.TrimSpace(result.PersonaID) != strings.TrimSpace(personaID) ||
		result.Version != sourceVersion || strings.ToLower(strings.TrimSpace(result.State)) != "active" {
		return model.ErrInvalidArgument
	}
	return nil
}

func (resolver *GatheringResolver) ValidateMembershipSource(
	ctx context.Context,
	ref model.SourceRef,
	sourceVersion int64,
	personaID string,
) error {
	if strings.TrimSpace(ref.ObjectTypeRef) != "circle.Gathering" {
		return model.ErrInvalidArgument
	}
	var result struct {
		GatheringID  string `json:"gatheringId"`
		Version      int64  `json:"version"`
		Participants []struct {
			PersonaID string `json:"personaId"`
			State     string `json:"state"`
		} `json:"participants"`
	}
	if err := getDelegatedJSON(
		ctx, resolver.baseURL, resolver.client, resolver.authorization, personaID,
		"gatherings/"+url.PathEscape(strings.TrimSpace(ref.ObjectID)), &result,
	); err != nil {
		return err
	}
	if strings.TrimSpace(result.GatheringID) != strings.TrimSpace(ref.ObjectID) || result.Version != sourceVersion {
		return model.ErrInvalidArgument
	}
	for _, participant := range result.Participants {
		if strings.TrimSpace(participant.PersonaID) == strings.TrimSpace(personaID) &&
			strings.ToLower(strings.TrimSpace(participant.State)) == "joined" {
			return nil
		}
	}
	return model.ErrInvalidArgument
}

func getDelegatedJSON(
	ctx context.Context,
	baseURL *url.URL,
	client *http.Client,
	authorization DelegatedAuthorizationProvider,
	personaID string,
	path string,
	destination any,
) error {
	if baseURL == nil || client == nil || authorization == nil ||
		strings.TrimSpace(personaID) == "" || strings.TrimSpace(path) == "" {
		return ports.ErrSourceUnavailable
	}
	header, err := authorization.AuthorizationHeaderForPersona(ctx, strings.TrimSpace(personaID))
	if err != nil || strings.TrimSpace(header) == "" {
		return ports.ErrSourceUnavailable
	}
	target := baseURL.ResolveReference(&url.URL{Path: path})
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return ports.ErrSourceUnavailable
	}
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Authorization", header)
	response, err := client.Do(request)
	if err != nil {
		return ports.ErrSourceUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode >= http.StatusBadRequest && response.StatusCode < http.StatusInternalServerError {
		return model.ErrInvalidArgument
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return ports.ErrSourceUnavailable
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, maximumResponseBytes+1))
	if err != nil || len(body) == 0 || len(body) > maximumResponseBytes {
		return ports.ErrSourceUnavailable
	}
	if err := json.Unmarshal(body, destination); err != nil {
		return ports.ErrSourceUnavailable
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
