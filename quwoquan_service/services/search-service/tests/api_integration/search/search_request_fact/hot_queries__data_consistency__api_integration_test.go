// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-004
// readiness_case: list-hot-queries-api
package api_integration

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	feedbackstore "quwoquan_service/services/search-service/internal/search/search_feedback_fact/infrastructure/feedbackstore"
	httpadapter "quwoquan_service/services/search-service/internal/search/search_request_fact/adapters/inbound/http"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/application/queryheat"
	"quwoquan_service/services/search-service/internal/search/search_request_fact/infrastructure/queryheatstore"
)

func TestHotQueriesReturnsTermHeatRanking(t *testing.T) {
	cleanSearchCollections(t)
	ctx := context.Background()
	now := time.Now().UTC()
	queries := mongoDB.Collection("search_queries")
	for index, query := range []string{
		"成都旅行",
		"成都旅行",
		"成都旅行",
		"露营",
	} {
		if _, err := queries.InsertOne(ctx, bson.M{
			"searchRequestId": "hot-query-request-" + string(rune('a'+index)),
			"query":           query,
			"resultCount":     5,
			"createdAt":       now.Add(time.Duration(index) * time.Second),
		}); err != nil {
			t.Fatalf("insert query log %d: %v", index, err)
		}
	}

	store := queryheatstore.NewStore(
		mongoDB,
		feedbackstore.NewStore(mongoDB),
		queryheat.Config{Now: func() time.Time { return now.Add(time.Minute) }},
		slog.Default(),
	)
	written, err := store.Rebuild(ctx)
	if err != nil {
		t.Fatalf("rebuild term heat: %v", err)
	}
	if written != 2 {
		t.Fatalf("written heat rows=%d, want 2", written)
	}

	handler := httpadapter.NewHandler(store).Routes()
	request := httptest.NewRequest(
		http.MethodGet,
		"/search/hot-queries?limit=2",
		nil,
	)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var response struct {
		Items []struct {
			Query     string  `json:"query"`
			Relevance float64 `json:"relevance"`
		} `json:"items"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(response.Items) != 2 {
		t.Fatalf("hot query count=%d, want 2", len(response.Items))
	}
	if response.Items[0].Query != "成都旅行" {
		t.Fatalf("hottest query=%q, want 成都旅行", response.Items[0].Query)
	}
	if response.Items[0].Relevance < response.Items[1].Relevance {
		t.Fatalf("hot queries are not relevance-desc: %+v", response.Items)
	}
}

func TestHotQueriesRejectsMissingReaderAndInvalidLimit(t *testing.T) {
	missingReaderHandler := httpadapter.NewHandler(nil).Routes()

	missingReader := httptest.NewRecorder()
	missingReaderHandler.ServeHTTP(
		missingReader,
		httptest.NewRequest(http.MethodGet, "/search/hot-queries", nil),
	)
	if missingReader.Code != http.StatusServiceUnavailable {
		t.Fatalf(
			"missing reader status=%d body=%s",
			missingReader.Code,
			missingReader.Body.String(),
		)
	}

	store := queryheatstore.NewStore(
		mongoDB,
		feedbackstore.NewStore(mongoDB),
		queryheat.Config{},
		slog.Default(),
	)
	handler := httpadapter.NewHandler(store).Routes()
	invalidLimit := httptest.NewRecorder()
	handler.ServeHTTP(
		invalidLimit,
		httptest.NewRequest(
			http.MethodGet,
			"/search/hot-queries?limit=21",
			nil,
		),
	)
	if invalidLimit.Code != http.StatusBadRequest {
		t.Fatalf(
			"invalid limit status=%d body=%s",
			invalidLimit.Code,
			invalidLimit.Body.String(),
		)
	}
}
