package taxonomyvalidation

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rtrec "quwoquan_service/runtime/recommendation"
)

const tagResolveOperationID = "tag.tag_node_view.ResolveTag"

// HTTPSameAsResolver resolves cross-axis concept bridges (sameAsRefs) from
// tag-service and caches them for the process lifetime.
//
// Caching is safe because a tag taxonomy release is immutable: a tagRef's
// sameAsRefs cannot change without activating a new release, which restarts the
// consumer. Negative results are cached too, otherwise the overwhelming majority
// of tags (which declare no bridge) would hit the network on every behavior batch.
//
// It is deliberately fail-open: a bridge is an enrichment, so an unavailable
// tag-service degrades affinity to single-axis propagation rather than dropping
// the whole behavior batch.
type HTTPSameAsResolver struct {
	baseURL string
	path    string
	client  *http.Client
	timeout time.Duration

	mu    sync.RWMutex
	cache map[string][]string
}

func NewHTTPSameAsResolver(
	baseURL string,
	timeout time.Duration,
	options ...HTTPActiveTaxonomyLeafValidatorOption,
) (*HTTPSameAsResolver, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil {
		return nil, errRequiredDependencyUnavailable(
			"tag same-as resolution requires a valid tag-service endpoint")
	}
	if timeout <= 0 {
		return nil, errRequiredDependencyUnavailable(
			"tag same-as resolution requires a positive request timeout")
	}
	path, err := tagResolvePathTemplate()
	if err != nil {
		return nil, err
	}
	resolver := &HTTPSameAsResolver{
		baseURL: strings.TrimRight(parsed.String(), "/"),
		path:    path,
		client:  &http.Client{Timeout: timeout},
		timeout: timeout,
		cache:   make(map[string][]string),
	}
	// Reuse the validator's option type so composition wires one HTTP client for
	// both tag-service adapters instead of maintaining two option families.
	probe := &HTTPActiveTaxonomyLeafValidator{client: resolver.client}
	for _, option := range options {
		if option != nil {
			option(probe)
		}
	}
	resolver.client = probe.client
	return resolver, nil
}

// tagResolvePathTemplate returns the generated ResolveTag path, which carries a
// single {tagRef} placeholder.
func tagResolvePathTemplate() (string, error) {
	for _, descriptor := range operationsecurity.ForDomain("tag") {
		if descriptor.CanonicalOperationID != tagResolveOperationID {
			continue
		}
		if descriptor.Method != http.MethodGet ||
			!strings.Contains(descriptor.PathTemplate, "{tagRef}") {
			return "", errRequiredDependencyUnavailable(
				"tag resolve generated operation descriptor is invalid")
		}
		return descriptor.PathTemplate, nil
	}
	return "", errRequiredDependencyUnavailable(
		"tag resolve generated operation descriptor is missing")
}

type tagResolveResponse struct {
	TagRef     string   `json:"tagRef"`
	SameAsRefs []string `json:"sameAsRefs"`
}

// SameAsRefs implements rtrec.SameAsResolver.
func (r *HTTPSameAsResolver) SameAsRefs(tagRef string) []string {
	if r == nil {
		return nil
	}
	tagRef = strings.TrimSpace(tagRef)
	if tagRef == "" {
		return nil
	}

	r.mu.RLock()
	cached, ok := r.cache[tagRef]
	r.mu.RUnlock()
	if ok {
		return cached
	}

	refs := r.fetch(tagRef)
	r.mu.Lock()
	r.cache[tagRef] = refs
	r.mu.Unlock()
	return refs
}

func (r *HTTPSameAsResolver) fetch(tagRef string) []string {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	endpoint := r.baseURL + strings.ReplaceAll(
		r.path, "{tagRef}", url.PathEscape(tagRef))
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil
	}
	request.Header.Set("X-Internal-Service", "content-service")

	response, err := r.client.Do(request)
	if err != nil {
		return nil
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		discardResponse(response.Body)
		return nil
	}

	var decoded tagResolveResponse
	if err := json.NewDecoder(io.LimitReader(response.Body, 1024*1024)).
		Decode(&decoded); err != nil {
		return nil
	}

	refs := make([]string, 0, len(decoded.SameAsRefs))
	for _, raw := range decoded.SameAsRefs {
		ref := strings.TrimSpace(raw)
		if ref != "" && ref != tagRef {
			refs = append(refs, ref)
		}
	}
	if len(refs) == 0 {
		return nil
	}
	return refs
}

var _ rtrec.SameAsResolver = (*HTTPSameAsResolver)(nil)
