package external

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

const defaultTargetReadTimeout = 1500 * time.Millisecond

// LocalCircleReader is the Gathering-owned read port for the only target type
// whose authority lives in the same process. The adapter is supplied by cmd/api
// so this package never imports another object's private implementation.
type LocalCircleReader interface {
	CircleExists(ctx context.Context, circleID string) (bool, error)
}

type TargetReaderConfig struct {
	ContentBaseURL string
	EntityBaseURL  string
	UserBaseURL    string
	HTTPClient     *http.Client
	Circles        LocalCircleReader
}

type TargetReader struct {
	contentBaseURL *url.URL
	entityBaseURL  *url.URL
	userBaseURL    *url.URL
	httpClient     *http.Client
	circles        LocalCircleReader
}

func NewTargetReader(config TargetReaderConfig) (*TargetReader, error) {
	contentBaseURL, err := requireHTTPBaseURL("CONTENT_SERVICE_BASE_URL", config.ContentBaseURL)
	if err != nil {
		return nil, err
	}
	entityBaseURL, err := requireHTTPBaseURL("ENTITY_SERVICE_BASE_URL", config.EntityBaseURL)
	if err != nil {
		return nil, err
	}
	userBaseURL, err := requireHTTPBaseURL("USER_SERVICE_BASE_URL", config.UserBaseURL)
	if err != nil {
		return nil, err
	}
	if config.Circles == nil {
		return nil, fmt.Errorf("Gathering target reader requires local Circle reader")
	}
	client := config.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: defaultTargetReadTimeout}
	}
	return &TargetReader{
		contentBaseURL: contentBaseURL,
		entityBaseURL:  entityBaseURL,
		userBaseURL:    userBaseURL,
		httpClient:     client,
		circles:        config.Circles,
	}, nil
}

func (reader *TargetReader) RequireNavigable(
	ctx context.Context,
	source contract.GatheringSourceRef,
) error {
	objectType := strings.TrimSpace(source.ObjectRef.ObjectTypeRef)
	objectID := strings.TrimSpace(source.ObjectRef.ObjectID)
	routeID := strings.TrimSpace(source.RouteID)
	if objectType == "" || objectID == "" || routeID == "" {
		return fmt.Errorf("%w: target identity is incomplete", ports.ErrTargetNotNavigable)
	}

	switch objectType {
	case "circle":
		if routeID != "circleDetail" {
			return invalidRoute(objectType, routeID)
		}
		exists, err := reader.circles.CircleExists(ctx, objectID)
		if err != nil {
			return fmt.Errorf("%w: read Circle target: %v", ports.ErrTargetAuthorityUnavailable, err)
		}
		if !exists {
			return fmt.Errorf("%w: Circle target does not exist", ports.ErrTargetNotNavigable)
		}
		return nil
	case "content":
		if routeID != "workBrowser" {
			return invalidRoute(objectType, routeID)
		}
		return reader.requireHTTPObject(ctx, reader.contentBaseURL, "/content/posts/", objectID)
	case "person":
		if routeID != "userProfile" {
			return invalidRoute(objectType, routeID)
		}
		return reader.requireHTTPObject(ctx, reader.userBaseURL, "/user/personas/", objectID)
	case "school", "place", "enterprise", "route", "photo_spot", "gear", "homepage":
		if routeID != "homepageDetail" {
			return invalidRoute(objectType, routeID)
		}
		return reader.requireHTTPObject(ctx, reader.entityBaseURL, "/homepages/", objectID)
	default:
		return fmt.Errorf("%w: unsupported target object type %q", ports.ErrTargetNotNavigable, objectType)
	}
}

func (reader *TargetReader) requireHTTPObject(
	ctx context.Context,
	baseURL *url.URL,
	pathPrefix string,
	objectID string,
) error {
	targetURL := *baseURL
	pathBase := strings.TrimRight(targetURL.Path, "/") + pathPrefix
	targetURL.Path = pathBase + objectID
	targetURL.RawPath = pathBase + url.PathEscape(objectID)
	targetURL.RawQuery = ""
	targetURL.Fragment = ""
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, targetURL.String(), nil)
	if err != nil {
		return fmt.Errorf("%w: build owner request: %v", ports.ErrTargetAuthorityUnavailable, err)
	}
	response, err := reader.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("%w: owner request failed: %v", ports.ErrTargetAuthorityUnavailable, err)
	}
	defer response.Body.Close()
	if response.StatusCode >= 200 && response.StatusCode < 300 {
		return nil
	}
	if response.StatusCode == http.StatusNotFound || response.StatusCode == http.StatusGone {
		return fmt.Errorf("%w: owner returned %s", ports.ErrTargetNotNavigable, response.Status)
	}
	return fmt.Errorf("%w: owner returned %s", ports.ErrTargetAuthorityUnavailable, response.Status)
}

func requireHTTPBaseURL(name, raw string) (*url.URL, error) {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || parsed == nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
		return nil, fmt.Errorf("%s must be an absolute http(s) URL", name)
	}
	return parsed, nil
}

func invalidRoute(objectType, routeID string) error {
	return fmt.Errorf(
		"%w: route %q is not canonical for target type %q",
		ports.ErrTargetNotNavigable,
		routeID,
		objectType,
	)
}

var _ ports.TargetReader = (*TargetReader)(nil)
