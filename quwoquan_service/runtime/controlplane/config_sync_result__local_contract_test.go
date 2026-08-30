package controlplane

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func configSyncAuthEnvironment(t *testing.T) {
	t.Helper()
	t.Setenv("AUTH_JWT_SECRET", strings.Repeat("s", 64))
	t.Setenv("AUTH_JWT_ISSUER", "quwoquan-auth")
	t.Setenv("AUTH_JWT_AUDIENCE", "quwoquan-app")
	t.Setenv("AUTH_JWT_TOKEN_VERSION", "1")
}

func TestConfigSyncLoopReportsSyncResultToCallback(t *testing.T) {
	configSyncAuthEnvironment(t)
	server := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			switch {
			case strings.HasSuffix(request.URL.Path, "/configs/resolve-for-instance"):
				_ = json.NewEncoder(writer).Encode(ConfigResolveResponse{
					EffectiveHash: "hash-a",
					DesiredHash:   "hash-a",
					Source:        "config-center",
				})
			case strings.Contains(request.URL.Path, ":report"):
				writer.WriteHeader(http.StatusOK)
			default:
				http.NotFound(writer, request)
			}
		},
	))
	defer server.Close()

	ctx, cancel := context.WithCancel(context.Background())
	var results []ConfigSyncResult
	RunConfigSyncLoopContext(ctx, ConfigSyncLoopOptions{
		BaseURL:      server.URL,
		ServiceName:  "circle-service",
		AppEnv:       "alpha",
		ConfigRoot:   t.TempDir(),
		ImageVersion: "sha256:abc",
		InstanceID:   "pod-1",
		OnSyncResult: func(result ConfigSyncResult) {
			results = append(results, result)
			cancel()
		},
	})

	if len(results) != 1 {
		t.Fatalf("expected exactly one sync result, got %d", len(results))
	}
	result := results[0]
	if result.SyncErr != nil {
		t.Fatalf("expected successful resolve, got %v", result.SyncErr)
	}
	if !result.InSync || result.Source != "config-center" {
		t.Fatalf("unexpected sync result: %+v", result)
	}
	if result.ReportErr != nil {
		t.Fatalf("expected accepted report, got %v", result.ReportErr)
	}
}

func TestConfigSyncLoopReportsResolveFailureToCallback(t *testing.T) {
	configSyncAuthEnvironment(t)
	server := httptest.NewServer(http.HandlerFunc(
		func(writer http.ResponseWriter, _ *http.Request) {
			writer.WriteHeader(http.StatusInternalServerError)
		},
	))
	defer server.Close()

	ctx, cancel := context.WithCancel(context.Background())
	var results []ConfigSyncResult
	RunConfigSyncLoopContext(ctx, ConfigSyncLoopOptions{
		BaseURL:      server.URL,
		ServiceName:  "circle-service",
		AppEnv:       "alpha",
		ConfigRoot:   t.TempDir(),
		ImageVersion: "sha256:abc",
		InstanceID:   "pod-1",
		OnSyncResult: func(result ConfigSyncResult) {
			results = append(results, result)
			cancel()
		},
	})

	if len(results) != 1 {
		t.Fatalf("expected exactly one sync result, got %d", len(results))
	}
	if results[0].SyncErr == nil {
		t.Fatal("expected SyncErr when resolve and disk fallback both fail")
	}
	if results[0].InSync {
		t.Fatal("failed resolve must not claim in-sync")
	}
}
