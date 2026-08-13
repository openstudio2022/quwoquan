package recommendation

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	transport "quwoquan_service/services/content-service/generated/content/post"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
)

const socialProofReadTimeout = 300 * time.Millisecond

// SocialProofReaderClient 是 Content 侧唯一的四锚点社会证明防腐客户端：
// 只读 recommendation internal 聚合读面，Content 不落任何计数副本。
type SocialProofReaderClient struct {
	baseURL     string
	httpClient  *http.Client
	credentials rtauth.ServiceAuthorizationProvider
}

func NewSocialProofReaderClient(
	baseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
) (*SocialProofReaderClient, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("social proof reader: valid recommendation base URL is required")
	}
	if credentials == nil {
		return nil, fmt.Errorf("social proof reader: service credentials are required")
	}
	return &SocialProofReaderClient{
		baseURL:     strings.TrimRight(parsed.String(), "/"),
		httpClient:  &http.Client{},
		credentials: credentials,
	}, nil
}

func (client *SocialProofReaderClient) SetTransport(transport http.RoundTripper) {
	if transport == nil {
		transport = http.DefaultTransport
	}
	client.httpClient.Transport = transport
}

func (client *SocialProofReaderClient) GetGatheringSocialProof(
	ctx context.Context,
	anchorKind string,
	objectID string,
) (ports.GatheringSocialProofSummary, error) {
	normalizedAnchor := strings.TrimSpace(anchorKind)
	normalizedObject := strings.TrimSpace(objectID)
	path := strings.Replace(
		transport.GetRecommendationGatheringSocialProofPath,
		"{anchorKind}",
		url.PathEscape(normalizedAnchor),
		1,
	)
	path = strings.Replace(
		path,
		"{objectId}",
		url.PathEscape(normalizedObject),
		1,
	)
	var wire transport.RecommendationGatheringSocialProofSummary
	if err := client.get(ctx, path, &wire); err != nil {
		return ports.GatheringSocialProofSummary{}, err
	}
	if strings.TrimSpace(wire.AnchorKind) != normalizedAnchor ||
		strings.TrimSpace(wire.ObjectId) != normalizedObject {
		return ports.GatheringSocialProofSummary{}, fmt.Errorf(
			"social proof response identity mismatch",
		)
	}
	return ports.GatheringSocialProofSummary{
		AnchorKind:       wire.AnchorKind,
		ObjectID:         wire.ObjectId,
		PublishedCount:   wire.PublishedCount,
		FormedCount:      wire.FormedCount,
		ExperiencedCount: wire.ExperiencedCount,
	}, nil
}

func (client *SocialProofReaderClient) get(
	ctx context.Context,
	path string,
	target any,
) error {
	if client == nil || client.httpClient == nil || client.credentials == nil {
		return fmt.Errorf("social proof reader is not configured")
	}
	requestContext, cancel := context.WithTimeout(ctx, socialProofReadTimeout)
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
		return fmt.Errorf("social proof service authorization: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	response, err := client.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("social proof request failed: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("social proof service status %d", response.StatusCode)
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 64*1024))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode social proof response: %w", err)
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return fmt.Errorf("social proof response has trailing payload")
	}
	return nil
}
