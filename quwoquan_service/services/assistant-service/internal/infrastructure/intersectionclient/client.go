package intersectionclient

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/assistant-service/internal/application"
)

const (
	listMyIntersectionsOperationID = "content.post.ListMyIntersections"
	maxResponseBytes               = 512 << 10
)

type Config struct {
	BaseURL       string
	HTTPClient    *http.Client
	Authorization rtauth.DelegatedPersonaAuthorizationProvider
}

// Client 从 content-service 的正式 ListMyIntersections Slice 读取事实交集。
type Client struct {
	baseURL       *url.URL
	http          *http.Client
	authorization rtauth.DelegatedPersonaAuthorizationProvider
	path          string
}

var _ application.IntersectionInboxReader = (*Client)(nil)

func New(config Config) (*Client, error) {
	baseURL, err := url.Parse(strings.TrimSpace(config.BaseURL))
	if err != nil || baseURL.Scheme == "" || baseURL.Host == "" {
		return nil, fmt.Errorf("content-service base url is invalid")
	}
	if config.Authorization == nil {
		return nil, fmt.Errorf("content-service delegated authorization is required")
	}
	descriptor, err := operationDescriptor()
	if err != nil {
		return nil, err
	}
	httpClient := config.HTTPClient
	if httpClient == nil {
		timeout := time.Duration(descriptor.TimeoutMilliseconds) * time.Millisecond
		if timeout <= 0 {
			timeout = 1500 * time.Millisecond
		}
		httpClient = &http.Client{Timeout: timeout}
	}
	return &Client{
		baseURL:       baseURL,
		http:          httpClient,
		authorization: config.Authorization,
		path:          descriptor.PathTemplate,
	}, nil
}

func (c *Client) ListNewIntersectionReasons(
	ctx context.Context,
	userID string,
	since time.Time,
	limit int,
) ([]application.IntersectionReminderReason, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return []application.IntersectionReminderReason{}, nil
	}
	if limit <= 0 {
		limit = 20
	}
	if limit > 50 {
		limit = 50
	}
	target := *c.baseURL
	target.Path = strings.TrimRight(target.Path, "/") + c.path
	values := target.Query()
	values.Set("filter", "new")
	values.Set("limit", strconv.Itoa(limit))
	target.RawQuery = values.Encode()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("build content intersection request: %w", err)
	}
	authorization, err := c.authorization.AuthorizationHeaderForPersona(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("authorize content intersection request: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	response, err := c.http.Do(request)
	if err != nil {
		return nil, fmt.Errorf("call content-service intersections: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("content-service intersections status=%d", response.StatusCode)
	}
	var payload struct {
		Items []struct {
			IntersectionID    string `json:"intersectionId"`
			RelationObjectID  string `json:"relationObjectId"`
			ActionTargetID    string `json:"actionTargetId"`
			DisplayName       string `json:"displayName"`
			Dimension         string `json:"dimension"`
			PrimaryText       string `json:"primaryText"`
			IntersectionClass string `json:"intersectionClass"`
			FreshAt           string `json:"freshAt"`
		} `json:"items"`
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, maxResponseBytes))
	if err := decoder.Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode content intersection response: %w", err)
	}
	reasons := make([]application.IntersectionReminderReason, 0, len(payload.Items))
	for _, item := range payload.Items {
		freshAt, ok := parseFreshAt(item.FreshAt)
		if !since.IsZero() && (!ok || !freshAt.After(since)) {
			continue
		}
		targetID := strings.TrimSpace(item.RelationObjectID)
		if targetID == "" {
			targetID = strings.TrimSpace(item.ActionTargetID)
		}
		class := strings.TrimSpace(item.IntersectionClass)
		reasons = append(reasons, application.IntersectionReminderReason{
			ReasonID:    strings.TrimSpace(item.IntersectionID),
			UserID:      userID,
			TargetID:    targetID,
			TargetName:  strings.TrimSpace(item.DisplayName),
			Dimension:   strings.TrimSpace(item.Dimension),
			PrimaryText: strings.TrimSpace(item.PrimaryText),
			IsFact:      class == "" || class == "fact",
			CreatedAt:   freshAt,
		})
	}
	return reasons, nil
}

func operationDescriptor() (rtauth.OperationSecurityDescriptor, error) {
	for _, descriptor := range operationsecurity.ForDomain("content") {
		if descriptor.CanonicalOperationID == listMyIntersectionsOperationID {
			return descriptor, nil
		}
	}
	return rtauth.OperationSecurityDescriptor{}, fmt.Errorf(
		"generated operation descriptor %q is missing",
		listMyIntersectionsOperationID,
	)
}

func parseFreshAt(raw string) (time.Time, bool) {
	value, err := time.Parse(time.RFC3339, strings.TrimSpace(raw))
	if err != nil {
		return time.Time{}, false
	}
	return value.UTC(), true
}
