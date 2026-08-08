// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/location/application"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/provider"
	"quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/providerbinding"
)

func TestLocationSelectedAdapterUsesBoundHTTPSProtocolAndNormalizesResult(t *testing.T) {
	calls := 0
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/place/v2/search":
			if r.Method != http.MethodGet || r.URL.Query().Get("ak") != "test-ak" ||
				r.URL.Query().Get("query") != "cafe" {
				t.Fatalf("unexpected search request: %s %s", r.Method, r.URL.RawQuery)
			}
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
		case "/reverse_geocoding/v3/":
			if r.Method != http.MethodGet || r.URL.Query().Get("ak") != "test-ak" ||
				r.URL.Query().Get("location") != "30.100000,104.200000" {
				t.Fatalf("unexpected nearby request: %s %s", r.Method, r.URL.RawQuery)
			}
			_ = json.NewEncoder(w).Encode(map[string]any{
				"status": 0,
				"result": map[string]any{"pois": []map[string]any{{
					"uid":      "poi-nearby-1",
					"name":     "Nearby Cafe",
					"addr":     "Road 2",
					"distance": "25",
					"point":    map[string]any{"y": "30.1", "x": "104.2"},
				}}},
			})
		default:
			t.Fatalf("unexpected selected-adapter path: %s", r.URL.Path)
		}
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

	items, err := service.Search(context.Background(), model.SearchRequestFact{
		Query: "cafe",
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("search through selected adapter: %v", err)
	}
	if len(items) != 1 || items[0].ID != "poi-1" ||
		items[0].Latitude != 30.1 || items[0].Longitude != 104.2 {
		t.Fatalf("normalized location result = %+v", items)
	}
	nearby, err := service.Nearby(context.Background(), model.NearbyQuery{
		Lat:          30.1,
		Lng:          104.2,
		RadiusMeters: 1000,
		Limit:        10,
	})
	if err != nil {
		t.Fatalf("nearby through selected adapter: %v", err)
	}
	if calls != 2 {
		t.Fatalf("selected adapter calls = %d, want 2", calls)
	}
	if len(nearby) != 1 || nearby[0].ID != "poi-nearby-1" ||
		nearby[0].DistanceMeters != 25 {
		t.Fatalf("normalized nearby result = %+v", nearby)
	}
}
