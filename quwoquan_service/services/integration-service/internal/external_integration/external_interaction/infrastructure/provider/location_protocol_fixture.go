package provider

import (
	"context"

	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/ports"
)

// ProtocolFixtureLocationProvider is the non-prod LocationLookupPort substitute.
type ProtocolFixtureLocationProvider struct{}

func NewProtocolFixtureLocationProvider() ports.LocationProvider {
	return ProtocolFixtureLocationProvider{}
}

func (ProtocolFixtureLocationProvider) Nearby(
	_ context.Context,
	query model.NearbyQuery,
) ([]model.POI, error) {
	return []model.POI{{
		ID:        "fixture-nearby",
		Name:      "Fixture Nearby POI",
		Latitude:  query.Lat,
		Longitude: query.Lng,
	}}, nil
}

func (ProtocolFixtureLocationProvider) Search(
	_ context.Context,
	query model.SearchQuery,
) ([]model.POI, error) {
	return []model.POI{{
		ID:        "fixture-search",
		Name:      "Fixture Search POI: " + query.Query,
		Latitude:  query.Lat,
		Longitude: query.Lng,
	}}, nil
}
