package api_integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	httpadapter "quwoquan_service/services/search-service/internal/adapters/http"
	"quwoquan_service/services/search-service/internal/application"
	"quwoquan_service/services/search-service/internal/infrastructure/searchbackend"
)

// fakeES returns a single content.post article hit for any _search request.
func fakeES(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasSuffix(r.URL.Path, "/_search") {
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{}`))
			return
		}
		payload := map[string]any{
			"hits": map[string]any{
				"hits": []map[string]any{{
					"_id":    "content.post:post_es",
					"_score": 3.2,
					"_source": map[string]any{
						"objectType": rtsearch.ObjectTypeContentPost,
						"objectId":   "post_es",
						"title":      "大理苍山徒步",
						"summary":    "ES 召回结果",
						"target":     string(rtsearch.TargetArticle),
						"visibility": "public",
					},
				}},
			},
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(payload)
	}))
}

func newServer(t *testing.T, cfg searchbackend.ESConfig, fallback rtsearch.RecallBackend) http.Handler {
	t.Helper()
	built, err := searchbackend.Build(cfg, fallback)
	if err != nil {
		t.Fatalf("Build err=%v", err)
	}
	svc := application.NewSearchService(built.Backend, nil)
	// nil TermHeatProvider => base ranking + empty relatedTerms; the AB bucket is
	// still assigned so the envelope carries experimentBucket.
	decorator := application.NewRankingDecorator(nil, application.NewExperiments(application.ExperimentConfig{}), 0, nil)
	return httpadapter.NewHandler(svc, decorator, nil).Routes()
}

func postSearch(t *testing.T, handler http.Handler, body string) (*httptest.ResponseRecorder, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/search", bytes.NewBufferString(body))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	var parsed map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &parsed)
	return rec, parsed
}

func hitCount(parsed map[string]any) int {
	hits, _ := parsed["hits"].([]any)
	return len(hits)
}

func TestSearchEndpointESBackedHits(t *testing.T) {
	srv := fakeES(t)
	defer srv.Close()
	handler := newServer(t, searchbackend.ESConfig{Enabled: true, Endpoints: []string{srv.URL}}, nil)

	rec, parsed := postSearch(t, handler, `{"query":"大理","objectTypes":["article"]}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if hitCount(parsed) == 0 {
		t.Fatalf("expected ES-backed hits, got: %s", rec.Body.String())
	}
	if parsed["rankingVersion"] != application.RankingVersion {
		t.Fatalf("missing rankingVersion: %#v", parsed["rankingVersion"])
	}
	if strings.TrimSpace(toString(parsed["requestId"])) == "" {
		t.Fatalf("missing requestId")
	}
}

func TestSearchEndpointNativeFallbackWhenESDisabled(t *testing.T) {
	native := rtsearch.NewSliceBackend([]rtsearch.Document{{
		ObjectType:  rtsearch.ObjectTypeContentPost,
		ObjectID:    "post_native",
		Title:       "大理古城漫步",
		ContentType: "article",
		Visibility:  "public",
	}})
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, native)

	rec, parsed := postSearch(t, handler, `{"query":"大理","objectTypes":["article"]}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if hitCount(parsed) == 0 {
		t.Fatalf("expected native fallback hits, got: %s", rec.Body.String())
	}
}

func TestSearchEndpointESDownDegradesToNativeFallback(t *testing.T) {
	// Production topology: ES primary + native fallback. ES is unroutable, so the
	// FallbackBackend must transparently serve native results (no 5xx, no break).
	native := rtsearch.NewSliceBackend([]rtsearch.Document{{
		ObjectType:  rtsearch.ObjectTypeContentPost,
		ObjectID:    "post_native",
		Title:       "大理古城漫步",
		ContentType: "article",
		Visibility:  "public",
	}})
	handler := newServer(t, searchbackend.ESConfig{Enabled: true, Endpoints: []string{"http://127.0.0.1:1"}}, native)

	rec, parsed := postSearch(t, handler, `{"query":"大理","objectTypes":["article"]}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("ES outage with fallback must degrade to 200, got status=%d body=%s", rec.Code, rec.Body.String())
	}
	if hitCount(parsed) == 0 {
		t.Fatalf("expected native fallback hits on ES outage, got: %s", rec.Body.String())
	}
}

func TestSearchEndpointPureESOutageReturns503(t *testing.T) {
	// Pure ES with no fallback honestly surfaces unavailability (no silent empty
	// success masking an outage).
	handler := newServer(t, searchbackend.ESConfig{Enabled: true, Endpoints: []string{"http://127.0.0.1:1"}}, nil)

	rec, _ := postSearch(t, handler, `{"query":"大理","objectTypes":["article"]}`)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("pure ES outage must surface 503, got status=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestSearchEndpointNearFilterPushesDownToRadius(t *testing.T) {
	// Two entity homepages match the term "营地"; only the one inside the 5km
	// radius around the pin survives the near filter, proving the wire near block
	// flows handler -> application -> RetrieveFilters.Near -> shared ranker.
	native := rtsearch.NewSliceBackend([]rtsearch.Document{
		{
			ObjectType: rtsearch.ObjectTypeEntityHomepage, ObjectID: "hp_close",
			Title: "西湖营地", Visibility: "public",
			Geo:    &rtsearch.GeoPoint{Lat: 30.2431, Lng: 120.1505},
			Fields: map[string]string{"placeName": "杭州"},
		},
		{
			ObjectType: rtsearch.ObjectTypeEntityHomepage, ObjectID: "hp_far",
			Title: "千岛湖营地", Visibility: "public",
			Geo:    &rtsearch.GeoPoint{Lat: 29.6050, Lng: 119.0300},
			Fields: map[string]string{"placeName": "淳安"},
		},
	})
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, native)

	rec, parsed := postSearch(t, handler,
		`{"query":"营地","objectTypes":["entity"],"filters":{"near":{"lat":30.25,"lng":120.15,"radiusKm":5}}}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	hits, _ := parsed["hits"].([]any)
	if len(hits) != 1 {
		t.Fatalf("near filter must keep only the nearby homepage, got %d: %s", len(hits), rec.Body.String())
	}
	hit, _ := hits[0].(map[string]any)
	if toString(hit["objectId"]) != "hp_close" {
		t.Fatalf("expected hp_close, got %v", hit["objectId"])
	}
	// The location dimension surfaces on the wire hit (distance + place name).
	if d, ok := hit["distanceKm"].(float64); !ok || d <= 0 || d > 5 {
		t.Fatalf("hit must carry distanceKm in (0,5], got %v", hit["distanceKm"])
	}
	if toString(hit["placeName"]) != "杭州" {
		t.Fatalf("hit placeName=%v want 杭州", hit["placeName"])
	}
}

func TestSearchEndpointCarriesRankingEnvelope(t *testing.T) {
	// The commercial envelope must surface experimentBucket + per-hit ranking
	// transparency (rankReasons/rankPosition) so AB attribution + explanation
	// work end to end, even without the Mongo heat read model wired.
	native := rtsearch.NewSliceBackend([]rtsearch.Document{{
		ObjectType:  rtsearch.ObjectTypeContentPost,
		ObjectID:    "post_native",
		Title:       "大理古城漫步",
		ContentType: "article",
		Visibility:  "public",
	}})
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, native)

	rec, parsed := postSearch(t, handler, `{"query":"大理","objectTypes":["article"]}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	if strings.TrimSpace(toString(parsed["experimentBucket"])) == "" {
		t.Fatalf("missing experimentBucket: %s", rec.Body.String())
	}
	hits, _ := parsed["hits"].([]any)
	if len(hits) == 0 {
		t.Fatalf("expected hits: %s", rec.Body.String())
	}
	hit, _ := hits[0].(map[string]any)
	if pos, ok := hit["rankPosition"].(float64); !ok || pos != 1 {
		t.Fatalf("hit must carry rankPosition=1, got %v", hit["rankPosition"])
	}
	reasons, ok := hit["rankReasons"].([]any)
	if !ok || len(reasons) == 0 {
		t.Fatalf("hit must carry non-empty rankReasons, got %v", hit["rankReasons"])
	}
}

func TestSearchEndpointRejectsEmptyQuery(t *testing.T) {
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, rtsearch.NewSliceBackend(nil))
	rec, _ := postSearch(t, handler, `{"query":"   "}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("empty query must be 400, got %d", rec.Code)
	}
}

func TestFeedbackEndpointAcceptsEvent(t *testing.T) {
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, rtsearch.NewSliceBackend(nil))
	req := httptest.NewRequest(http.MethodPost, "/v1/search/feedback",
		bytes.NewBufferString(`{"searchRequestId":"req_1","eventType":"click","objectId":"post_es","rankPosition":2}`))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("feedback must be 202, got %d body=%s", rec.Code, rec.Body.String())
	}
}

func TestFeedbackEndpointRejectsMissingFields(t *testing.T) {
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, rtsearch.NewSliceBackend(nil))
	req := httptest.NewRequest(http.MethodPost, "/v1/search/feedback", bytes.NewBufferString(`{"eventType":"click"}`))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("missing searchRequestId must be 400, got %d", rec.Code)
	}
}

func toString(v any) string {
	s, _ := v.(string)
	return s
}
