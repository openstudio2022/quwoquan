package recommendation_test

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"testing"
	"time"

	transport "quwoquan_service/services/content-service/generated/content/post"
	recommendation "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func TestAuthorImpactReaderClientUsesGeneratedRoutesAndTypedResponses(t *testing.T) {
	client, err := recommendation.NewAuthorImpactReaderClient(
		"https://recommendation.internal",
		fixedServiceCredentials("Bearer feature-profile-token"),
	)
	if err != nil {
		t.Fatalf("new author impact reader: %v", err)
	}
	client.SetTransport(roundTripFunc(func(request *http.Request) (*http.Response, error) {
		if request.Method != transport.GetRecommendationAuthorImpactMethod {
			t.Fatalf("method=%s", request.Method)
		}
		if request.URL.EscapedPath() != "/internal/recommendation/authors/author%20one/impact" {
			t.Fatalf("path=%q", request.URL.EscapedPath())
		}
		if request.URL.Query().Get("limit") != "12" {
			t.Fatalf("query=%v", request.URL.Query())
		}
		if request.Header.Get("Authorization") != "Bearer feature-profile-token" {
			t.Fatalf("authorization=%q", request.Header.Get("Authorization"))
		}
		return jsonResponse(`{
			"authorId":"author one",
			"total":2,
			"items":[{
				"impactId":"impact-001",
				"helpType":"decision",
				"action":"content_depth",
				"intersectionDimension":"content",
				"tagRef":"Topic/旅行",
				"source":"behavior",
				"count":2,
				"updatedAt":"2026-08-02T12:00:00Z",
				"representativeContentId":"post-001"
			}]
		}`), nil
	}))

	summary, err := client.GetSummary(context.Background(), "author one", 12)
	if err != nil {
		t.Fatalf("get summary: %v", err)
	}
	if summary.Total != 2 || len(summary.Items) != 1 ||
		summary.Items[0].RepresentativeContentID != "post-001" {
		t.Fatalf("summary=%+v", summary)
	}
}

func TestAuthorImpactReaderClientPreservesOpaqueEvidenceCursor(t *testing.T) {
	client, err := recommendation.NewAuthorImpactReaderClient(
		"https://recommendation.internal",
		fixedServiceCredentials("Bearer feature-profile-token"),
	)
	if err != nil {
		t.Fatalf("new author impact reader: %v", err)
	}
	client.SetTransport(roundTripFunc(func(request *http.Request) (*http.Response, error) {
		if request.Method != transport.ListRecommendationAuthorImpactEvidenceMethod {
			t.Fatalf("method=%s", request.Method)
		}
		if request.URL.Query().Get("cursor") != "opaque-cursor" ||
			request.URL.Query().Get("limit") != "20" {
			t.Fatalf("query=%v", request.URL.Query())
		}
		return jsonResponse(`{
			"impactId":"impact-001",
			"totalCount":1,
			"items":[{
				"evidenceId":"evidence-001",
				"impactId":"impact-001",
				"contentId":"post-001",
				"contentType":"post",
				"helpType":"decision",
				"action":"content_depth",
				"intersectionDimension":"content",
				"occurredAt":"2026-08-02T12:00:00Z"
			}],
			"nextCursor":"next-opaque-cursor",
			"hasMore":true
		}`), nil
	}))

	items, nextCursor, hasMore, total, err := client.ListPageWithTotal(
		context.Background(),
		"author-001",
		"impact-001",
		"opaque-cursor",
		20,
	)
	if err != nil {
		t.Fatalf("list evidence: %v", err)
	}
	if len(items) != 1 || nextCursor != "next-opaque-cursor" || !hasMore || total != 1 {
		t.Fatalf("items=%+v cursor=%q hasMore=%v total=%d", items, nextCursor, hasMore, total)
	}
	if !items[0].OccurredAt.Equal(time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC)) {
		t.Fatalf("occurredAt=%v", items[0].OccurredAt)
	}
}

func jsonResponse(body string) *http.Response {
	return &http.Response{
		StatusCode: http.StatusOK,
		Header:     http.Header{"Content-Type": []string{"application/json"}},
		Body:       io.NopCloser(bytes.NewBufferString(body)),
	}
}
