package external

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
)

type ContentIntersectionConfig struct {
	BaseURL                 string
	ObjectIntersectionsPath string
	HTTPClient              *http.Client
	Authorization           rtauth.DelegatedPersonaAuthorizationProvider
}

type ContentIntersectionReader struct {
	baseURL    *url.URL
	objectPath string
	client     *http.Client
	auth       rtauth.DelegatedPersonaAuthorizationProvider
}

var _ application.ObjectIntersectionReader = (*ContentIntersectionReader)(nil)

func NewContentIntersectionReader(
	config ContentIntersectionConfig,
) (*ContentIntersectionReader, error) {
	baseURL, err := url.Parse(strings.TrimSpace(config.BaseURL))
	if err != nil || baseURL.Scheme == "" || baseURL.Host == "" {
		return nil, fmt.Errorf("content intersection base URL is invalid")
	}
	path := strings.TrimSpace(config.ObjectIntersectionsPath)
	if path == "" || !strings.HasPrefix(path, "/") {
		return nil, fmt.Errorf("content intersection path must be injected as an absolute path")
	}
	if config.Authorization == nil {
		return nil, fmt.Errorf("content intersection delegated authorization is required")
	}
	client := config.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: 3 * time.Second}
	}
	return &ContentIntersectionReader{
		baseURL: baseURL, objectPath: path, client: client, auth: config.Authorization,
	}, nil
}

type objectIntersectionsResponse struct {
	Items []json.RawMessage `json:"items"`
}

func (r *ContentIntersectionReader) ListObjectIntersections(
	ctx context.Context,
	query application.ObjectIntersectionQuery,
) ([]json.RawMessage, error) {
	if strings.TrimSpace(query.ViewerPersonaID) == "" {
		return []json.RawMessage{}, nil
	}
	target := *r.baseURL
	target.Path = strings.TrimRight(target.Path, "/") + r.objectPath
	values := target.Query()
	objectID := strings.TrimSpace(query.CanonicalEntityID)
	objectType := strings.TrimSpace(query.HomepageType)
	if objectID == "" {
		objectID = strings.TrimSpace(query.ObjectID)
		objectType = "homepage"
	}
	values.Set("objectId", objectID)
	values.Set("objectType", objectType)
	limit := query.Limit
	if limit <= 0 {
		limit = 8
	}
	values.Set("limit", strconv.Itoa(limit))
	target.RawQuery = values.Encode()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(err.Error())
	}
	authorization, err := r.auth.AuthorizationHeaderForPersona(
		ctx,
		query.ViewerPersonaID,
	)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(
			"content intersection delegated authorization failed: " + err.Error(),
		)
	}
	request.Header.Set("Authorization", authorization)
	response, err := r.client.Do(request)
	if err != nil {
		return nil, generated.AppErrorFromInternalError(
			"content intersection dependency unavailable: " + err.Error(),
		)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, generated.AppErrorFromInternalError(
			fmt.Sprintf("content intersection dependency returned status %d", response.StatusCode),
		)
	}
	var payload objectIntersectionsResponse
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return nil, generated.AppErrorFromInternalError(
			"content intersection response is invalid: " + err.Error(),
		)
	}
	if payload.Items == nil {
		payload.Items = []json.RawMessage{}
	}
	sanitized := make([]json.RawMessage, 0, len(payload.Items))
	for _, item := range payload.Items {
		var fields map[string]json.RawMessage
		if err := json.Unmarshal(item, &fields); err != nil {
			return nil, generated.AppErrorFromInternalError(
				"content intersection item is invalid: " + err.Error(),
			)
		}
		delete(fields, "sourceRefs")
		delete(fields, "primaryEvidenceRef")
		raw, err := json.Marshal(fields)
		if err != nil {
			return nil, generated.AppErrorFromInternalError(err.Error())
		}
		sanitized = append(sanitized, raw)
	}
	return sanitized, nil
}
