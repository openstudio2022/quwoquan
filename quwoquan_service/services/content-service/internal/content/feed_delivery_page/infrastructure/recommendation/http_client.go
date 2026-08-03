package recommendation

import (
	"bytes"
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
	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
)

const retryBackoff = 20 * time.Millisecond

type HTTPClient struct {
	baseURL     string
	httpClient  *http.Client
	credentials rtauth.ServiceAuthorizationProvider
}

func NewHTTPClient(
	baseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
) (*HTTPClient, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("ranked recommendation client: valid base URL is required")
	}
	if credentials == nil {
		return nil, fmt.Errorf("ranked recommendation client: service credentials are required")
	}
	return &HTTPClient{
		baseURL:     strings.TrimRight(parsed.String(), "/"),
		httpClient:  &http.Client{},
		credentials: credentials,
	}, nil
}

func (client *HTTPClient) SetTransport(transport http.RoundTripper) {
	if transport == nil {
		transport = http.DefaultTransport
	}
	client.httpClient.Transport = transport
}

func (client *HTTPClient) Create(
	ctx context.Context,
	command transport.CreateRankedRecommendationWindowCommand,
) (transport.RankedRecommendationPage, error) {
	body, err := json.Marshal(transport.CreateRankedRecommendationWindowRequestBody{
		SubjectId: command.SubjectId,
		Scenario:  command.Scenario,
		Limit:     command.Limit,
	})
	if err != nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf(
			"%w: encode create ranked window request: %v",
			deliveryapp.ErrRecommendationUnavailable,
			err,
		)
	}
	return client.do(
		ctx,
		transport.CreateRankedRecommendationWindowMethod,
		client.baseURL+transport.CreateRankedRecommendationWindowPath,
		body,
		strings.TrimSpace(command.IdempotencyKey),
		800*time.Millisecond,
	)
}

func (client *HTTPClient) GetPage(
	ctx context.Context,
	request transport.GetRankedRecommendationPageQuery,
) (transport.RankedRecommendationPage, error) {
	path := strings.Replace(
		transport.GetRankedRecommendationPagePath,
		"{windowId}",
		url.PathEscape(strings.TrimSpace(request.WindowId)),
		1,
	)
	query := url.Values{}
	query.Set("subjectId", strings.TrimSpace(request.SubjectId))
	if request.FromOrdinal != nil {
		query.Set("fromOrdinal", strconv.Itoa(*request.FromOrdinal))
	}
	if request.Limit != nil {
		query.Set("limit", strconv.Itoa(*request.Limit))
	}
	return client.do(
		ctx,
		transport.GetRankedRecommendationPageMethod,
		client.baseURL+path+"?"+query.Encode(),
		nil,
		"",
		300*time.Millisecond,
	)
}

type transientStatusError struct {
	status int
}

func (err transientStatusError) Error() string {
	return fmt.Sprintf("transient recommendation status %d", err.status)
}

func (client *HTTPClient) do(
	ctx context.Context,
	method string,
	endpoint string,
	body []byte,
	idempotencyKey string,
	timeout time.Duration,
) (transport.RankedRecommendationPage, error) {
	if client == nil || client.httpClient == nil || client.credentials == nil {
		return transport.RankedRecommendationPage{}, deliveryapp.ErrRecommendationUnavailable
	}
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		if attempt > 0 {
			timer := time.NewTimer(retryBackoff)
			select {
			case <-ctx.Done():
				timer.Stop()
				return transport.RankedRecommendationPage{}, ctx.Err()
			case <-timer.C:
			}
		}
		page, err := client.doOnce(
			ctx,
			method,
			endpoint,
			body,
			idempotencyKey,
			timeout,
		)
		if err == nil {
			return page, nil
		}
		lastErr = err
		var transient transientStatusError
		if !errors.As(err, &transient) {
			break
		}
	}
	return transport.RankedRecommendationPage{}, fmt.Errorf(
		"%w: %v",
		deliveryapp.ErrRecommendationUnavailable,
		lastErr,
	)
}

func (client *HTTPClient) doOnce(
	ctx context.Context,
	method string,
	endpoint string,
	body []byte,
	idempotencyKey string,
	timeout time.Duration,
) (transport.RankedRecommendationPage, error) {
	requestContext, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		requestContext,
		method,
		endpoint,
		bytes.NewReader(body),
	)
	if err != nil {
		return transport.RankedRecommendationPage{}, err
	}
	request.Header.Set("Accept", "application/json")
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	authorization, err := client.credentials.AuthorizationHeader(requestContext)
	if err != nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf("service authorization: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	response, err := client.httpClient.Do(request)
	if err != nil {
		return transport.RankedRecommendationPage{}, transientStatusError{status: http.StatusServiceUnavailable}
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		if response.StatusCode == http.StatusBadGateway ||
			response.StatusCode == http.StatusServiceUnavailable ||
			response.StatusCode == http.StatusGatewayTimeout {
			return transport.RankedRecommendationPage{}, transientStatusError{status: response.StatusCode}
		}
		return transport.RankedRecommendationPage{}, fmt.Errorf(
			"recommendation status %d",
			response.StatusCode,
		)
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 2*1024*1024))
	decoder.DisallowUnknownFields()
	var page transport.RankedRecommendationPage
	if err := decoder.Decode(&page); err != nil {
		return transport.RankedRecommendationPage{}, fmt.Errorf("decode ranked recommendation page: %w", err)
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return transport.RankedRecommendationPage{}, fmt.Errorf("ranked recommendation page has trailing payload")
	}
	if err := validatePage(page); err != nil {
		return transport.RankedRecommendationPage{}, err
	}
	return page, nil
}

func validatePage(page transport.RankedRecommendationPage) error {
	if strings.TrimSpace(page.WindowId) == "" || strings.TrimSpace(page.Scenario) == "" ||
		!strings.HasPrefix(strings.TrimSpace(page.PolicyDigest), "sha256:") ||
		strings.TrimSpace(page.RankingSnapshotDigest) == "" || page.FeatureSnapshotAt.IsZero() ||
		page.ExpiresAt.IsZero() || !page.ExpiresAt.After(time.Now().UTC()) ||
		page.UserFeatureSnapshot == nil || len(page.Items) > 100 {
		return fmt.Errorf("ranked recommendation page identity is invalid")
	}
	modelChannel := optionalText(page.ModelChannel)
	modelReleaseID := optionalText(page.ModelReleaseId)
	switch page.ModelBucket {
	case "model":
		if modelChannel == "" || modelReleaseID == "" {
			return fmt.Errorf("model ranked page attribution is incomplete")
		}
	case "rule":
		if modelChannel != "" || modelReleaseID != "" {
			return fmt.Errorf("rule ranked page cannot claim a model release")
		}
	default:
		return fmt.Errorf("ranked page model bucket is invalid")
	}
	seenOrdinals := make(map[int]struct{}, len(page.Items))
	seenContent := make(map[string]struct{}, len(page.Items))
	for _, item := range page.Items {
		contentID := strings.TrimSpace(item.ContentId)
		if item.Ordinal < 0 || contentID == "" || strings.TrimSpace(item.FeatureSnapshotDigest) == "" ||
			item.ItemFeatureSnapshot == nil {
			return fmt.Errorf("ranked recommendation item is invalid")
		}
		if _, duplicate := seenOrdinals[item.Ordinal]; duplicate {
			return fmt.Errorf("ranked recommendation item ordinal is duplicated")
		}
		if _, duplicate := seenContent[contentID]; duplicate {
			return fmt.Errorf("ranked recommendation content identity is duplicated")
		}
		seenOrdinals[item.Ordinal] = struct{}{}
		seenContent[contentID] = struct{}{}
	}
	if len(page.ObjectCards) > 20 {
		return fmt.Errorf("ranked recommendation page has too many object cards")
	}
	seenObjectCards := make(map[string]struct{}, len(page.ObjectCards))
	for _, card := range page.ObjectCards {
		objectID := strings.TrimSpace(card.ObjectId)
		if strings.TrimSpace(card.ObjectKind) == "" || objectID == "" ||
			strings.TrimSpace(card.Title) == "" || strings.TrimSpace(card.ReasonKey) == "" ||
			strings.TrimSpace(card.RecallPath) == "" {
			return fmt.Errorf("ranked recommendation object card is invalid")
		}
		if _, duplicate := seenObjectCards[objectID]; duplicate {
			return fmt.Errorf("ranked recommendation object card identity is duplicated")
		}
		seenObjectCards[objectID] = struct{}{}
		seenTags := make(map[string]struct{}, len(card.TagRefs))
		for _, rawTag := range card.TagRefs {
			tag := strings.TrimSpace(rawTag)
			if tag == "" {
				return fmt.Errorf("ranked recommendation object card tag is empty")
			}
			if _, duplicate := seenTags[tag]; duplicate {
				return fmt.Errorf("ranked recommendation object card tag is duplicated")
			}
			seenTags[tag] = struct{}{}
		}
	}
	if page.NextOrdinal != nil && (*page.NextOrdinal < 0 || len(page.Items) == 0) {
		return fmt.Errorf("ranked recommendation continuation is invalid")
	}
	return nil
}

func optionalText(value *string) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(*value)
}

var _ deliveryapp.RankedRecommendationGateway = (*HTTPClient)(nil)
