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

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/search-service/internal/application"
)

const (
	getObjectIntersectionsOperation = "content.post.GetObjectIntersections"
	maxResponseBytes                = 256 << 10
)

type Config struct {
	BaseURL       string
	HTTPClient    *http.Client
	Authorization rtauth.DelegatedPersonaAuthorizationProvider
}

type Client struct {
	baseURL       *url.URL
	path          string
	client        *http.Client
	authorization rtauth.DelegatedPersonaAuthorizationProvider
}

var _ application.ObjectIntersectionReader = (*Client)(nil)

func New(config Config) (*Client, error) {
	baseURL, err := url.Parse(strings.TrimSpace(config.BaseURL))
	if err != nil || baseURL.Scheme == "" || baseURL.Host == "" {
		return nil, fmt.Errorf("content intersection base URL is invalid")
	}
	if config.Authorization == nil {
		return nil, fmt.Errorf("content intersection delegated authorization is required")
	}
	descriptor, err := objectIntersectionDescriptor()
	if err != nil {
		return nil, err
	}
	client := config.HTTPClient
	if client == nil {
		timeout := time.Duration(descriptor.TimeoutMilliseconds) * time.Millisecond
		if timeout <= 0 {
			timeout = 1500 * time.Millisecond
		}
		client = &http.Client{Timeout: timeout}
	}
	return &Client{
		baseURL:       baseURL,
		path:          descriptor.PathTemplate,
		client:        client,
		authorization: config.Authorization,
	}, nil
}

func (c *Client) ListObjectIntersections(
	ctx context.Context,
	query application.ObjectIntersectionQuery,
) ([]application.ObjectIntersectionFact, error) {
	if strings.TrimSpace(query.ViewerPersonaID) == "" ||
		strings.TrimSpace(query.ObjectID) == "" {
		return []application.ObjectIntersectionFact{}, nil
	}

	target := *c.baseURL
	target.Path = strings.TrimRight(target.Path, "/") + c.path
	values := target.Query()
	values.Set("objectId", strings.TrimSpace(query.ObjectID))
	values.Set("objectType", strings.TrimSpace(query.ObjectType))
	limit := query.Limit
	if limit <= 0 {
		limit = 1
	}
	values.Set("limit", strconv.Itoa(limit))
	target.RawQuery = values.Encode()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("build content intersection request: %w", err)
	}
	authorization, err := c.authorization.AuthorizationHeaderForPersona(
		ctx,
		query.ViewerPersonaID,
	)
	if err != nil {
		return nil, fmt.Errorf("authorize content intersection request: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")

	response, err := c.client.Do(request)
	if err != nil {
		return nil, fmt.Errorf("content intersection request: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf(
			"content intersection dependency returned status %d",
			response.StatusCode,
		)
	}

	var payload struct {
		Items []struct {
			PrimaryText       string `json:"primaryText"`
			IntersectionID    string `json:"intersectionId"`
			Dimension         string `json:"dimension"`
			IntersectionClass string `json:"intersectionClass"`
			Points            []struct {
				SourceRef string `json:"sourceRef"`
			} `json:"intersectionPoints"`
		} `json:"items"`
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, maxResponseBytes))
	if err := decoder.Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode content intersection response: %w", err)
	}
	facts := make([]application.ObjectIntersectionFact, 0, len(payload.Items))
	for _, item := range payload.Items {
		primaryText := strings.TrimSpace(item.PrimaryText)
		if primaryText == "" {
			continue
		}
		sourceRef := ""
		sourceRefs := make([]string, 0, len(item.Points))
		seenSourceRefs := make(map[string]struct{}, len(item.Points))
		for _, point := range item.Points {
			normalized := strings.TrimSpace(point.SourceRef)
			if normalized == "" {
				continue
			}
			if sourceRef == "" {
				sourceRef = normalized
			}
			if _, exists := seenSourceRefs[normalized]; exists {
				continue
			}
			seenSourceRefs[normalized] = struct{}{}
			sourceRefs = append(sourceRefs, normalized)
		}
		facts = append(facts, application.ObjectIntersectionFact{
			PrimaryText:       primaryText,
			IntersectionID:    strings.TrimSpace(item.IntersectionID),
			Dimension:         strings.TrimSpace(item.Dimension),
			IntersectionClass: strings.TrimSpace(item.IntersectionClass),
			SourceRef:         sourceRef,
			SourceRefs:        sourceRefs,
		})
	}
	return facts, nil
}

func objectIntersectionDescriptor() (rtauth.OperationSecurityDescriptor, error) {
	for _, descriptor := range operationsecurity.ForDomain("content") {
		if descriptor.CanonicalOperationID == getObjectIntersectionsOperation {
			return descriptor, nil
		}
	}
	return rtauth.OperationSecurityDescriptor{}, fmt.Errorf(
		"generated operation descriptor missing: %s",
		getObjectIntersectionsOperation,
	)
}
