// spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rerrors "quwoquan_service/runtime/errors"
	locationgenerated "quwoquan_service/services/integration-service/generated/external_integration/location"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/provider"
)

func TestNominatimConformanceUsesExplicitQueryAndCoarseCenter(t *testing.T) {
	var rawQuery string
	upstream := httptest.NewTLSServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			rawQuery = r.URL.RawQuery
			if r.Method != http.MethodGet || r.URL.Path != "/search" ||
				r.URL.Query().Get("q") != "library" ||
				r.URL.Query().Get("format") != "jsonv2" ||
				r.URL.Query().Get("limit") != "3" {
				t.Fatalf("unexpected Nominatim request: %s %s", r.Method, r.URL.RequestURI())
			}
			if got := r.URL.Query().Get("viewbox"); got != "104.07,30.17,104.17,30.07" {
				t.Fatalf("coarse viewbox = %q", got)
			}
			if r.URL.Query().Has("lat") || r.URL.Query().Has("lon") {
				t.Fatal("precise center must not be sent as standalone coordinates")
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode([]map[string]any{{
				"place_id":     7,
				"osm_type":     "node",
				"osm_id":       11,
				"lat":          "30.120000",
				"lon":          "104.130000",
				"name":         "Library",
				"display_name": "Library, Chengdu",
			}})
		},
	))
	t.Cleanup(upstream.Close)
	client, err := provider.NewNominatimClient(
		upstream.URL,
		upstream.Client(),
		provider.RatePolicy{RequestsPerSecond: 10},
	)
	if err != nil {
		t.Fatalf("construct Nominatim client: %v", err)
	}
	items, err := client.Search(context.Background(), model.SearchRequestFact{
		Query: "library",
		Lat:   30.123456,
		Lng:   104.123456,
		Limit: 3,
	})
	if err != nil {
		t.Fatalf("search Nominatim: %v", err)
	}
	if strings.Contains(rawQuery, "30.123456") ||
		strings.Contains(rawQuery, "104.123456") {
		t.Fatalf("raw request leaked exact center: %s", rawQuery)
	}
	if len(items) != 1 || items[0].ID != "nominatim:node:11" ||
		items[0].Name != "Library" ||
		items[0].Latitude != 30.12 ||
		items[0].Longitude != 104.13 {
		t.Fatalf("canonical POI = %+v", items)
	}
}

func TestOSRMConformanceUsesLngLatWireAndCanonicalRoute(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet ||
				r.URL.Path != "/route/v1/driving/104.100000,30.200000;104.300000,30.400000" ||
				r.URL.Query().Get("overview") != "full" ||
				r.URL.Query().Get("geometries") != "polyline" ||
				r.URL.Query().Get("alternatives") != "false" {
				t.Fatalf("unexpected OSRM request: %s %s", r.Method, r.URL.RequestURI())
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(
				`{"code":"Ok","routes":[{"geometry":"encoded-polyline","distance":1234.4,"duration":321.6}]}`,
			))
		},
	))
	t.Cleanup(upstream.Close)
	client, err := provider.NewOSRMClient(
		upstream.URL,
		upstream.Client(),
		provider.RatePolicy{RequestsPerSecond: 10},
	)
	if err != nil {
		t.Fatalf("construct OSRM client: %v", err)
	}
	route, err := client.ReadRoute(context.Background(), model.RouteQuery{
		OriginLat:      30.2,
		OriginLng:      104.1,
		DestinationLat: 30.4,
		DestinationLng: 104.3,
		TravelMode:     model.TravelModeDriving,
	})
	if err != nil {
		t.Fatalf("read OSRM route: %v", err)
	}
	if !strings.HasPrefix(route.RouteRef, "osrm:sha256:") ||
		route.EncodedPolyline != "encoded-polyline" ||
		route.DistanceMeters != 1234 ||
		route.DurationSeconds != 322 ||
		route.OriginLat != 30.2 ||
		route.DestinationLng != 104.3 {
		t.Fatalf("canonical route = %+v", route)
	}
}

func TestNominatimFailureConformance(t *testing.T) {
	tests := []struct {
		name     string
		status   int
		body     string
		delay    time.Duration
		wantCode string
	}{
		{
			name:     "rate limited",
			status:   http.StatusTooManyRequests,
			body:     `{}`,
			wantCode: locationgenerated.ErrLocationProviderRateLimited.Error(),
		},
		{
			name:     "server unavailable",
			status:   http.StatusBadGateway,
			body:     `{}`,
			wantCode: locationgenerated.ErrLocationProviderUnavailable.Error(),
		},
		{
			name:     "invalid payload",
			status:   http.StatusOK,
			body:     `{`,
			wantCode: locationgenerated.ErrLocationProviderInvalidResponse.Error(),
		},
		{
			name:   "partial payload",
			status: http.StatusOK,
			body: `[{"place_id":1,"osm_type":"node","osm_id":2,` +
				`"lat":"invalid","lon":"104.1","name":"Bad"}]`,
			wantCode: locationgenerated.ErrLocationProviderInvalidResponse.Error(),
		},
		{
			name:     "timeout",
			status:   http.StatusOK,
			body:     `[]`,
			delay:    80 * time.Millisecond,
			wantCode: locationgenerated.ErrUpstreamTimeout.Error(),
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			upstream := httptest.NewTLSServer(http.HandlerFunc(
				func(w http.ResponseWriter, _ *http.Request) {
					time.Sleep(test.delay)
					w.WriteHeader(test.status)
					_, _ = w.Write([]byte(test.body))
				},
			))
			t.Cleanup(upstream.Close)
			httpClient := upstream.Client()
			httpClient.Timeout = 20 * time.Millisecond
			client, err := provider.NewNominatimClient(
				upstream.URL,
				httpClient,
				provider.RatePolicy{RequestsPerSecond: 10},
			)
			if err != nil {
				t.Fatalf("construct Nominatim client: %v", err)
			}
			_, err = client.Search(
				context.Background(),
				model.SearchRequestFact{Query: "cafe", Limit: 1},
			)
			assertAppErrorCode(t, err, test.wantCode)
		})
	}
}

func TestOSRMPartialPayloadFailsClosed(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(
		func(w http.ResponseWriter, _ *http.Request) {
			_, _ = w.Write([]byte(
				`{"code":"Ok","routes":[{"geometry":"encoded","distance":100}]}`,
			))
		},
	))
	t.Cleanup(upstream.Close)
	client, err := provider.NewOSRMClient(
		upstream.URL,
		upstream.Client(),
		provider.RatePolicy{RequestsPerSecond: 1},
	)
	if err != nil {
		t.Fatalf("construct OSRM client: %v", err)
	}
	_, err = client.ReadRoute(context.Background(), model.RouteQuery{
		OriginLat:      30.1,
		OriginLng:      104.1,
		DestinationLat: 30.2,
		DestinationLng: 104.2,
		TravelMode:     model.TravelModeDriving,
	})
	assertAppErrorCode(
		t,
		err,
		locationgenerated.ErrLocationProviderInvalidResponse.Error(),
	)
}

func TestPublicProviderLocalRateLimitFailsClosed(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(
		func(w http.ResponseWriter, _ *http.Request) {
			_, _ = w.Write([]byte(`[]`))
		},
	))
	t.Cleanup(upstream.Close)
	client, err := provider.NewNominatimClient(
		upstream.URL,
		upstream.Client(),
		provider.RatePolicy{RequestsPerSecond: 1},
	)
	if err != nil {
		t.Fatalf("construct Nominatim client: %v", err)
	}
	query := model.SearchRequestFact{Query: "cafe", Limit: 1}
	if _, err := client.Search(context.Background(), query); err != nil {
		t.Fatalf("first request failed: %v", err)
	}
	_, err = client.Search(context.Background(), query)
	assertAppErrorCode(
		t,
		err,
		locationgenerated.ErrLocationProviderRateLimited.Error(),
	)
}

func assertAppErrorCode(t *testing.T, err error, want string) {
	t.Helper()
	var appErr *rerrors.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("error type = %T, want *AppError: %v", err, err)
	}
	if appErr.Code.String() != want {
		t.Fatalf("error code = %s, want %s", appErr.Code.String(), want)
	}
}
