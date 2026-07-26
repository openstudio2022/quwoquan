package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/providerbinding"
	"quwoquan_service/services/integration-service/internal/external_integration/location/application"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
)

func TestLocationSelectedAdapterUsesBoundHTTPSProtocolAndNormalizesResult(t *testing.T) {
	calls := 0
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.Method != http.MethodGet || r.URL.Path != "/place/v2/search" {
			t.Fatalf("request = %s %s, want GET /place/v2/search", r.Method, r.URL.Path)
		}
		if r.URL.Query().Get("ak") != "test-ak" ||
			r.URL.Query().Get("query") != "cafe" {
			t.Fatalf("unexpected bound request query: %s", r.URL.RawQuery)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"status": 0,
			"results": []map[string]any{{
				"uid":       "poi-1",
				"name":      "Cafe",
				"address":   "Road 1",
				"city_code": 510100,
				"location":  map[string]any{"lat": 30.1, "lng": 104.2},
			}},
		})
	}))
	t.Cleanup(upstream.Close)

	locationProvider, err := provider.NewLocationProvider(
		providerbinding.ResolvedLocationBinding{
			AdapterID: provider.LocationAdapterBaiduID,
			Endpoints: map[string]string{
				"base": upstream.URL,
			},
			Secrets: map[string]string{
				"INTEGRATION_LOCATION_BAIDU_AK": "test-ak",
			},
			Timeout: time.Second,
		},
		upstream.Client(),
	)
	if err != nil {
		t.Fatalf("construct selected location adapter: %v", err)
	}
	service, err := application.NewService(locationProvider)
	if err != nil {
		t.Fatalf("construct location application service: %v", err)
	}

	items, err := service.Search(context.Background(), model.SearchQuery{
		Query: "cafe",
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("search through selected adapter: %v", err)
	}
	if calls != 1 {
		t.Fatalf("selected adapter calls = %d, want 1", calls)
	}
	if len(items) != 1 || items[0].ID != "poi-1" ||
		items[0].Latitude != 30.1 || items[0].Longitude != 104.2 {
		t.Fatalf("normalized location result = %+v", items)
	}
}
