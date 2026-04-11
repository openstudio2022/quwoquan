package tests

import (
	"net/http"
	"testing"
)

func TestSearchCirclesShape(t *testing.T) {
	defer cleanCollections(t)

	createTestCircle(t, "可搜圈子Alpha")
	createTestCircle(t, "另一个Beta")

	rec := doRequest(t, http.MethodGet, "/v1/circles/search?query=alpha&limit=10", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	items, ok := body["items"].([]any)
	if !ok {
		t.Fatalf("expected items array, got %T", body["items"])
	}
	if len(items) < 1 {
		t.Fatalf("expected at least one search hit, got %d", len(items))
	}
	first, ok := items[0].(map[string]any)
	if !ok {
		t.Fatalf("expected object item, got %T", items[0])
	}
	for _, key := range []string{"circleId", "name", "memberCount", "postCount"} {
		if _, ok := first[key]; !ok {
			t.Errorf("missing key %q on search item", key)
		}
	}
	buckets, ok := body["facetBuckets"].([]any)
	if !ok {
		t.Fatalf("expected facetBuckets array, got %T", body["facetBuckets"])
	}
	if len(buckets) < 1 {
		t.Fatalf("expected at least one facet bucket, got %d", len(buckets))
	}
	b0, ok := buckets[0].(map[string]any)
	if !ok {
		t.Fatalf("expected object bucket, got %T", buckets[0])
	}
	for _, key := range []string{"facetKey", "label", "facetCount"} {
		if _, ok := b0[key]; !ok {
			t.Errorf("missing key %q on facet bucket", key)
		}
	}
}
