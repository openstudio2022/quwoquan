// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
// readiness_case: get-nearby-locations-local
// readiness_case: search-locations-local
// readiness_case: read-location-route-local
package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	locationgenerated "quwoquan_service/services/integration-service/generated/external_integration/location"
	. "quwoquan_service/services/integration-service/internal/external_integration/location/adapters/inbound/http"
	locationapplication "quwoquan_service/services/integration-service/internal/external_integration/location/application"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
)

type fakeProviderClient struct {
	nearbyFn func(model.NearbyQuery) ([]model.POI, error)
	searchFn func(model.SearchRequestFact) ([]model.POI, error)
	routeFn  func(model.RouteQuery) (model.Route, error)
}

func (f *fakeProviderClient) Nearby(_ context.Context, q model.NearbyQuery) ([]model.POI, error) {
	return f.nearbyFn(q)
}

func (f *fakeProviderClient) Search(_ context.Context, q model.SearchRequestFact) ([]model.POI, error) {
	return f.searchFn(q)
}

func (f *fakeProviderClient) ReadRoute(
	_ context.Context,
	q model.RouteQuery,
) (model.Route, error) {
	return f.routeFn(q)
}

func newLocationService(t *testing.T, provider *fakeProviderClient) *locationapplication.Service {
	t.Helper()
	service, err := locationapplication.NewService(provider)
	if err != nil {
		t.Fatalf("construct location service: %v", err)
	}
	return service
}

func TestNearbyUsesDefaultCenterWhenLatLngMissing(t *testing.T) {
	var got model.NearbyQuery
	svc := newLocationService(t, &fakeProviderClient{
		nearbyFn: func(q model.NearbyQuery) ([]model.POI, error) {
			got = q
			return []model.POI{{Name: "x", Latitude: q.Lat, Longitude: q.Lng}}, nil
		},
		searchFn: func(model.SearchRequestFact) ([]model.POI, error) {
			return nil, nil
		},
	})

	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, locationgenerated.NearbyPath+"?"+locationgenerated.QueryParamLimit+"=1", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d, want=200 body=%s", rr.Code, rr.Body.String())
	}
	if got.Lat != 30.1 || got.Lng != 104.2 {
		t.Fatalf("lat/lng not fallback, got=(%f,%f)", got.Lat, got.Lng)
	}
}

func TestSearchUsesTypedProviderAndReturnsCanonicalPOI(t *testing.T) {
	var got model.SearchRequestFact
	svc := newLocationService(t, &fakeProviderClient{
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) { return nil, nil },
		searchFn: func(query model.SearchRequestFact) ([]model.POI, error) {
			got = query
			return []model.POI{{
				ID:        "poi-search-local-001",
				Name:      "Local Cafe",
				Latitude:  30.1,
				Longitude: 104.2,
			}}, nil
		},
	})
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	request := httptest.NewRequest(
		http.MethodGet,
		locationgenerated.SearchPath+"?"+locationgenerated.QueryParamQ+"=cafe&"+
			locationgenerated.QueryParamLimit+"=1",
		nil,
	)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("status=%d, want=200 body=%s", recorder.Code, recorder.Body.String())
	}
	if got.Query != "cafe" || got.Limit != 1 {
		t.Fatalf("search query was not bound canonically: %+v", got)
	}
	var response struct {
		Items []model.POI `json:"items"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode search response: %v", err)
	}
	if len(response.Items) != 1 || response.Items[0].ID != "poi-search-local-001" {
		t.Fatalf("unexpected search response: %+v", response.Items)
	}
}

func TestSearchEmptyQueryReturnsBadRequest(t *testing.T) {
	svc := newLocationService(t, &fakeProviderClient{
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) { return nil, nil },
		searchFn: func(model.SearchRequestFact) ([]model.POI, error) { return nil, nil },
	})
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, locationgenerated.SearchPath, nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d, want=400 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] != locationgenerated.ErrInvalidArgument.Error() {
		t.Fatalf("code=%v, want %s", body["code"], locationgenerated.ErrInvalidArgument.Error())
	}
}

func TestReadRouteBindsCanonicalCoordinatesAndReturnsCanonicalRoute(
	t *testing.T,
) {
	fake := &fakeProviderClient{
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return nil, nil
		},
		searchFn: func(model.SearchRequestFact) ([]model.POI, error) {
			return nil, nil
		},
	}
	var got model.RouteQuery
	fake.routeFn = func(query model.RouteQuery) (model.Route, error) {
		got = query
		return model.Route{
			RouteRef:        "route-1",
			OriginLat:       query.OriginLat,
			OriginLng:       query.OriginLng,
			DestinationLat:  query.DestinationLat,
			DestinationLng:  query.DestinationLng,
			EncodedPolyline: "encoded",
			DurationSeconds: 120,
			DistanceMeters:  900,
			TravelMode:      query.TravelMode,
		}, nil
	}
	service, err := locationapplication.NewServiceWithProviders(
		fake,
		fake,
		fake,
	)
	if err != nil {
		t.Fatalf("construct location service: %v", err)
	}
	handler := NewHandler(
		service,
		3000,
		20,
		20,
		30.1,
		104.2,
	).Routes()
	request := httptest.NewRequest(
		http.MethodGet,
		locationgenerated.RoutePath+
			"?originLat=30.100001&originLng=104.200001"+
			"&destinationLat=30.200001&destinationLng=104.300001"+
			"&travelMode=walking",
		nil,
	)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf(
			"status=%d, want=200 body=%s",
			recorder.Code,
			recorder.Body.String(),
		)
	}
	if got.OriginLat != 30.100001 || got.OriginLng != 104.200001 ||
		got.DestinationLat != 30.200001 ||
		got.DestinationLng != 104.300001 ||
		got.TravelMode != model.TravelModeWalking {
		t.Fatalf("route query was not bound canonically: %+v", got)
	}
	var response map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode route response: %v", err)
	}
	if response[locationgenerated.FieldKeyRouteRef] != "route-1" ||
		response[locationgenerated.FieldKeyEncodedPolyline] != "encoded" {
		t.Fatalf("unexpected route response: %+v", response)
	}
}

func TestNearbyProviderFailureReturnsStructuredUnavailableError(t *testing.T) {
	fail := &fakeProviderClient{
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return nil, locationgenerated.AppErrorFromLocationProviderUnavailable(
				"location provider request failed",
			)
		},
		searchFn: func(model.SearchRequestFact) ([]model.POI, error) {
			return nil, nil
		},
	}
	svc := newLocationService(t, fail)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, locationgenerated.NearbyPath, nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d, want=503 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] != locationgenerated.ErrLocationProviderUnavailable.Error() {
		t.Fatalf("code=%v, want %s", body["code"], locationgenerated.ErrLocationProviderUnavailable.Error())
	}
}

func TestNearbyTimeoutReturns504WithUpstreamTimeoutCode(t *testing.T) {
	timeoutClient := &fakeProviderClient{
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return nil, locationgenerated.AppErrorFromUpstreamTimeout(
				"location provider request timed out",
			)
		},
		searchFn: func(model.SearchRequestFact) ([]model.POI, error) { return nil, nil },
	}
	svc := newLocationService(t, timeoutClient)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, locationgenerated.NearbyPath, nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusGatewayTimeout {
		t.Fatalf("status=%d, want=504 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] != locationgenerated.ErrUpstreamTimeout.Error() {
		t.Fatalf("code=%v, want %s", body["code"], locationgenerated.ErrUpstreamTimeout.Error())
	}
}
