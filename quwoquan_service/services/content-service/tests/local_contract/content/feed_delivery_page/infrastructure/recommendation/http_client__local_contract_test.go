package recommendation_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	recommendation "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/recommendation"
)

type staticCredentials struct{}

func (staticCredentials) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer generated-service-token", nil
}

func TestHTTPClientCreateUsesGeneratedBodyAndRetriesTransientStatus(t *testing.T) {
	var attempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != transport.CreateRankedRecommendationWindowPath ||
			request.Method != transport.CreateRankedRecommendationWindowMethod {
			t.Fatalf("request=%s %s", request.Method, request.URL.Path)
		}
		if request.Header.Get("Authorization") != "Bearer generated-service-token" ||
			request.Header.Get("Idempotency-Key") != "feed-request-1" {
			t.Fatalf("headers=%v", request.Header)
		}
		var body map[string]any
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
			t.Fatalf("decode body: %v", err)
		}
		if _, leaked := body["idempotencyKey"]; leaked {
			t.Fatalf("injected idempotency key leaked into JSON body: %v", body)
		}
		if body["subjectId"] != "subject-1" || body["scenario"] != "content_feed" {
			t.Fatalf("body=%v", body)
		}
		if attempts.Add(1) == 1 {
			writer.WriteHeader(http.StatusServiceUnavailable)
			return
		}
		writeRankedPage(t, writer, "window-1", 1)
	}))
	defer server.Close()

	client, err := recommendation.NewHTTPClient(server.URL, staticCredentials{})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	page, err := client.Create(context.Background(), transport.CreateRankedRecommendationWindowCommand{
		IdempotencyKey: "feed-request-1",
		SubjectId:      "subject-1",
		Scenario:       "content_feed",
		Limit:          20,
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}
	if attempts.Load() != 2 || page.WindowId != "window-1" || len(page.Items) != 1 ||
		len(page.ObjectCards) != 1 || page.ObjectCards[0].ObjectId != "homepage-dali" {
		t.Fatalf("attempts=%d page=%+v", attempts.Load(), page)
	}
}

func TestHTTPClientGetPageBindsGeneratedPathAndQuery(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/internal/recommendation/ranked-pages/window%20identity" &&
			request.URL.EscapedPath() != "/internal/recommendation/ranked-pages/window%20identity" {
			t.Fatalf("path=%q escaped=%q", request.URL.Path, request.URL.EscapedPath())
		}
		if request.URL.Query().Get("subjectId") != "subject identity" ||
			request.URL.Query().Get("fromOrdinal") != "20" ||
			request.URL.Query().Get("limit") != "10" {
			t.Fatalf("query=%v", request.URL.Query())
		}
		writeRankedPage(t, writer, "window identity", 20)
	}))
	defer server.Close()

	client, err := recommendation.NewHTTPClient(server.URL, staticCredentials{})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	fromOrdinal := 20
	limit := 10
	page, err := client.GetPage(context.Background(), transport.GetRankedRecommendationPageQuery{
		SubjectId:   "subject identity",
		WindowId:    "window identity",
		FromOrdinal: &fromOrdinal,
		Limit:       &limit,
	})
	if err != nil {
		t.Fatalf("get page: %v", err)
	}
	if page.Items[0].Ordinal != 20 {
		t.Fatalf("page=%+v", page)
	}
}

func TestHTTPClientRejectsMalformedRankedObjectCard(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(writer).Encode(rankedPageWire(
			"window-invalid-card",
			0,
			[]map[string]any{{
				"objectKind": "entity_homepage",
				"objectId":   "homepage-dali",
				"title":      "大理古城",
				"tagRefs":    []string{"travel.photography.landmark"},
				"reasonKey":  "",
				"recallPath": "candidate_index",
			}},
		)); err != nil {
			t.Fatalf("encode response: %v", err)
		}
	}))
	defer server.Close()

	client, err := recommendation.NewHTTPClient(server.URL, staticCredentials{})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	if _, err := client.Create(context.Background(), transport.CreateRankedRecommendationWindowCommand{
		IdempotencyKey: "feed-request-invalid-card",
		SubjectId:      "subject-invalid-card",
		Scenario:       "content_feed",
		Limit:          20,
	}); err == nil {
		t.Fatal("malformed ranked object card must fail closed")
	}
}

func writeRankedPage(t *testing.T, writer http.ResponseWriter, windowID string, ordinal int) {
	t.Helper()
	writer.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(writer).Encode(rankedPageWire(
		windowID,
		ordinal,
		[]map[string]any{{
			"objectKind": "entity_homepage",
			"objectId":   "homepage-dali",
			"title":      "大理古城",
			"tagRefs":    []string{"travel.photography.landmark"},
			"reasonKey":  "shared_interest",
			"recallPath": "candidate_index",
		}},
	)); err != nil {
		t.Fatalf("encode response: %v", err)
	}
}

func rankedPageWire(
	windowID string,
	ordinal int,
	objectCards []map[string]any,
) map[string]any {
	return map[string]any{
		"windowId":              windowID,
		"scenario":              "content_feed",
		"modelBucket":           "rule",
		"policyDigest":          "sha256:" + strings.Repeat("c", 64),
		"rankingSnapshotDigest": strings.Repeat("a", 64),
		"featureSnapshotAt":     time.Now().UTC().Add(-time.Second),
		"userFeatureSnapshot":   map[string]any{},
		"items": []map[string]any{{
			"ordinal":               ordinal,
			"contentId":             "post-1",
			"score":                 1.0,
			"featureSnapshotDigest": strings.Repeat("b", 64),
			"itemFeatureSnapshot":   map[string]any{"qualityScore": 1.0},
		}},
		"objectCards": objectCards,
		"expiresAt":   time.Now().UTC().Add(time.Minute),
	}
}
