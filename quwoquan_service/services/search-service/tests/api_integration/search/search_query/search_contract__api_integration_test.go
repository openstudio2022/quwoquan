package api_integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	httpadapter "quwoquan_service/services/search-service/internal/search/search_query/adapters/inbound/http"
	"quwoquan_service/services/search-service/internal/search/search_query/application"
	"quwoquan_service/services/search-service/internal/search/search_query/infrastructure/searchbackend"
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
						"payload": map[string]any{
							"coverUrl":        "https://cdn.example/post_es.webp",
							"contentIdentity": "work",
							"likeCount":       "12",
						},
					},
				}},
			},
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(payload)
	}))
}

func newServer(
	t *testing.T,
	cfg searchbackend.ESConfig,
	testBackend rtsearch.RecallBackend,
) http.Handler {
	t.Helper()
	backend := testBackend
	if cfg.Enabled {
		built, err := searchbackend.Build(cfg)
		if err != nil {
			t.Fatalf("Build err=%v", err)
		}
		backend = built.Backend
	}
	if backend == nil {
		t.Fatal("test server requires one explicit recall backend")
	}
	svc := application.NewSearchService(backend)
	// nil TermHeatProvider => base ranking + empty relatedTerms; the AB bucket is
	// still assigned so the envelope carries experimentBucket.
	experiments, err := application.NewExperiments(application.ExperimentConfig{
		Enabled: true,
		Buckets: []application.ExperimentBucket{{
			Name:      application.BucketControl,
			WeightPct: 100,
		}},
	})
	if err != nil {
		t.Fatalf("NewExperiments() error = %v", err)
	}
	decorator := application.NewRankingDecorator(nil, experiments, 0, nil)
	return httpadapter.NewHandler(svc, decorator, nil).Routes()
}

func postSearch(t *testing.T, handler http.Handler, body string) (*httptest.ResponseRecorder, map[string]any) {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/search", bytes.NewBufferString(body))
	req.Header.Set("X-Session-Id", "search-api-integration-session")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	var parsed map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &parsed)
	return rec, parsed
}

func TestSearchEndpointRejectsAnonymousRequestWithoutStableSession(t *testing.T) {
	native := rtsearch.NewSliceBackend([]rtsearch.Document{{
		ObjectType: rtsearch.ObjectTypeContentPost,
		ObjectID:   "post_native",
		Title:      "大理古城漫步",
		Visibility: "public",
	}})
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, native)
	request := httptest.NewRequest(http.MethodPost, "/search", bytes.NewBufferString(`{"query":"大理"}`))
	request.Header.Set("X-Request-Id", "search-request-without-session")
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var parsed map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &parsed); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	if got := toString(parsed["code"]); got != "SEARCH.USER.invalid_argument" {
		t.Fatalf("error code=%q body=%s", got, response.Body.String())
	}
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
	if _, exists := parsed["rankingVersion"]; exists {
		t.Fatalf("retired rankingVersion returned: %#v", parsed["rankingVersion"])
	}
	if strings.TrimSpace(toString(parsed["requestId"])) == "" {
		t.Fatalf("missing requestId")
	}
	hits, _ := parsed["hits"].([]any)
	hit, _ := hits[0].(map[string]any)
	content, _ := hit["content"].(map[string]any)
	if toString(content["coverUrl"]) != "https://cdn.example/post_es.webp" {
		t.Fatalf("ES typed content projection was not round-tripped: %#v", hit)
	}
	if _, exists := hit["payload"]; exists {
		t.Fatalf("retired untyped payload returned: %#v", hit)
	}
}

func TestSearchEndpointWithDeterministicContractBackend(t *testing.T) {
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
		t.Fatalf("expected contract backend hits, got: %s", rec.Body.String())
	}
}

func TestSearchEndpointRecallsUserProfileObject(t *testing.T) {
	native := rtsearch.NewSliceBackend([]rtsearch.Document{{
		ObjectType:   rtsearch.ObjectTypeUserProfile,
		ObjectID:     "user_photographer",
		Title:        "林摄影",
		Summary:      "旅行与街头摄影创作者",
		Visibility:   "public",
		SourceDomain: "user",
	}})
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, native)

	rec, parsed := postSearch(t, handler, `{"query":"摄影","objectTypes":["user"]}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	hits, _ := parsed["hits"].([]any)
	if len(hits) != 1 {
		t.Fatalf("expected one user hit, got %d: %s", len(hits), rec.Body.String())
	}
	hit, _ := hits[0].(map[string]any)
	if toString(hit["target"]) != string(rtsearch.TargetUser) ||
		toString(hit["objectId"]) != "user_photographer" {
		t.Fatalf("unexpected user hit: %#v", hit)
	}
}

func TestSearchEndpointReadsLocationPlaceByCanonicalID(t *testing.T) {
	native := rtsearch.NewSliceBackend([]rtsearch.Document{{
		ObjectType: rtsearch.ObjectTypeLocation,
		ObjectID:   "place_broken_bridge_lane",
		Title:      "断桥小巷",
		Visibility: "public",
		Fields: map[string]string{
			"address": "杭州 · 西湖区",
		},
	}})
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, native)

	rec, parsed := postSearch(
		t,
		handler,
		`{"query":"place_broken_bridge_lane","ids":["place_broken_bridge_lane"],"objectTypes":["location"]}`,
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", rec.Code, rec.Body.String())
	}
	hits, _ := parsed["hits"].([]any)
	if len(hits) != 1 {
		t.Fatalf("expected one location hit, got %d: %s", len(hits), rec.Body.String())
	}
	hit, _ := hits[0].(map[string]any)
	if toString(hit["target"]) != string(rtsearch.TargetLocation) ||
		toString(hit["objectId"]) != "place_broken_bridge_lane" {
		t.Fatalf("unexpected exact location hit: %#v", hit)
	}
}

func TestSearchEndpointESOutageReturns503(t *testing.T) {
	// The single production backend honestly surfaces unavailability instead of
	// masking the outage with a second source of truth.
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

func TestSearchEndpointAppliesTagFilterWithPositiveAndNegativeCases(t *testing.T) {
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, rtsearch.NewSliceBackend([]rtsearch.Document{
		{
			ObjectType:  rtsearch.ObjectTypeContentPost,
			ObjectID:    "post_camping",
			Title:       "露营攻略",
			ContentType: "article",
			Visibility:  "public",
			Tags:        []string{"Topic/旅行/露营"},
		},
		{
			ObjectType:  rtsearch.ObjectTypeContentPost,
			ObjectID:    "post_photography",
			Title:       "摄影攻略",
			ContentType: "article",
			Visibility:  "public",
			Tags:        []string{"Topic/旅行/摄影"},
		},
	}))

	positive, parsed := postSearch(
		t,
		handler,
		`{"query":"攻略","objectTypes":["article"],"filters":{"tags":["Topic/旅行/露营"]}}`,
	)
	if positive.Code != http.StatusOK || hitCount(parsed) != 1 {
		t.Fatalf("tag positive case must return exactly one hit, status=%d body=%s", positive.Code, positive.Body.String())
	}
	hits, _ := parsed["hits"].([]any)
	hit, _ := hits[0].(map[string]any)
	if toString(hit["objectId"]) != "post_camping" {
		t.Fatalf("tag positive case returned unexpected hit: %#v", hit)
	}

	negative, negativeParsed := postSearch(
		t,
		handler,
		`{"query":"攻略","objectTypes":["article"],"filters":{"tags":["Topic/旅行/徒步"]}}`,
	)
	if negative.Code != http.StatusOK || hitCount(negativeParsed) != 0 {
		t.Fatalf("tag negative case must return no hits, status=%d body=%s", negative.Code, negative.Body.String())
	}
}

func TestSearchEndpointCarriesCanonicalAttribution(t *testing.T) {
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

func TestSearchEndpointRejectsLocalOnlyOrUnknownTarget(t *testing.T) {
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, rtsearch.NewSliceBackend(nil))
	for _, target := range []string{"chat", "unknown"} {
		rec, _ := postSearch(
			t,
			handler,
			`{"query":"旅行","objectTypes":["`+target+`"]}`,
		)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("target %q must be rejected with 400, got %d body=%s", target, rec.Code, rec.Body.String())
		}
	}
}

func TestSearchEndpointAcceptsIndexedCircleTargets(t *testing.T) {
	handler := newServer(t, searchbackend.ESConfig{Enabled: false}, rtsearch.NewSliceBackend([]rtsearch.Document{
		{
			ObjectType: rtsearch.ObjectTypeCircle,
			ObjectID:   "circle_travel",
			Title:      "旅行圈",
			Visibility: "public",
		},
		{
			ObjectType: rtsearch.ObjectTypeCircleGroup,
			ObjectID:   "group_travel",
			Title:      "旅行讨论",
			Visibility: "public",
		},
	}))

	for _, target := range []string{"circle", "group"} {
		rec, _ := postSearch(
			t,
			handler,
			`{"query":"旅行","objectTypes":["`+target+`"]}`,
		)
		if rec.Code != http.StatusOK {
			t.Fatalf("target %q must be searchable when indexed, got %d body=%s", target, rec.Code, rec.Body.String())
		}
	}
}

func toString(v any) string {
	s, _ := v.(string)
	return s
}
