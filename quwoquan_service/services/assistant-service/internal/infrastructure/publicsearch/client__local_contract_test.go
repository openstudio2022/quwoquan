package publicsearch

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/application"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return fn(request)
}

func TestExtractDuckDuckGoResultsNormalizesRedirectAndSource(t *testing.T) {
	raw := `
<div class="result">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fsupport.huaweicloud.com%2Fprice-desc-ecs%2Fecs_01_0001.html">弹性云服务器 ECS 价格详情 - 华为云</a>
  <div class="result__snippet">官方价格详情页，包含按需和包年包月说明。</div>
</div>`
	references := extractDuckDuckGoResults(raw)
	if len(references) != 1 {
		t.Fatalf("references=%#v", references)
	}
	if references[0].URL != "https://support.huaweicloud.com/price-desc-ecs/ecs_01_0001.html" {
		t.Fatalf("url=%q", references[0].URL)
	}
	if references[0].Source != "support.huaweicloud.com" {
		t.Fatalf("source=%q", references[0].Source)
	}
	if references[0].Snippet == "" || references[0].Rank != 1 {
		t.Fatalf("reference=%+v", references[0])
	}
}

func TestSearchDoesNotSelectUnboundBingFallback(t *testing.T) {
	var hosts []string
	client, err := New(
		Config{SearchURL: "https://duckduckgo.com/html/"},
		&http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
			hosts = append(hosts, request.URL.Host)
			return &http.Response{
				StatusCode: http.StatusServiceUnavailable,
				Body:       io.NopCloser(strings.NewReader("unavailable")),
				Header:     make(http.Header),
			}, nil
		})},
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}

	_, err = client.Search(context.Background(), application.ExternalSearchRequest{Query: "可疑供应商切换"})
	var failure application.ProviderFailure
	if !errors.As(err, &failure) {
		t.Fatalf("error = %v, want ProviderFailure", err)
	}
	if failure.Capability != "public_search" || failure.Reason != application.ProviderFailureUnavailable {
		t.Fatalf("failure = %+v", failure)
	}
	if len(hosts) != 2 {
		t.Fatalf("requests = %v, want two DuckDuckGo retry attempts", hosts)
	}
	for _, host := range hosts {
		if host != "duckduckgo.com" {
			t.Fatalf("unexpected implicit provider fallback host %q", host)
		}
	}
}
