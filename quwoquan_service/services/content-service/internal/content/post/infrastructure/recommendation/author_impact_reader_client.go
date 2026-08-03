package recommendation

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	transport "quwoquan_service/services/content-service/generated/content/post"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
)

const authorImpactReadTimeout = 300 * time.Millisecond

type AuthorImpactReaderClient struct {
	baseURL     string
	httpClient  *http.Client
	credentials rtauth.ServiceAuthorizationProvider
}

func NewAuthorImpactReaderClient(
	baseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
) (*AuthorImpactReaderClient, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("author impact reader: valid recommendation base URL is required")
	}
	if credentials == nil {
		return nil, fmt.Errorf("author impact reader: service credentials are required")
	}
	return &AuthorImpactReaderClient{
		baseURL:     strings.TrimRight(parsed.String(), "/"),
		httpClient:  &http.Client{},
		credentials: credentials,
	}, nil
}

func (client *AuthorImpactReaderClient) SetTransport(transport http.RoundTripper) {
	if transport == nil {
		transport = http.DefaultTransport
	}
	client.httpClient.Transport = transport
}

func (client *AuthorImpactReaderClient) GetSummary(
	ctx context.Context,
	authorID string,
	limit int64,
) (ports.AuthorImpactSummary, error) {
	if limit < 1 || limit > 50 {
		return ports.AuthorImpactSummary{}, fmt.Errorf("author impact limit must be within [1,50]")
	}
	path := strings.Replace(
		transport.GetRecommendationAuthorImpactPath,
		"{authorId}",
		url.PathEscape(strings.TrimSpace(authorID)),
		1,
	)
	query := url.Values{}
	query.Set("limit", strconv.FormatInt(limit, 10))
	var wire transport.RecommendationAuthorImpactSummary
	if err := client.get(ctx, path+"?"+query.Encode(), &wire); err != nil {
		return ports.AuthorImpactSummary{}, err
	}
	if strings.TrimSpace(wire.AuthorId) != strings.TrimSpace(authorID) {
		return ports.AuthorImpactSummary{}, fmt.Errorf("author impact response author identity mismatch")
	}
	summary := ports.AuthorImpactSummary{
		AuthorID: wire.AuthorId,
		Total:    wire.Total,
		Items:    make([]ports.AuthorImpactItem, 0, len(wire.Items)),
	}
	for _, item := range wire.Items {
		summary.Items = append(summary.Items, ports.AuthorImpactItem{
			ImpactID:                item.ImpactId,
			HelpType:                item.HelpType,
			Action:                  item.Action,
			IntersectionDimension:   optionalString(item.IntersectionDimension),
			TagRef:                  optionalString(item.TagRef),
			Source:                  item.Source,
			Count:                   item.Count,
			UpdatedAt:               item.UpdatedAt,
			RepresentativeContentID: optionalString(item.RepresentativeContentId),
		})
	}
	return summary, nil
}

func (client *AuthorImpactReaderClient) ListPageWithTotal(
	ctx context.Context,
	authorID,
	impactID,
	cursor string,
	limit int64,
) ([]ports.AuthorImpactEvidenceRaw, string, bool, int64, error) {
	if limit < 1 || limit > 50 {
		return nil, "", false, 0, fmt.Errorf("author impact evidence limit must be within [1,50]")
	}
	path := strings.Replace(
		transport.ListRecommendationAuthorImpactEvidencePath,
		"{authorId}",
		url.PathEscape(strings.TrimSpace(authorID)),
		1,
	)
	path = strings.Replace(
		path,
		"{impactId}",
		url.PathEscape(strings.TrimSpace(impactID)),
		1,
	)
	query := url.Values{}
	query.Set("limit", strconv.FormatInt(limit, 10))
	if normalizedCursor := strings.TrimSpace(cursor); normalizedCursor != "" {
		query.Set("cursor", normalizedCursor)
	}
	var wire transport.RecommendationAuthorImpactEvidencePage
	if err := client.get(ctx, path+"?"+query.Encode(), &wire); err != nil {
		return nil, "", false, 0, err
	}
	if strings.TrimSpace(wire.ImpactId) != strings.TrimSpace(impactID) {
		return nil, "", false, 0, fmt.Errorf("author impact evidence identity mismatch")
	}
	items := make([]ports.AuthorImpactEvidenceRaw, 0, len(wire.Items))
	for _, item := range wire.Items {
		if item.ImpactId != wire.ImpactId {
			return nil, "", false, 0, fmt.Errorf("author impact evidence item identity mismatch")
		}
		items = append(items, ports.AuthorImpactEvidenceRaw{
			EvidenceID:            item.EvidenceId,
			ImpactID:              item.ImpactId,
			ContentID:             item.ContentId,
			ContentType:           optionalString(item.ContentType),
			HelpType:              item.HelpType,
			Action:                item.Action,
			IntersectionDimension: optionalString(item.IntersectionDimension),
			OccurredAt:            item.OccurredAt,
		})
	}
	return items, optionalString(wire.NextCursor), wire.HasMore, wire.TotalCount, nil
}

func (client *AuthorImpactReaderClient) get(
	ctx context.Context,
	path string,
	target any,
) error {
	if client == nil || client.httpClient == nil || client.credentials == nil {
		return fmt.Errorf("author impact reader is not configured")
	}
	requestContext, cancel := context.WithTimeout(ctx, authorImpactReadTimeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		requestContext,
		http.MethodGet,
		client.baseURL+path,
		nil,
	)
	if err != nil {
		return err
	}
	request.Header.Set("Accept", "application/json")
	authorization, err := client.credentials.AuthorizationHeader(requestContext)
	if err != nil {
		return fmt.Errorf("author impact service authorization: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	response, err := client.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("author impact request failed: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("author impact service status %d", response.StatusCode)
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 2*1024*1024))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode author impact response: %w", err)
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return fmt.Errorf("author impact response has trailing payload")
	}
	return nil
}

func optionalString(value *string) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(*value)
}
