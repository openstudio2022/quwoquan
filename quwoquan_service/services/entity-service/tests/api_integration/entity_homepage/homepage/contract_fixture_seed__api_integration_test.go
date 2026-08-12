package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/contractfixture"
	httpadapter "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/adapters/inbound/http"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
)

type entityFixturePack struct {
	Examples map[string]entityFixtureSeedSet `json:"examples"`
}

type entityFixtureSeedSet struct {
	Homepages []entityFixtureHomepage `json:"homepages"`
}

type entityFixtureHomepage struct {
	HomepageID   string `json:"homepageId"`
	HomepageType string `json:"homepageType"`
	Title        string `json:"title"`
	Summary      string `json:"summary"`
}

func TestContractFixtureSeed_EntityReadsViaHandler(t *testing.T) {
	pack, err := contractfixture.LoadRepositoryJSON[entityFixturePack](
		"quwoquan_service/services/entity-service/tests/support/contract_examples/entity_homepage_examples.json",
	)
	if err != nil {
		t.Fatalf("load entity fixture: %v", err)
	}
	seed := pack.Examples["entity_homepage_core"]
	if len(seed.Homepages) == 0 {
		t.Fatalf("entity_homepage_core has no homepages")
	}
	canonicalRefs := map[string]string{}
	duplicateCanonicalRefs := []string{}
	for _, homepage := range seed.Homepages {
		if !homepagemodel.ValidHomepageType(homepage.HomepageType) {
			continue
		}
		canonical := homepagemodel.CanonicalEntityID(
			homepage.HomepageType,
			homepage.Title,
		)
		if previous, exists := canonicalRefs[canonical]; exists {
			duplicateCanonicalRefs = append(
				duplicateCanonicalRefs,
				fmt.Sprintf("%s: %s / %s", canonical, previous, homepage.HomepageID),
			)
			continue
		}
		canonicalRefs[canonical] = homepage.HomepageID
	}
	if len(duplicateCanonicalRefs) > 0 {
		t.Fatalf(
			"entity_homepage_core duplicates import identities: %v",
			duplicateCanonicalRefs,
		)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()
	mongoRuntime, err := testinfra.StartRealMongo(
		ctx,
		fmt.Sprintf("entity_fixture_seed_%d", time.Now().UnixNano()),
	)
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		cleanupCtx, cleanupCancel := context.WithTimeout(
			context.Background(),
			30*time.Second,
		)
		defer cleanupCancel()
		if closeErr := mongoRuntime.Close(cleanupCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	store := homepagepersistence.NewMongoHomepageStore(mongoRuntime.Database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure homepage indexes: %v", err)
	}
	service := application.NewHomepageServiceWithStore(ctx, store)
	inputs := make([]application.ImportedHomepageInput, 0, len(seed.Homepages))
	for _, homepage := range seed.Homepages {
		if !homepagemodel.ValidHomepageType(homepage.HomepageType) {
			continue
		}
		inputs = append(inputs, application.ImportedHomepageInput{
			EntityRef:    homepage.HomepageID,
			HomepageType: homepage.HomepageType,
			Title:        homepage.Title,
		})
	}
	report, err := service.ReconcileImportedHomepages(
		ctx,
		application.HomepageImportRequest{
			Mode:            application.HomepageImportModeSync,
			SourceOwner:     "contract_fixture",
			SourceReleaseID: "entity-homepage-core",
			RunID:           "fixture-import-001",
			Inputs:          inputs,
		},
	)
	if err != nil {
		t.Fatalf("import entity fixture through object store: %v", err)
	}
	if len(report.Created) != len(inputs) {
		t.Fatalf(
			"created homepage count=%d want=%d report=%+v",
			len(report.Created),
			len(inputs),
			report,
		)
	}
	t.Logf("entity homepage import inserted=%d", len(report.Created))

	server := httptest.NewServer(
		httpadapter.NewHandler(service).Routes(),
	)
	defer server.Close()

	read := 0
	for _, homepage := range seed.Homepages {
		if !homepagemodel.ValidHomepageType(homepage.HomepageType) {
			continue
		}
		homepageID := report.EntityRefToHomepageID[homepage.HomepageID]
		if homepageID == "" {
			t.Fatalf("fixture %s missing imported homepage id", homepage.HomepageID)
		}
		detail := requestJSON(
			t,
			server.Client(),
			http.MethodGet,
			server.URL+"/homepages/"+homepageID,
			nil,
			http.StatusOK,
		)
		if got := stringField(t, detail, "title"); got != homepage.Title {
			t.Fatalf("fixture %s title=%q, want %q", homepage.HomepageID, got, homepage.Title)
		}
		read++
	}
	if read == 0 {
		t.Fatal("expected at least one canonical HomepageType fixture")
	}
}
