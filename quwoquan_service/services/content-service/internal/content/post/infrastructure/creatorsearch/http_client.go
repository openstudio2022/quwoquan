package creatorsearch

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
	"net/http"
	"net/url"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/auth"
	runtimeobservability "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/operation"
	rt "quwoquan_service/runtime/search"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"strings"
	"time"
)

// Client只消费生成operation descriptor和共享值，Content不导入User/Search internal。
type Client struct {
	userURL, searchURL                                 string
	userCredential, prepareCredential, queryCredential auth.ServiceAuthorizationProvider
	http                                               *http.Client
}

func NewClient(userURL, searchURL string, user, prepare, query auth.ServiceAuthorizationProvider) (*Client, error) {
	for _, raw := range []string{userURL, searchURL} {
		u, err := url.Parse(raw)
		if err != nil || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || (u.Scheme != "http" && u.Scheme != "https") {
			return nil, fmt.Errorf("invalid Creator owner transport")
		}
	}
	if user == nil || prepare == nil || query == nil {
		return nil, fmt.Errorf("Creator owner credentials required")
	}
	return &Client{strings.TrimRight(userURL, "/"), strings.TrimRight(searchURL, "/"), user, prepare, query, &http.Client{CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}, nil
}
func (c *Client) call(ctx context.Context, base, domain, operationID string, credential auth.ServiceAuthorizationProvider, timeout time.Duration, input, output any, commandKey string) error {
	path := ""
	method := ""
	for _, d := range operationsecurity.ForDomain(domain) {
		if d.CanonicalOperationID == operationID {
			path = d.PathTemplate
			method = d.Method
		}
	}
	if path == "" || method != "POST" {
		return fmt.Errorf("Creator operation unavailable")
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, method, base+path, bytes.NewReader(raw))
	if err != nil {
		return err
	}
	authorization, err := credential.AuthorizationHeader(ctx)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", authorization)
	req.Header.Set("Content-Type", "application/json")
	if commandKey != "" {
		req.Header.Set("Idempotency-Key", commandKey)
	}
	if current, ok := operation.FromContext(ctx); ok {
		req.Header.Set("X-Request-Id", current.RequestID)
		req.Header.Set("X-Trace-Id", current.TraceID)
	}
	if meta, ok := runtimeobservability.CorrelationMetaFromContext(ctx); ok {
		if req.Header.Get("X-Request-Id") == "" {
			req.Header.Set("X-Request-Id", meta.RequestID)
		}
		if req.Header.Get("X-Trace-Id") == "" {
			req.Header.Set("X-Trace-Id", meta.TraceID)
		}
	}
	otel.GetTextMapPropagator().Inject(ctx, propagation.HeaderCarrier(req.Header))
	response, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return fmt.Errorf("Creator operation %s status %d", operationID, response.StatusCode)
	}
	return rt.DecodeCreatorValue(response.Body, output)
}
func (c *Client) ReadCreatorCandidate(ctx context.Context, b rt.ReleaseCandidateBinding) (rt.CreatorSearchCandidateSnapshot, error) {
	var result struct {
		Found    bool                               `json:"found"`
		Snapshot *rt.CreatorSearchCandidateSnapshot `json:"snapshot"`
	}
	err := c.call(ctx, c.userURL, "user", "user.user_account.ReadCreatorSearchCandidate", c.userCredential, 1500*time.Millisecond, struct {
		Release rt.ReleaseCandidateBinding `json:"release"`
	}{b}, &result, "")
	if err != nil {
		return rt.CreatorSearchCandidateSnapshot{}, err
	}
	if !result.Found || result.Snapshot == nil {
		return rt.CreatorSearchCandidateSnapshot{}, app.ErrReleaseQueryNotReady
	}
	if result.Snapshot.Release != b || result.Snapshot.Validate() != nil {
		return rt.CreatorSearchCandidateSnapshot{}, app.ErrReleaseQueryInvalid
	}
	return *result.Snapshot, nil
}

type preparationView struct {
	PreparationID  string                            `json:"preparationId"`
	Binding        rt.ReleaseQueryPreparationBinding `json:"binding"`
	SnapshotDigest string                            `json:"snapshotDigest"`
	Version        int64                             `json:"version"`
	Status         string                            `json:"status"`
	FailureCode    *string                           `json:"failureCode"`
	Proof          *rt.ReleaseQueryReadinessProof    `json:"proof"`
	UpdatedAt      time.Time                         `json:"updatedAt"`
}

func (c *Client) PrepareSearchRelease(ctx context.Context, b rt.ReleaseQueryPreparationBinding, s rt.SearchReleaseCandidateSnapshot, version int64, key string) error {
	if strings.TrimSpace(key) == "" || len(key) > 128 || version < 0 {
		return app.ErrReleaseQueryInvalid
	}
	var result preparationView
	err := c.call(ctx, c.searchURL, "search", "search.search_release_preparation.PrepareSearchRelease", c.prepareCredential, 30*time.Second, struct {
		Binding         rt.ReleaseQueryPreparationBinding `json:"binding"`
		Snapshot        rt.SearchReleaseCandidateSnapshot `json:"snapshot"`
		ExpectedVersion int64                             `json:"expectedVersion"`
		IdempotencyKey  string                            `json:"idempotencyKey"`
	}{b, s, version, key}, &result, key)
	if err != nil {
		return err
	}
	if result.Binding != b || result.PreparationID != b.ID() || result.SnapshotDigest != s.SnapshotDigest() {
		return app.ErrReleaseQueryInvalid
	}
	return nil
}
func (c *Client) ReadSearchProof(ctx context.Context, b rt.ReleaseQueryPreparationBinding, digest string) (rt.ReleaseQueryReadinessProof, error) {
	var result preparationView
	err := c.call(ctx, c.searchURL, "search", "search.search_release_preparation.ReadSearchReleasePreparation", c.queryCredential, 2*time.Second, struct {
		Binding        rt.ReleaseQueryPreparationBinding `json:"binding"`
		SnapshotDigest string                            `json:"snapshotDigest"`
	}{b, digest}, &result, "")
	if err != nil {
		return rt.ReleaseQueryReadinessProof{}, err
	}
	if result.Binding != b || result.PreparationID != b.ID() || result.SnapshotDigest != digest {
		return rt.ReleaseQueryReadinessProof{}, app.ErrReleaseQueryInvalid
	}
	if result.Status != "completed" || result.Proof == nil {
		return rt.ReleaseQueryReadinessProof{}, app.ErrReleaseQueryNotReady
	}
	return *result.Proof, nil
}

var _ app.SearchPreparationPort = (*Client)(nil)
