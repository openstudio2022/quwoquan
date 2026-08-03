package contentreference

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan_template/domain/ports"
)

const maximumResponseBytes = 256 << 10

// PublicPostResolver validates template attributions through Content's public
// Post reader. It deliberately sends no caller credential: a Post that is
// visible only to its owner must not become reusable template material.
type PublicPostResolver struct {
	baseURL *url.URL
	client  *http.Client
}

type publicPost struct {
	PostID     string `json:"postId"`
	AuthorID   string `json:"authorId"`
	Status     string `json:"status"`
	Visibility string `json:"visibility"`
}

func NewPublicPostResolver(baseURL string, client *http.Client) (*PublicPostResolver, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed == nil || parsed.Host == "" ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.User != nil ||
		parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, fmt.Errorf("invalid Content public Post base URL")
	}
	if client == nil {
		return nil, fmt.Errorf("Content public Post HTTP client is required")
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/") + "/"
	return &PublicPostResolver{baseURL: parsed, client: client}, nil
}

func (resolver *PublicPostResolver) ValidatePublicAttribution(
	ctx context.Context,
	_ string,
	attribution model.Attribution,
) error {
	if resolver == nil || resolver.baseURL == nil || resolver.client == nil {
		return ports.ErrReferenceUnavailable
	}
	if strings.TrimSpace(attribution.ReferenceObjectTypeRef) != "content.Post" ||
		strings.TrimSpace(attribution.ReferenceObjectID) == "" {
		return model.ErrInvalidArgument
	}
	postID := strings.TrimSpace(attribution.ReferenceObjectID)
	postURL := resolver.baseURL.ResolveReference(&url.URL{
		Path: "content/posts/" + url.PathEscape(postID),
	})
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, postURL.String(), nil)
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
	var post publicPost
	if err := json.Unmarshal(body, &post); err != nil {
		return ports.ErrReferenceUnavailable
	}
	if strings.TrimSpace(post.PostID) != postID ||
		strings.ToLower(strings.TrimSpace(post.Status)) != "published" ||
		strings.ToLower(strings.TrimSpace(post.Visibility)) != "public" {
		return model.ErrInvalidArgument
	}
	if attribution.Kind == model.AttributionProfessionalCommentary &&
		strings.TrimSpace(post.AuthorID) != strings.TrimSpace(attribution.AuthorPersonaID) {
		return model.ErrInvalidArgument
	}
	return nil
}

var _ interface {
	ValidatePublicAttribution(context.Context, string, model.Attribution) error
} = (*PublicPostResolver)(nil)
