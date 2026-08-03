package provider

import (
	"context"
	"strings"
	"testing"

	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
)

func TestProtocolFixtureLocationProviderReturnsDeterministicNonprodIdentity(t *testing.T) {
	provider := NewProtocolFixtureLocationProvider()
	query := model.SearchRequestFact{Query: "西湖", Lat: 30.25, Lng: 120.15}
	first, err := provider.Search(context.Background(), query)
	if err != nil {
		t.Fatalf("search: %v", err)
	}
	second, err := provider.Search(context.Background(), query)
	if err != nil {
		t.Fatalf("repeat search: %v", err)
	}
	if len(first) != 1 || len(second) != 1 || first[0].ID != second[0].ID {
		t.Fatalf("expected one deterministic result: first=%#v second=%#v", first, second)
	}
	if !strings.HasPrefix(first[0].ID, "nonprod-poi-") || strings.Contains(first[0].ID, "fixture") {
		t.Fatalf("runtime substitute must not expose fixed fixture identity: %q", first[0].ID)
	}
}
