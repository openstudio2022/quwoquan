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
}

func (f *fakeProviderClient) Nearby(_ context.Context, q model.NearbyQuery) ([]model.POI, error) {
	return f.nearbyFn(q)
}

func (f *fakeProviderClient) Search(_ context.Context, q model.SearchRequestFact) ([]model.POI, error) {
	return f.searchFn(q)
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
