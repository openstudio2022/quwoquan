package main

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/runtime/servicekit"
)

// TestRegisterProductOpsRoutesLeavesCanonicalProbesToServicekit 锁定领域路由
// 只拥有声明的业务前缀，不以根 fallback 建立第二套探针面。Bootstrap 外层的
// /readyz 因而始终可以按 canonical readiness checker 回答。
func TestRegisterProductOpsRoutesLeavesCanonicalProbesToServicekit(t *testing.T) {
	assembly := &servicekit.Assembly{Mux: http.NewServeMux()}
	registerProductOpsRouteHandler(assembly, http.NotFoundHandler())

	for _, path := range []string{"/healthz", "/readyz", "/metrics", "/not-owned"} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		if _, pattern := assembly.Mux.Handler(request); pattern != "" {
			t.Fatalf("product domain must not own %s; matched pattern %q", path, pattern)
		}
	}

	for _, path := range []string{
		"/ops/events",
		"/control-plane/product/experiments",
		"/download/android/latest.json",
	} {
		request := httptest.NewRequest(http.MethodGet, path, nil)
		if _, pattern := assembly.Mux.Handler(request); pattern == "" {
			t.Fatalf("product domain route %s is not registered", path)
		}
	}
}
