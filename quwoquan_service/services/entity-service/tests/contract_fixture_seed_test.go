package tests

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/runtime/contractfixture"
	httpadapter "quwoquan_service/services/entity-service/internal/adapters/http"
	"quwoquan_service/services/entity-service/internal/application"
)

type entityFixturePack struct {
	SeedSets map[string]entityFixtureSeedSet `json:"seedSets"`
}

type entityFixtureSeedSet struct {
	Homepages []entityFixtureHomepage `json:"homepages"`
}

type entityFixtureHomepage struct {
	HomepageID string `json:"homepageId"`
	Type       string `json:"type"`
	Title      string `json:"title"`
	Summary    string `json:"summary"`
}

func TestContractFixtureSeed_EntityReadsViaHandler(t *testing.T) {
	pack, err := contractfixture.LoadMetadataJSON[entityFixturePack](
		"entity/test_fixtures/scenarios/entity_scenarios.json",
	)
	if err != nil {
		t.Fatalf("load entity fixture: %v", err)
	}
	seed := pack.SeedSets["entity_homepage_core"]
	if len(seed.Homepages) == 0 {
		t.Fatalf("entity_homepage_core has no homepages")
	}

	server := httptest.NewServer(
		httpadapter.NewHandler(application.NewHomepageService()).Routes(),
	)
	defer server.Close()

	for _, homepage := range seed.Homepages {
		candidate := requestJSON(t, server.Client(), http.MethodPost, server.URL+"/v1/homepages/candidates", map[string]any{
			"title":        homepage.Title,
			"subtitle":     homepage.Summary,
			"homepageType": supportedHomepageType(homepage.Type),
			"city":         "杭州",
		}, http.StatusCreated)
		homepageID := stringField(t, candidate, "_id")
		requestJSON(t, server.Client(), http.MethodPost, server.URL+"/v1/homepages/candidates/"+homepageID+":publish", nil, http.StatusOK)
	}

	search := requestJSON(t, server.Client(), http.MethodGet, server.URL+"/v1/homepages/search?query=契约&status=published", nil, http.StatusOK)
	if len(sliceField(t, search, "items")) == 0 {
		t.Fatalf("expected contract fixture homepages in search response")
	}
}

func supportedHomepageType(value string) string {
	switch value {
	case "vehicle", "hotel", "restaurant", "sight":
		return value
	case "poi":
		return "sight"
	default:
		return "sight"
	}
}
