package provider

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strconv"
	"strings"

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
		ID:        nonprodLocationID("nearby", "", query.Lat, query.Lng),
		Name:      "Nonprod Nearby POI",
		Latitude:  query.Lat,
		Longitude: query.Lng,
	}}, nil
}

func (ProtocolFixtureLocationProvider) Search(
	_ context.Context,
	query model.SearchRequestFact,
) ([]model.POI, error) {
	return []model.POI{{
		ID:        nonprodLocationID("search", query.Query, query.Lat, query.Lng),
		Name:      "Nonprod Search POI: " + strings.TrimSpace(query.Query),
		Latitude:  query.Lat,
		Longitude: query.Lng,
	}}, nil
}

func nonprodLocationID(kind, query string, latitude, longitude float64) string {
	payload := strings.Join([]string{
		strings.TrimSpace(kind),
		strings.TrimSpace(query),
		strconv.FormatFloat(latitude, 'f', 6, 64),
		strconv.FormatFloat(longitude, 'f', 6, 64),
	}, "|")
	digest := sha256.Sum256([]byte(payload))
	return "nonprod-poi-" + hex.EncodeToString(digest[:8])
}
