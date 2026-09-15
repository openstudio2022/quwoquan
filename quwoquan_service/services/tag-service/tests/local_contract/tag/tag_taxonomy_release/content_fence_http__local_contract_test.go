package tag_taxonomy_release_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/contentfence"
)

type fenceCredential string

func (c fenceCredential) AuthorizationHeader(context.Context) (string, error) { return string(c), nil }

// spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001
func TestContentFenceHTTPRejectsIncompleteDriftAndTransportFailure(t *testing.T) {
	valid := func() map[string]any {
		return map[string]any{"found": true, "environment": "gamma", "sourceOwner": "qwq_data", "releaseId": "a", "manifestDigest": "sha256:" + strings.Repeat("a", 64), "revision": 3, "projectionVersion": 2, "activatedAt": "2026-09-12T00:00:00Z"}
	}
	tests := []struct {
		name   string
		mutate func(map[string]any)
		status int
	}{
		{"complete", func(map[string]any) {}, 200},
		{"environment", func(m map[string]any) { m["environment"] = "prod" }, 200},
		{"owner", func(m map[string]any) { m["sourceOwner"] = "other" }, 200},
		{"revision", func(m map[string]any) { m["revision"] = 0 }, 200},
		{"digest", func(m map[string]any) { m["manifestDigest"] = "broken" }, 200},
		{"missing-found", func(m map[string]any) { delete(m, "found") }, 200},
		{"missing-time", func(m map[string]any) { delete(m, "activatedAt") }, 200},
		{"empty-found", func(m map[string]any) { m["found"] = nil }, 200},
		{"absent-with-state", func(m map[string]any) { m["found"] = false }, 200},
		{"unauthorized", func(map[string]any) {}, 401},
		{"unavailable", func(map[string]any) {}, 503},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			calls := 0
			body := valid()
			test.mutate(body)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				calls++
				if r.Header.Get("Authorization") != "Bearer service-token" {
					t.Error("credential missing")
				}
				w.WriteHeader(test.status)
				_ = json.NewEncoder(w).Encode(body)
			}))
			defer server.Close()
			reader, err := contentfence.NewHTTPReader(server.URL, "gamma", 500*time.Millisecond, fenceCredential("Bearer service-token"))
			if err != nil {
				t.Fatal(err)
			}
			_, err = reader.ReadActiveContentFence(context.Background())
			if (err == nil) != (test.name == "complete") {
				t.Fatalf("error=%v", err)
			}
			if calls != 1 {
				t.Fatalf("retry count=%d", calls)
			}
		})
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-r.Context().Done() }))
	defer server.Close()
	reader, err := contentfence.NewHTTPReader(server.URL, "gamma", 10*time.Millisecond, fenceCredential("Bearer service-token"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := reader.ReadActiveContentFence(context.Background()); err == nil {
		t.Fatal("deadline not enforced")
	}
}
