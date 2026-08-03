package contentpost

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/ports"
)

const maximumResponseBytes = 256 << 10

// PublicPostResolver verifies that a link target is a public, published Post.
// Link visibility can be narrower than Post visibility, but it must never make
// a private Post readable to other Trip members.
type PublicPostResolver struct {
	baseURL *url.URL
	client  *http.Client
}

type publicPost struct {
	PostID     string `json:"postId"`
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

func (resolver *PublicPostResolver) ValidateVisiblePost(
	ctx context.Context,
	_ string,
	postID string,
	_ bool,
) error {
	postID = strings.TrimSpace(postID)
	if resolver == nil || resolver.baseURL == nil || resolver.client == nil || postID == "" {
		return ports.ErrPostUnavailable
	}
	postURL := resolver.baseURL.ResolveReference(&url.URL{
		Path: "content/posts/" + url.PathEscape(postID),
	})
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, postURL.String(), nil)
	if err != nil {
		return ports.ErrPostUnavailable
	}
	request.Header.Set("Accept", "application/json")
	response, err := resolver.client.Do(request)
	if err != nil {
		return ports.ErrPostUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return ports.ErrPostUnavailable
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, maximumResponseBytes+1))
	if err != nil || len(body) == 0 || len(body) > maximumResponseBytes {
		return ports.ErrPostUnavailable
	}
	var post publicPost
	if err := json.Unmarshal(body, &post); err != nil {
		return ports.ErrPostUnavailable
	}
	if strings.TrimSpace(post.PostID) != postID ||
		strings.ToLower(strings.TrimSpace(post.Status)) != "published" ||
		strings.ToLower(strings.TrimSpace(post.Visibility)) != "public" {
		return ports.ErrPostUnavailable
	}
	return nil
}
