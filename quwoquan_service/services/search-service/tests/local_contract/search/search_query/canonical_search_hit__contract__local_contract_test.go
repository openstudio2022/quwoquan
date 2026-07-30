package local_contract

import (
	"encoding/json"
	"strings"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	searchhttp "quwoquan_service/services/search-service/internal/search/search_query/adapters/inbound/http"
)

func TestCanonicalSearchHitUsesTypedContentSliceWithoutPayload(t *testing.T) {
	hit := searchhttp.CanonicalSearchHit(rtsearch.RetrieveHit{
		Target: rtsearch.TargetPhoto, ObjectType: "content.post", ObjectID: "post_1",
		Title: "川西日落", Snippet: "雪山下的日落",
		Payload: map[string]any{
			"contentIdentity": "work", "coverUrl": "https://cdn.example/cover.jpg",
			"likeCount": float64(12), "unknownPrivateKey": "must-not-leak",
		},
	})
	if hit.Content == nil || hit.Content.PostID != "post_1" || hit.Content.ContentType != "image" {
		t.Fatalf("typed content slice mismatch: %#v", hit.Content)
	}
	if hit.Payload != nil {
		t.Fatalf("content hit must not expose generic payload: %#v", hit.Payload)
	}
	encoded, err := json.Marshal(hit)
	if err != nil {
		t.Fatalf("marshal canonical hit: %v", err)
	}
	if strings.Contains(string(encoded), "unknownPrivateKey") || strings.Contains(string(encoded), `"payload"`) {
		t.Fatalf("content hit leaked arbitrary payload: %s", encoded)
	}
}

func TestCanonicalSearchHitBoundsNonContentPayload(t *testing.T) {
	hit := searchhttp.CanonicalSearchHit(rtsearch.RetrieveHit{
		Target: rtsearch.TargetEntity, ObjectType: "entity.homepage", ObjectID: "home_1",
		Title: "四姑娘山",
		Payload: map[string]any{
			"coverUrl": "https://cdn.example/entity.jpg", "followerCount": float64(7),
			"unknownPrivateKey": "must-not-leak",
		},
	})
	if hit.Content != nil || hit.Payload == nil || hit.Payload.FollowerCount == nil || *hit.Payload.FollowerCount != 7 {
		t.Fatalf("bounded entity payload mismatch: %#v", hit)
	}
	encoded, err := json.Marshal(hit)
	if err != nil {
		t.Fatalf("marshal canonical hit: %v", err)
	}
	if strings.Contains(string(encoded), "unknownPrivateKey") {
		t.Fatalf("non-content hit leaked arbitrary payload: %s", encoded)
	}
}
