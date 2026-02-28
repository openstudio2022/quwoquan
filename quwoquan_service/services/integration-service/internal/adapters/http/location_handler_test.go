package httpadapter

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/integration-service/internal/application"
	"quwoquan_service/services/integration-service/internal/domain/location/model"
)

type fakeProviderClient struct {
	name     model.Provider
	nearbyFn func(model.NearbyQuery) ([]model.POI, error)
	searchFn func(model.SearchQuery) ([]model.POI, error)
}

func (f *fakeProviderClient) Name() model.Provider { return f.name }

func (f *fakeProviderClient) Nearby(_ context.Context, q model.NearbyQuery) ([]model.POI, error) {
	return f.nearbyFn(q)
}

func (f *fakeProviderClient) Search(_ context.Context, q model.SearchQuery) ([]model.POI, error) {
	return f.searchFn(q)
}

func TestNearbyUsesDefaultCenterWhenLatLngMissing(t *testing.T) {
	var got model.NearbyQuery
	svc := application.NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{
			model.ProviderBaidu: &fakeProviderClient{
				name: model.ProviderBaidu,
				nearbyFn: func(q model.NearbyQuery) ([]model.POI, error) {
					got = q
					return []model.POI{{Name: "x", Latitude: q.Lat, Longitude: q.Lng}}, nil
				},
				searchFn: func(model.SearchQuery) ([]model.POI, error) {
					return nil, nil
				},
			},
		},
		nil,
	)

	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, "/v1/integration/location/nearby?limit=1", nil)
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
	svc := application.NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{},
		nil,
	)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, "/v1/integration/location/search", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d, want=400 body=%s", rr.Code, rr.Body.String())
	}
}

func TestNearbyBothProvidersFailReturns503(t *testing.T) {
	fail := &fakeProviderClient{
		name: model.ProviderBaidu,
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return nil, errors.New("down")
		},
		searchFn: func(model.SearchQuery) ([]model.POI, error) {
			return nil, nil
		},
	}
	backup := &fakeProviderClient{
		name: model.ProviderAMap,
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return nil, errors.New("down2")
		},
		searchFn: func(model.SearchQuery) ([]model.POI, error) {
			return nil, nil
		},
	}
	svc := application.NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{
			model.ProviderBaidu: fail,
			model.ProviderAMap:  backup,
		},
		nil,
	)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, "/v1/integration/location/nearby", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d, want=503 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] == nil {
		t.Fatalf("error response missing code: %v", body)
	}
}
