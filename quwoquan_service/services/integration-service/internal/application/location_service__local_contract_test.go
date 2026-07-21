package application

import (
	"context"
	"errors"
	"testing"

	"quwoquan_service/services/integration-service/internal/domain/location/model"
)

type fakeProvider struct {
	nearbyFn func() ([]model.POI, error)
	searchFn func() ([]model.POI, error)
}

func (f *fakeProvider) Nearby(_ context.Context, _ model.NearbyQuery) ([]model.POI, error) {
	return f.nearbyFn()
}

func (f *fakeProvider) Search(_ context.Context, _ model.SearchQuery) ([]model.POI, error) {
	return f.searchFn()
}

func TestNearbyUsesExactlyOneBoundProvider(t *testing.T) {
	called := 0
	svc, err := NewService(&fakeProvider{
		nearbyFn: func() ([]model.POI, error) {
			called++
			return []model.POI{{ID: "1", Name: "ok"}}, nil
		},
		searchFn: func() ([]model.POI, error) { return nil, nil },
	})
	if err != nil {
		t.Fatalf("NewService() error = %v", err)
	}

	items, err := svc.Nearby(context.Background(), model.NearbyQuery{})
	if err != nil {
		t.Fatalf("Nearby() error = %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("Nearby() len = %d, want 1", len(items))
	}
	if called != 1 {
		t.Fatalf("bound provider calls = %d, want 1", called)
	}
}

func TestSearchPropagatesBoundProviderFailure(t *testing.T) {
	expected := errors.New("structured location provider failure")
	svc, err := NewService(&fakeProvider{
		nearbyFn: func() ([]model.POI, error) { return nil, nil },
		searchFn: func() ([]model.POI, error) { return nil, expected },
	})
	if err != nil {
		t.Fatalf("NewService() error = %v", err)
	}

	_, err = svc.Search(context.Background(), model.SearchQuery{Query: "cafe"})
	if !errors.Is(err, expected) {
		t.Fatalf("Search() error = %v, want provider failure", err)
	}
}

func TestNewServiceRequiresLocationPort(t *testing.T) {
	if _, err := NewService(nil); err == nil {
		t.Fatal("NewService(nil) must fail closed")
	}
}
