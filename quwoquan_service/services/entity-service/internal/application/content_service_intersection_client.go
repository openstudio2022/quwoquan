package application

import (
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

const contentServiceObjectIntersectionsPath = "/v1/content/intersections/object"

var contentServiceObjectIntersectionsHTTPClient = &http.Client{Timeout: 3 * time.Second}

type contentServiceObjectIntersectionsResponse struct {
	Items []map[string]any `json:"items"`
}

func resolveObjectPageIntersections(
	ctx context.Context,
	viewerID string,
	homepage *Homepage,
	relationEdges []map[string]any,
) ([]map[string]any, []map[string]any) {
	if remote, ok := fetchContentServiceObjectIntersections(ctx, viewerID, homepage); ok {
		remote = cloneObjectSlice(remote)
		return remote, cloneObjectSlice(remote)
	}
	return defaultIntersectionReasons(homepage, relationEdges), defaultObjectIntersections(homepage, relationEdges)
}

func fetchContentServiceObjectIntersections(
	ctx context.Context,
	viewerID string,
	homepage *Homepage,
) ([]map[string]any, bool) {
	baseURL := strings.TrimSpace(os.Getenv("CONTENT_SERVICE_BASE_URL"))
	if baseURL == "" || strings.TrimSpace(viewerID) == "" || homepage == nil {
		return nil, false
	}
	parsed, err := url.Parse(baseURL)
	if err != nil {
		return nil, false
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/") + contentServiceObjectIntersectionsPath
	query := parsed.Query()
	objectID := strings.TrimSpace(homepage.CanonicalEntityID)
	if objectID == "" {
		return nil, false
	}
	query.Set("objectId", objectID)
	query.Set("objectType", "entity")
	query.Set("limit", strconv.Itoa(8))
	parsed.RawQuery = query.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, parsed.String(), nil)
	if err != nil {
		return nil, false
	}
	req.Header.Set("X-Client-User-Id", strings.TrimSpace(viewerID))
	resp, err := contentServiceObjectIntersectionsHTTPClient.Do(req)
	if err != nil {
		return nil, false
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, false
	}
	var payload contentServiceObjectIntersectionsResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, false
	}
	if len(payload.Items) == 0 {
		return nil, false
	}
	return payload.Items, true
}
