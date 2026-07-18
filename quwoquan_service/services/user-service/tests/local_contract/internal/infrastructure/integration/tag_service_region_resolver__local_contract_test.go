package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	integration "quwoquan_service/services/user-service/internal/infrastructure/integration"
)

func TestTagServiceRegionResolverValidatesActiveDirectChild(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/tag/children" {
			t.Fatalf("unexpected path %s", r.URL.Path)
		}
		if got := r.URL.Query().Get("parentTagRef"); got != "Topic/地理/行政区/中国/广东省" {
			t.Fatalf("unexpected parentTagRef %s", got)
		}
		_ = json.NewEncoder(w).Encode([]map[string]any{
			{"tagRef": "Topic/地理/行政区/中国/广东省/深圳市", "lifecycleStatus": "active"},
		})
	}))
	defer server.Close()

	resolver := integration.NewTagServiceRegionResolver(server.URL, server.Client())
	display, err := resolver.ResolveRegionTag(context.Background(), "Topic/地理/行政区/中国/广东省/深圳市")
	if err != nil {
		t.Fatalf("expected valid regionTagRef: %v", err)
	}
	if display != "广东 深圳" {
		t.Fatalf("expected derived display, got %s", display)
	}
}

func TestTagServiceRegionResolverRejectsMissingChild(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode([]map[string]any{
			{"tagRef": "Topic/地理/行政区/中国/广东省/广州市", "lifecycleStatus": "active"},
		})
	}))
	defer server.Close()

	resolver := integration.NewTagServiceRegionResolver(server.URL, server.Client())
	if _, err := resolver.ResolveRegionTag(context.Background(), "Topic/地理/行政区/中国/广东省/深圳市"); err == nil {
		t.Fatal("expected missing direct child to fail")
	}
}
