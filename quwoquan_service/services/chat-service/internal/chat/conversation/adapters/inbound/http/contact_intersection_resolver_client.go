package http

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
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

type ContactIntersectionResolverClient struct {
	baseURL       string
	client        *http.Client
	authorization rtauth.DelegatedPersonaAuthorizationProvider
}

func NewContactIntersectionResolverClient(
	baseURL string,
	client *http.Client,
	authorization rtauth.DelegatedPersonaAuthorizationProvider,
) (*ContactIntersectionResolverClient, error) {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	parsed, err := url.Parse(baseURL)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" || parsed.User != nil {
		return nil, fmt.Errorf("content intersection base URL is invalid")
	}
	if authorization == nil {
		return nil, fmt.Errorf("content intersection delegated authorization is required")
	}
	if client == nil {
		client = &http.Client{Timeout: 1500 * time.Millisecond}
	}
	return &ContactIntersectionResolverClient{
		baseURL:       baseURL,
		client:        client,
		authorization: authorization,
	}, nil
}

func (c *ContactIntersectionResolverClient) ListContactIntersections(
	ctx context.Context,
	viewerPersonaID string,
	contactPersonaID string,
	limit int,
) ([]application.ContactIntersectionSummary, error) {
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	contactPersonaID = strings.TrimSpace(contactPersonaID)
	if viewerPersonaID == "" || contactPersonaID == "" {
		return nil, nil
	}
	if limit <= 0 || limit > 2 {
		limit = 2
	}
	values := url.Values{}
	values.Set("objectId", contactPersonaID)
	values.Set("objectType", "user")
	values.Set("limit", strconv.Itoa(limit))
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		c.baseURL+"/content/intersections/object?"+values.Encode(),
		nil,
	)
	if err != nil {
		return nil, err
	}
	authorization, err := c.authorization.AuthorizationHeaderForPersona(ctx, viewerPersonaID)
	if err != nil {
		return nil, err
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	response, err := c.client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("content contact intersections status=%d", response.StatusCode)
	}
	var payload struct {
		Items []struct {
			IntersectionID         string `json:"intersectionId"`
			PointSummarySnapshotID string `json:"pointSummarySnapshotId"`
			Kind                   string `json:"kind"`
			IntersectionClass      string `json:"intersectionClass"`
			PrimaryText            string `json:"primaryText"`
			Dimension              string `json:"dimension"`
		} `json:"items"`
	}
	decoder := json.NewDecoder(response.Body)
	if err := decoder.Decode(&payload); err != nil {
		return nil, err
	}
	items := make([]application.ContactIntersectionSummary, 0, len(payload.Items))
	for _, item := range payload.Items {
		if strings.TrimSpace(item.PrimaryText) == "" {
			continue
		}
		items = append(items, application.ContactIntersectionSummary{
			IntersectionID:    strings.TrimSpace(item.IntersectionID),
			EvidenceID:        strings.TrimSpace(item.PointSummarySnapshotID),
			SourceRef:         strings.TrimSpace(item.Kind),
			ObjectTypeRef:     "user",
			ObjectID:          contactPersonaID,
			PrimaryText:       strings.TrimSpace(item.PrimaryText),
			Dimension:         strings.TrimSpace(item.Dimension),
			IntersectionClass: strings.TrimSpace(item.IntersectionClass),
		})
		if len(items) == limit {
			break
		}
	}
	return items, nil
}

var _ application.ContactIntersectionResolver = (*ContactIntersectionResolverClient)(nil)
