package httpadapter

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"quwoquan_service/runtime/contractfixture"
	"quwoquan_service/services/integration-service/internal/application"
	"quwoquan_service/services/integration-service/internal/domain/location/model"
	"quwoquan_service/services/integration-service/internal/generated"
)

type integrationFixturePack struct {
	SeedSets map[string]integrationFixtureSeedSet `json:"seedSets"`
}

type integrationFixtureSeedSet struct {
	POIs []integrationFixturePOI `json:"pois"`
}

type integrationFixturePOI struct {
	POIID   string  `json:"poiId"`
	Name    string  `json:"name"`
	Address string  `json:"address"`
	Lat     float64 `json:"lat"`
	Lng     float64 `json:"lng"`
}

func TestContractFixtureSeed_LocationPOIReadsViaHandler(t *testing.T) {
	pack, err := contractfixture.LoadMetadataJSON[integrationFixturePack](
		"integration/test_fixtures/scenarios/integration_scenarios.json",
	)
	if err != nil {
		t.Fatalf("load integration fixture: %v", err)
	}
	seed := pack.SeedSets["location_poi_core"]
	pois := make([]model.POI, 0, len(seed.POIs))
	for _, item := range seed.POIs {
		pois = append(pois, model.POI{
			ID:        item.POIID,
			Provider:  model.ProviderBaidu,
			Name:      item.Name,
			Address:   item.Address,
			Latitude:  item.Lat,
			Longitude: item.Lng,
		})
	}
	client := &fakeProviderClient{
		name: model.ProviderBaidu,
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return pois, nil
		},
		searchFn: func(model.SearchQuery) ([]model.POI, error) {
			return pois, nil
		},
	}
	svc := application.NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{model.ProviderBaidu: client},
		nil,
	)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, generated.SearchPath+"?"+generated.QueryParamQ+"=西湖", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d, want=200 body=%s", rr.Code, rr.Body.String())
	}
	if !containsBody(rr.Body.String(), "fixture_poi_west_lake") {
		t.Fatalf("expected fixture_poi_west_lake in response: %s", rr.Body.String())
	}
}

func containsBody(body, want string) bool {
	return strings.Contains(body, want)
}
