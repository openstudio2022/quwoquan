package application

import (
	"context"
	"errors"
	"log"
	"testing"

	"quwoquan_service/services/integration-service/internal/domain/location/model"
)

type fakeProvider struct {
	name     model.Provider
	nearbyFn func() ([]model.POI, error)
	searchFn func() ([]model.POI, error)
}

func (f *fakeProvider) Name() model.Provider { return f.name }

func (f *fakeProvider) Nearby(_ context.Context, _ model.NearbyQuery) ([]model.POI, error) {
	return f.nearbyFn()
}

func (f *fakeProvider) Search(_ context.Context, _ model.SearchQuery) ([]model.POI, error) {
	return f.searchFn()
}

func TestNearbyFallbackToBackup(t *testing.T) {
	primaryCalled := 0
	backupCalled := 0
	svc := NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{
			model.ProviderBaidu: &fakeProvider{
				name: model.ProviderBaidu,
				nearbyFn: func() ([]model.POI, error) {
					primaryCalled++
					return nil, errors.New("primary down")
				},
				searchFn: func() ([]model.POI, error) { return nil, nil },
			},
			model.ProviderAMap: &fakeProvider{
				name: model.ProviderAMap,
				nearbyFn: func() ([]model.POI, error) {
					backupCalled++
					return []model.POI{{ID: "1", Provider: model.ProviderAMap, Name: "ok"}}, nil
				},
				searchFn: func() ([]model.POI, error) { return nil, nil },
			},
		},
		log.Default(),
	)

	items, err := svc.Nearby(context.Background(), model.NearbyQuery{})
	if err != nil {
		t.Fatalf("Nearby() error = %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("Nearby() len = %d, want 1", len(items))
	}
	if primaryCalled != 1 || backupCalled != 1 {
		t.Fatalf("calls primary=%d backup=%d, want 1/1", primaryCalled, backupCalled)
	}
}

func TestSearchFailAfterTwoProviders(t *testing.T) {
	svc := NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{
			model.ProviderBaidu: &fakeProvider{
				name:     model.ProviderBaidu,
				nearbyFn: func() ([]model.POI, error) { return nil, nil },
				searchFn: func() ([]model.POI, error) { return nil, errors.New("primary down") },
			},
			model.ProviderAMap: &fakeProvider{
				name:     model.ProviderAMap,
				nearbyFn: func() ([]model.POI, error) { return nil, nil },
				searchFn: func() ([]model.POI, error) { return nil, errors.New("backup down") },
			},
		},
		log.Default(),
	)

	_, err := svc.Search(context.Background(), model.SearchQuery{Query: "cafe"})
	if err == nil {
		t.Fatalf("Search() error = nil, want non-nil")
	}
}
