package integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/services/user-service/internal/application"
)

type TagServiceRegionResolver struct {
	baseURL string
	client  *http.Client
}

func NewTagServiceRegionResolver(baseURL string, client *http.Client) *TagServiceRegionResolver {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if client == nil {
		client = &http.Client{Timeout: 2 * time.Second}
	}
	return &TagServiceRegionResolver{baseURL: baseURL, client: client}
}

func (r *TagServiceRegionResolver) ResolveRegionTag(ctx context.Context, regionTagRef string) (string, error) {
	display, err := application.PathRegionTagResolver{}.ResolveRegionTag(ctx, regionTagRef)
	if err != nil || strings.TrimSpace(regionTagRef) == "" {
		return display, err
	}
	if r == nil || r.baseURL == "" {
		return display, nil
	}
	parentTagRef := parentTagRef(regionTagRef)
	if parentTagRef == "" {
		return "", fmt.Errorf("regionTagRef parent is required")
	}
	query := url.Values{}
	query.Set("parentTagRef", parentTagRef)
	query.Set("limit", "500")
	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		r.baseURL+"/v1/tag/children?"+query.Encode(),
		nil,
	)
	if err != nil {
		return "", err
	}
	req.Header.Set("X-Internal-Service", "user-service")

	resp, err := r.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return "", fmt.Errorf("regionTagRef parent not found")
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("tag-service list children: status %d", resp.StatusCode)
	}
	var children []struct {
		TagRef          string `json:"tagRef"`
		LifecycleStatus string `json:"lifecycleStatus"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&children); err != nil {
		return "", err
	}
	for _, child := range children {
		if strings.TrimSpace(child.TagRef) == strings.TrimSpace(regionTagRef) && strings.TrimSpace(child.LifecycleStatus) == "active" {
			return display, nil
		}
	}
	return "", fmt.Errorf("regionTagRef not found in active direct children")
}

func parentTagRef(tagRef string) string {
	parts := strings.Split(strings.TrimSpace(tagRef), "/")
	if len(parts) <= 1 {
		return ""
	}
	return strings.Join(parts[:len(parts)-1], "/")
}

var _ application.RegionTagResolver = (*TagServiceRegionResolver)(nil)
