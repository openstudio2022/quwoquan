// spec_ref: specs/feature-tree/discovery-content/content-service-cloud-production/remote-content-delivery/spec.md#gwt-001
package searchindex_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/searchindex"
)

func TestSearchIndexStartupWaitsForDelayedRecoverableDependency(t *testing.T) {
	// alias 版本化启动序列：GET /_alias/{index} -> HEAD /{index} ->
	// PUT /{index}-v1。可恢复依赖抖动发生在第一步的 alias 解析上。
	var aliasAttempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch {
		case request.Method == http.MethodGet && request.URL.Path == "/_alias/"+es.DefaultIndex:
			switch aliasAttempts.Add(1) {
			case 1:
				writer.WriteHeader(http.StatusTooManyRequests)
				return
			case 2:
				writer.WriteHeader(http.StatusServiceUnavailable)
				return
			}
			writer.WriteHeader(http.StatusNotFound)
		case request.Method == http.MethodHead && request.URL.Path == "/"+es.DefaultIndex:
			writer.WriteHeader(http.StatusNotFound)
		case request.Method == http.MethodPut && request.URL.Path == "/"+es.DefaultIndex+"-v1":
			writer.WriteHeader(http.StatusOK)
		default:
			http.Error(writer, "unexpected request", http.StatusTeapot)
		}
	}))
	defer server.Close()

	built, err := searchindex.Build(searchindex.ESConfig{
		Enabled:                 true,
		Endpoints:               []string{server.URL},
		RequestTimeoutMs:        50,
		StartupTimeoutMs:        500,
		StartupInitialBackoffMs: 5,
		StartupMaxBackoffMs:     10,
	}, fakeReader{})
	if err != nil {
		t.Fatalf("build search index: %v", err)
	}
	if err := built.EnsureIndexReady(context.Background()); err != nil {
		t.Fatalf("ensure delayed search index: %v", err)
	}
	if got := aliasAttempts.Load(); got != 3 {
		t.Fatalf("alias attempts=%d want=3", got)
	}
}

func TestSearchIndexStartupTimeoutIsBoundedAndFailClosed(t *testing.T) {
	built, err := searchindex.Build(searchindex.ESConfig{
		Enabled:                 true,
		Endpoints:               []string{"http://127.0.0.1:1"},
		RequestTimeoutMs:        20,
		StartupTimeoutMs:        40,
		StartupInitialBackoffMs: 5,
		StartupMaxBackoffMs:     10,
	}, fakeReader{})
	if err != nil {
		t.Fatalf("build search index: %v", err)
	}
	startedAt := time.Now()
	err = built.EnsureIndexReady(context.Background())
	if !errors.Is(err, searchindex.ErrSearchIndexStartupTimeout) {
		t.Fatalf("startup timeout error=%v", err)
	}
	if elapsed := time.Since(startedAt); elapsed > 250*time.Millisecond {
		t.Fatalf("startup timeout was not bounded: %s", elapsed)
	}
}

func TestSearchIndexStartupRejectsInvalidRetryConfiguration(t *testing.T) {
	for name, cfg := range map[string]searchindex.ESConfig{
		"negative timeout": {
			Enabled: true, Endpoints: []string{"http://127.0.0.1:9200"},
			StartupTimeoutMs: -1,
		},
		"initial exceeds maximum": {
			Enabled: true, Endpoints: []string{"http://127.0.0.1:9200"},
			StartupTimeoutMs: 100, StartupInitialBackoffMs: 20, StartupMaxBackoffMs: 10,
		},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := searchindex.Build(cfg, fakeReader{}); err == nil {
				t.Fatal("invalid startup retry configuration was accepted")
			}
		})
	}
}

func TestSearchIndexStartupDoesNotRetrySchemaOrAuthorizationFailures(t *testing.T) {
	tests := []struct {
		name       string
		headStatus int
		mapping    bool
		wantSchema bool
		wantCalls  int32
	}{
		{name: "authorization", headStatus: http.StatusUnauthorized, wantCalls: 1},
		{name: "schema", headStatus: http.StatusOK, mapping: true, wantSchema: true, wantCalls: 2},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			var calls atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
				calls.Add(1)
				// schema 分支：alias 解析出唯一物理索引后，additive
				// mapping 更新命中 mapper conflict，fail closed 不重试。
				if request.Method == http.MethodGet &&
					request.URL.Path == "/_alias/"+es.DefaultIndex && test.mapping {
					_, _ = writer.Write([]byte(`{"` + es.DefaultIndex + `-v1":{"aliases":{}}}`))
					return
				}
				if request.Method == http.MethodPut && test.mapping {
					writer.WriteHeader(http.StatusBadRequest)
					_, _ = writer.Write([]byte(`{"error":"mapper conflict"}`))
					return
				}
				writer.WriteHeader(test.headStatus)
			}))
			defer server.Close()

			built, err := searchindex.Build(searchindex.ESConfig{
				Enabled:                 true,
				Endpoints:               []string{server.URL},
				RequestTimeoutMs:        20,
				StartupTimeoutMs:        200,
				StartupInitialBackoffMs: 5,
				StartupMaxBackoffMs:     10,
			}, fakeReader{})
			if err != nil {
				t.Fatalf("build search index: %v", err)
			}
			err = built.EnsureIndexReady(context.Background())
			if err == nil {
				t.Fatal("non-retryable startup failure was accepted")
			}
			if test.wantSchema != errors.Is(err, es.ErrIndexSchemaIncompatible) {
				t.Fatalf("schema classification=%v error=%v", test.wantSchema, err)
			}
			if got := calls.Load(); got != test.wantCalls {
				t.Fatalf("calls=%d want=%d", got, test.wantCalls)
			}
		})
	}
}
