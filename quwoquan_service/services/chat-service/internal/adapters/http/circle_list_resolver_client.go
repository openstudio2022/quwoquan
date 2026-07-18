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

type CircleListResolverClient struct {
	baseURL string
	client  *http.Client
}

type circleListPage struct {
	Items []circleListItem `json:"items"`
}

type circleListItem struct {
	CircleID      string `json:"circleId"`
	ID            string `json:"id"`
	DisplayName   string `json:"displayName"`
	Name          string `json:"name"`
	AvatarURL     string `json:"avatarUrl"`
	CoverURL      string `json:"coverUrl"`
	Description   string `json:"description"`
	MemberCount   int    `json:"memberCount"`
}

func NewCircleListResolverClient(baseURL string, client *http.Client) *CircleListResolverClient {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if client == nil {
		client = &http.Client{Timeout: 2 * time.Second}
	}
	return &CircleListResolverClient{baseURL: baseURL, client: client}
}

func (r *CircleListResolverClient) ListCircles(
	ctx context.Context,
	userID string,
	limit int,
) ([]application.ContactHomeCircleHit, error) {
	if r == nil || r.client == nil || r.baseURL == "" {
		return nil, nil
	}
	if limit <= 0 {
		limit = 50
	}
	endpoint, err := url.Parse(r.baseURL + "/circles")
	if err != nil {
		return nil, err
	}
	query := endpoint.Query()
	query.Set("limit", fmt.Sprintf("%d", limit))
	endpoint.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return nil, err
	}
	if userID = strings.TrimSpace(userID); userID != "" {
		req.Header.Set("X-Client-User-Id", userID)
	}

	resp, err := r.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("circle list status %d", resp.StatusCode)
	}

	var page circleListPage
	if err := json.NewDecoder(resp.Body).Decode(&page); err != nil {
		return nil, err
	}
	out := make([]application.ContactHomeCircleHit, 0, len(page.Items))
	for _, item := range page.Items {
		circleID := strings.TrimSpace(firstNonEmptyString(item.CircleID, item.ID))
		if circleID == "" {
			continue
		}
		displayName := strings.TrimSpace(firstNonEmptyString(item.DisplayName, item.Name))
		avatarURL := strings.TrimSpace(firstNonEmptyString(item.AvatarURL, item.CoverURL))
		subtitle := strings.TrimSpace(item.Description)
		if subtitle == "" && item.MemberCount > 0 {
			subtitle = fmt.Sprintf("%d", item.MemberCount)
		}
		out = append(out, application.ContactHomeCircleHit{
			CircleID:    circleID,
			DisplayName: displayName,
			AvatarURL:   avatarURL,
			Subtitle:    subtitle,
		})
		if len(out) >= limit {
			break
		}
	}
	return out, nil
}

func firstNonEmptyString(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
