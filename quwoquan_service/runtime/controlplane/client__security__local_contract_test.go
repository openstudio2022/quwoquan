package controlplane

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

type staticConfigSyncAuthorization string

func (authorization staticConfigSyncAuthorization) AuthorizationHeader(context.Context) (string, error) {
	return string(authorization), nil
}

func TestConfigSyncClientUsesMachineAuthorizationForResolveAndAck(t *testing.T) {
	requests := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests++
		if got := r.Header.Get("Authorization"); got != "Bearer service-machine-token" {
			t.Fatalf("authorization=%q", got)
		}
		switch r.URL.Path {
		case "/control-plane/platform/configs/resolve-for-instance":
			_, _ = w.Write([]byte(`{
				"desiredHash":"desired",
				"effectiveHash":"desired",
				"source":"release-package",
				"values":[]
			}`))
		case "/control-plane/platform/configs/instances/content-service-prod-a-0:report":
			w.WriteHeader(http.StatusOK)
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	client := NewClient(server.URL, server.Client()).WithServiceAuthorization(
		staticConfigSyncAuthorization("Bearer service-machine-token"),
	)
	if _, err := client.Resolve(context.Background(), ConfigResolutionScope{
		Environment: "prod",
		Service:     "content-service",
	}); err != nil {
		t.Fatalf("resolve: %v", err)
	}
	if err := client.ReportInstance(context.Background(), InstanceConfigReport{
		ID:          "content-service-prod-a-0",
		InstanceID:  "content-service-prod-a-0",
		Service:     "content-service",
		Environment: "prod",
	}); err != nil {
		t.Fatalf("report: %v", err)
	}
	if requests != 2 {
		t.Fatalf("requests=%d want=2", requests)
	}
}

func TestConfigSyncClientRejectsMissingMachineAuthorization(t *testing.T) {
	client := NewClient("https://platform-ops.invalid", http.DefaultClient)
	if _, err := client.Resolve(context.Background(), ConfigResolutionScope{
		Environment: "prod",
		Service:     "content-service",
	}); err == nil {
		t.Fatal("resolve without machine authorization must fail closed")
	}
}
