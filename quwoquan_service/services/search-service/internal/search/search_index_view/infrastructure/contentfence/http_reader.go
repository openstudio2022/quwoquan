package contentfence

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/auth"
	rt "quwoquan_service/runtime/search"
	app "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"strings"
	"time"
)

type Reader struct {
	endpoint    string
	credentials auth.ServiceAuthorizationProvider
	client      *http.Client
}

func NewReader(base, environment string, credentials auth.ServiceAuthorizationProvider) (*Reader, error) {
	u, err := url.Parse(base)
	if err != nil || u.Host == "" || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil || u.RawQuery != "" || u.Fragment != "" || credentials == nil {
		return nil, fmt.Errorf("invalid Content fence transport binding")
	}
	path := ""
	for _, d := range operationsecurity.ForDomain("content") {
		if d.CanonicalOperationID == "content.post.ReadActiveReleaseFence" && d.Method == http.MethodGet {
			path = d.PathTemplate
		}
	}
	if path == "" {
		return nil, fmt.Errorf("Content fence contract absent")
	}
	u.Path = strings.TrimRight(u.Path, "/") + path
	u.RawQuery = url.Values{"environment": {environment}, "sourceOwner": {"qwq_data"}}.Encode()
	return &Reader{u.String(), credentials, &http.Client{Timeout: 500 * time.Millisecond, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}, nil
}
func (r *Reader) Read(ctx context.Context) (app.ContentCreatorFence, error) {
	var fence app.ContentCreatorFence
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, r.endpoint, nil)
	if err != nil {
		return fence, err
	}
	authorization, err := r.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return fence, err
	}
	req.Header.Set("Authorization", authorization)
	response, err := r.client.Do(req)
	if err != nil {
		return fence, err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return fence, fmt.Errorf("Content fence status %d", response.StatusCode)
	}
	if err = rt.DecodeCreatorValue(response.Body, &fence); err != nil {
		return fence, err
	}
	return fence, nil
}
