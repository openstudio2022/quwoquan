package contentfence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/auth"
	runtimeobservability "quwoquan_service/runtime/observability"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/ports"
)

// HTTPReader 只消费正式 Content operation；不共享 Mongo，不缓存或重试 fence。
type HTTPReader struct {
	endpoint    string
	environment string
	client      *http.Client
	credentials auth.ServiceAuthorizationProvider
}

func NewHTTPReader(baseURL, environment string, timeout time.Duration, credentials auth.ServiceAuthorizationProvider) (*HTTPReader, error) {
	endpoint, err := url.Parse(baseURL)
	if err != nil || (endpoint.Scheme != "http" && endpoint.Scheme != "https") || endpoint.Host == "" || endpoint.User != nil || endpoint.RawQuery != "" || endpoint.Fragment != "" || environment == "" || timeout <= 0 || timeout > 500*time.Millisecond || credentials == nil {
		return nil, errors.New("Content fence endpoint, environment, scoped credential and bounded timeout are required")
	}
	path := ""
	for _, descriptor := range operationsecurity.ForDomain("content") {
		if descriptor.CanonicalOperationID == "content.post.ReadActiveReleaseFence" && descriptor.Method == http.MethodGet {
			if path != "" {
				return nil, errors.New("Content fence operation is ambiguous")
			}
			path = descriptor.PathTemplate
		}
	}
	if path == "" {
		return nil, errors.New("Content fence operation is unavailable")
	}
	endpoint.Path = strings.TrimRight(endpoint.Path, "/") + path
	query := url.Values{"environment": {environment}, "sourceOwner": {"qwq_data"}}
	endpoint.RawQuery = query.Encode()
	return &HTTPReader{endpoint: endpoint.String(), environment: environment, credentials: credentials, client: &http.Client{Timeout: timeout, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}, nil
}

func (r *HTTPReader) ReadActiveContentFence(ctx context.Context) (ports.ContentFence, error) {
	var fence ports.ContentFence
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, r.endpoint, nil)
	if err != nil {
		return fence, err
	}
	header, err := r.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return fence, fmt.Errorf("Content fence credential unavailable: %w", err)
	}
	if !strings.HasPrefix(header, "Bearer ") || strings.TrimSpace(strings.TrimPrefix(header, "Bearer ")) == "" {
		return fence, errors.New("Content fence requires bearer service credentials")
	}
	request.Header.Set("Authorization", header)
	if meta, ok := runtimeobservability.CorrelationMetaFromContext(ctx); ok {
		request.Header.Set("X-Trace-Id", meta.TraceID)
		request.Header.Set("X-Request-Id", meta.RequestID)
	}
	otel.GetTextMapPropagator().Inject(ctx, propagation.HeaderCarrier(request.Header))
	response, err := r.client.Do(request)
	if err != nil {
		return fence, fmt.Errorf("Content fence transport failed: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fence, fmt.Errorf("Content fence HTTP status %d", response.StatusCode)
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, 8193))
	if err != nil || len(raw) > 8192 {
		return fence, errors.New("Content fence response exceeds bounded payload")
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		return fence, errors.New("Content fence response is not an object")
	}
	for _, key := range []string{"found", "environment", "sourceOwner", "releaseId", "manifestDigest", "revision", "projectionVersion", "activatedAt"} {
		value, ok := fields[key]
		if !ok || (key != "activatedAt" && string(value) == "null") {
			return fence, fmt.Errorf("Content fence required field %s is absent", key)
		}
	}
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&fence); err != nil {
		return ports.ContentFence{}, fmt.Errorf("Content fence response invalid: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return ports.ContentFence{}, errors.New("Content fence response has trailing data")
	}
	if fence.Environment != r.environment || fence.SourceOwner != "qwq_data" {
		return ports.ContentFence{}, errors.New("Content fence query identity drift")
	}
	if !fence.Found {
		if fence.ReleaseID != "" || fence.ManifestDigest != "" || fence.Revision != 0 || fence.ProjectionVersion != 0 || fence.ActivatedAt != nil {
			return ports.ContentFence{}, errors.New("Content absent fence contains state")
		}
		return fence, nil
	}
	if strings.TrimSpace(fence.ReleaseID) == "" || !regexp.MustCompile(`^sha256:[0-9a-f]{64}$`).MatchString(fence.ManifestDigest) || fence.Revision <= 0 || fence.ProjectionVersion <= 0 || fence.ActivatedAt == nil || fence.ActivatedAt.IsZero() {
		return ports.ContentFence{}, errors.New("Content active fence is incomplete")
	}
	return fence, nil
}
