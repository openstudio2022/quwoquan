package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	httpadapter "quwoquan_service/services/chat-service/internal/adapters/http"
)

func TestContactHomeProjection_CircleListResolverClient(t *testing.T) {
	t.Parallel()

	circleServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/circles" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"items": []map[string]any{
				{
					"circleId":    "fixture_circle_photo",
					"displayName": "契约摄影圈",
					"avatarUrl":   "media/avatar/s/archived-avatar/circle/fixture_circle_photo/v1/avatar.png",
					"description": "890",
				},
			},
		})
	}))
	t.Cleanup(circleServer.Close)

	resolver := httpadapter.NewCircleListResolverClient(circleServer.URL, circleServer.Client())
	items, err := resolver.ListCircles(context.Background(), "fixture_user_current", 10)
	if err != nil {
		t.Fatalf("ListCircles: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("expected 1 circle, got %d", len(items))
	}
	if items[0].CircleID != "fixture_circle_photo" {
		t.Fatalf("unexpected circle id: %s", items[0].CircleID)
	}
	if items[0].AvatarURL == "" {
		t.Fatal("expected circle avatarUrl")
	}
}
