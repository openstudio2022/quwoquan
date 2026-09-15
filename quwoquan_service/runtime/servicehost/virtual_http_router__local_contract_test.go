// spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t5
package servicehost

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestVirtualHTTPRouterPreservesHostnameIdentityOnSharedPort(t *testing.T) {
	t.Parallel()

	userUpstream := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, _ *http.Request) {
			_, _ = writer.Write([]byte("user"))
		},
	))
	defer userUpstream.Close()
	chatUpstream := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, _ *http.Request) {
			_, _ = writer.Write([]byte("chat"))
		},
	))
	defer chatUpstream.Close()
	contentUpstream := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			if request.Header.Get("Authorization") != "Bearer service-token" {
				http.Error(writer, "unauthorized", http.StatusUnauthorized)
				return
			}
			_, _ = writer.Write([]byte("content"))
		},
	))
	defer contentUpstream.Close()

	router, err := NewVirtualHTTPRouter(
		VirtualHTTPRoute{
			Host:       "user-service",
			PublicAddr: "127.0.0.1:0",
			Upstream:   userUpstream.URL,
		},
		VirtualHTTPRoute{
			Host:       "chat-service",
			PublicAddr: "127.0.0.1:0",
			Upstream:   chatUpstream.URL,
		},
		VirtualHTTPRoute{
			Host:       "content-service",
			PublicAddr: "127.0.0.1:0",
			Upstream:   contentUpstream.URL,
		},
	)
	if err != nil {
		t.Fatalf("NewVirtualHTTPRouter() error = %v", err)
	}
	if err := router.Bind(context.Background()); err != nil {
		t.Fatalf("Bind() error = %v", err)
	}
	if err := router.Start(context.Background()); err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		if err := router.Shutdown(ctx); err != nil {
			t.Errorf("Shutdown() error = %v", err)
		}
	}()

	address := "http://" + router.groups[0].listener.Addr().String()
	if status, body := virtualHTTPGet(t, address, "user-service:18081"); status != http.StatusOK || body != "user" {
		t.Fatalf("closed health route = (%d, %q), want (%d, %q)", status, body, http.StatusOK, "user")
	}
	if status, _ := virtualHTTPGetPath(
		t,
		address,
		"user-service:18081",
		"/operations/private",
	); status != http.StatusServiceUnavailable {
		t.Fatalf("closed operation status = %d, want %d", status, http.StatusServiceUnavailable)
	}
	if status, body := virtualHTTPGetPath(
		t,
		address,
		"user-service:18081",
		"/internal/user/account-security/health",
	); status != http.StatusOK || body != "user" {
		t.Fatalf(
			"closed readiness route = (%d, %q), want (%d, %q)",
			status,
			body,
			http.StatusOK,
			"user",
		)
	}
	if status, _ := virtualHTTPRequestPath(
		t,
		http.MethodGet,
		address,
		"content-service:18081",
		activeReleaseFencePath+"?environment=gamma&sourceOwner=qwq_data",
	); status != http.StatusUnauthorized {
		t.Fatalf("closed anonymous active release fence status = %d, want %d", status, http.StatusUnauthorized)
	}
	if status, body := virtualHTTPRequestPathWithAuthorization(
		t,
		http.MethodGet,
		address,
		"content-service:18081",
		activeReleaseFencePath+"?environment=gamma&sourceOwner=qwq_data",
		"Bearer service-token",
	); status != http.StatusOK || body != "content" {
		t.Fatalf(
			"closed authenticated active release fence = (%d, %q), want (%d, %q)",
			status,
			body,
			http.StatusOK,
			"content",
		)
	}
	if status, _ := virtualHTTPRequestPath(
		t,
		http.MethodGet,
		address,
		"user-service:18081",
		activeReleaseFencePath,
	); status != http.StatusServiceUnavailable {
		t.Fatalf("closed fence wrong service host status = %d, want %d", status, http.StatusServiceUnavailable)
	}
	if status, _ := virtualHTTPRequestPath(
		t,
		http.MethodGet,
		address,
		"unknown-service:18081",
		activeReleaseFencePath,
	); status != http.StatusMisdirectedRequest {
		t.Fatalf("closed fence unknown host status = %d, want %d", status, http.StatusMisdirectedRequest)
	}
	for _, blocked := range []struct {
		name   string
		method string
		path   string
	}{
		{name: "post exact fence", method: http.MethodPost, path: activeReleaseFencePath},
		{name: "similar fence path", method: http.MethodGet, path: activeReleaseFencePath + "/"},
		{name: "other business path", method: http.MethodGet, path: "/operations/private"},
	} {
		blocked := blocked
		t.Run(blocked.name, func(t *testing.T) {
			if status, _ := virtualHTTPRequestPath(
				t,
				blocked.method,
				address,
				"content-service:18081",
				blocked.path,
			); status != http.StatusServiceUnavailable {
				t.Fatalf("closed route status = %d, want %d", status, http.StatusServiceUnavailable)
			}
		})
	}

	router.OpenAdmission()
	if status, body := virtualHTTPGet(t, address, "user-service:18081"); status != http.StatusOK || body != "user" {
		t.Fatalf("user route = (%d, %q), want (%d, %q)", status, body, http.StatusOK, "user")
	}
	if status, body := virtualHTTPGet(t, address, "chat-service:18081"); status != http.StatusOK || body != "chat" {
		t.Fatalf("chat route = (%d, %q), want (%d, %q)", status, body, http.StatusOK, "chat")
	}
	if status, _ := virtualHTTPGet(t, address, "unknown-service:18081"); status != http.StatusMisdirectedRequest {
		t.Fatalf("unknown route status = %d, want %d", status, http.StatusMisdirectedRequest)
	}
}

func virtualHTTPGet(t *testing.T, address string, host string) (int, string) {
	return virtualHTTPGetPath(t, address, host, "/healthz")
}

func virtualHTTPGetPath(
	t *testing.T,
	address string,
	host string,
	path string,
) (int, string) {
	t.Helper()
	return virtualHTTPRequestPath(t, http.MethodGet, address, host, path)
}

func virtualHTTPRequestPath(
	t *testing.T,
	method string,
	address string,
	host string,
	path string,
) (int, string) {
	t.Helper()
	return virtualHTTPRequestPathWithAuthorization(t, method, address, host, path, "")
}

func virtualHTTPRequestPathWithAuthorization(
	t *testing.T,
	method string,
	address string,
	host string,
	path string,
	authorization string,
) (int, string) {
	t.Helper()
	request, err := http.NewRequestWithContext(
		context.Background(),
		method,
		address+path,
		nil,
	)
	if err != nil {
		t.Fatalf("NewRequestWithContext() error = %v", err)
	}
	request.Host = host
	if authorization != "" {
		request.Header.Set("Authorization", authorization)
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("Do() error = %v", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatalf("ReadAll() error = %v", err)
	}
	return response.StatusCode, string(body)
}
