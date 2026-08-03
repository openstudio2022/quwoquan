package userpersona

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_guide_assignment/domain/ports"
)

const maximumResponseBytes = 256 << 10

type PublicPersonaResolver struct {
	baseURL *url.URL
	client  *http.Client
}

type publicPersonaProfile struct {
	PersonaID string `json:"personaId"`
}

func NewPublicPersonaResolver(baseURL string, client *http.Client) (*PublicPersonaResolver, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed == nil || parsed.Host == "" ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.User != nil ||
		parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, fmt.Errorf("invalid User public Persona base URL")
	}
	if client == nil {
		return nil, fmt.Errorf("User public Persona HTTP client is required")
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/") + "/"
	return &PublicPersonaResolver{baseURL: parsed, client: client}, nil
}

func (resolver *PublicPersonaResolver) ValidatePublicGuidePersona(
	ctx context.Context,
	assigneePersonaID string,
	qualificationPersonaID string,
	role model.Role,
) error {
	assigneePersonaID = strings.TrimSpace(assigneePersonaID)
	qualificationPersonaID = strings.TrimSpace(qualificationPersonaID)
	if resolver == nil || resolver.baseURL == nil || resolver.client == nil {
		return ports.ErrReferenceUnavailable
	}
	if role != model.RoleLicensedGuide || assigneePersonaID == "" ||
		qualificationPersonaID != assigneePersonaID {
		return model.ErrInvalidArgument
	}
	profileURL := resolver.baseURL.ResolveReference(&url.URL{
		Path: "user/" + url.PathEscape(qualificationPersonaID),
	})
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, profileURL.String(), nil)
	if err != nil {
		return ports.ErrReferenceUnavailable
	}
	request.Header.Set("Accept", "application/json")
	response, err := resolver.client.Do(request)
	if err != nil {
		return ports.ErrReferenceUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusNotFound {
		return model.ErrInvalidArgument
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		if response.StatusCode >= http.StatusBadRequest && response.StatusCode < http.StatusInternalServerError {
			return model.ErrInvalidArgument
		}
		return ports.ErrReferenceUnavailable
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, maximumResponseBytes+1))
	if err != nil || len(body) == 0 || len(body) > maximumResponseBytes {
		return ports.ErrReferenceUnavailable
	}
	var profile publicPersonaProfile
	if err := json.Unmarshal(body, &profile); err != nil {
		return ports.ErrReferenceUnavailable
	}
	if strings.TrimSpace(profile.PersonaID) != qualificationPersonaID {
		return model.ErrInvalidArgument
	}
	return nil
}
