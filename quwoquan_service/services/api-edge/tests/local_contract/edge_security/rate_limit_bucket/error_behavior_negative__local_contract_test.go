// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
//
// owner proxy 错误行为负例：上游不可达时 ReverseProxy ErrorHandler 必须以
// 声明的稳定码 GATEWAY.MIDDLEWARE.upstream_unavailable fail-closed，并带
// Retry-After 恢复语义，而不是透传空响应或 502 裸错。
package local_contract

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"

	httpadapter "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/adapters/inbound/http"
)

// unreachableTransport 注入上游连接失败，驱动 ErrorHandler 路径。
type unreachableTransport struct{}

func (unreachableTransport) RoundTrip(*http.Request) (*http.Response, error) {
	return nil, errors.New("injected upstream connection failure")
}

func TestOwnerProxyUpstreamFailureEmitsUpstreamUnavailable(t *testing.T) {
	t.Parallel()
	upstream, err := url.Parse("http://owner-upstream.invalid")
	if err != nil {
		t.Fatal(err)
	}
	proxy, err := httpadapter.NewOwnerProxy(httpadapter.OwnerProxyConfig{
		Routes: []httpadapter.OwnerRoute{
			{OperationPrefix: "/content/", Upstream: upstream},
		},
		Transport: unreachableTransport{},
	})
	if err != nil {
		t.Fatalf("build owner proxy: %v", err)
	}

	recorder := httptest.NewRecorder()
	proxy.ServeHTTP(
		recorder,
		httptest.NewRequest(http.MethodGet, "/content/feed", nil),
	)

	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want 503 (body=%s)", recorder.Code, recorder.Body.String())
	}
	if retry := recorder.Header().Get("Retry-After"); retry == "" {
		t.Fatal("upstream failure must carry Retry-After recovery semantics")
	}
	var body struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode error body %q: %v", recorder.Body.String(), err)
	}
	if body.Code != "GATEWAY.MIDDLEWARE.upstream_unavailable" {
		t.Fatalf("code = %s, want GATEWAY.MIDDLEWARE.upstream_unavailable", body.Code)
	}
}
