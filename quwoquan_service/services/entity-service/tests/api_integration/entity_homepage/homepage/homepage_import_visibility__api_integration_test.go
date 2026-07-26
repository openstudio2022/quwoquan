package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"
	httpadapter "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/adapters/inbound/http"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
)

func TestImportedHomepageIsImmediatelyVisible(t *testing.T) {
	ctx := context.Background()
	store := newHomepageImportVisibilityMongoStore(t)
	runtimeService := application.NewHomepageServiceWithStore(ctx, store)
	importerService := application.NewHomepageServiceWithStore(ctx, store)
	server := httptest.NewServer(httpadapter.NewHandler(runtimeService).Routes())
	defer server.Close()

	input := importedHomepageInput("地点/景区/权威集合验证", "权威集合验证")
	report, err := importerService.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
		Mode:            application.HomepageImportModeSync,
		SourceOwner:     "qwq_data",
		SourceReleaseID: "release-001",
		RunID:           "import-run-001",
		Inputs:          []application.ImportedHomepageInput{input},
	})
	if err != nil {
		t.Fatalf("import homepage: %v", err)
	}
	homepageID := report.EntityRefToHomepageID[input.EntityRef]
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+homepageID, nil, http.StatusOK)
}

func TestDataSyncOfflineIsImmediatelyVisible(t *testing.T) {
	ctx := context.Background()
	store := newHomepageImportVisibilityMongoStore(t)
	service := application.NewHomepageServiceWithStore(ctx, store)
	server := httptest.NewServer(httpadapter.NewHandler(service).Routes())
	defer server.Close()

	input := importedHomepageInput("地点/景区/同步下线验证", "同步下线验证")
	first, err := service.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
		Mode:            application.HomepageImportModeSync,
		SourceOwner:     "qwq_data",
		SourceReleaseID: "release-001",
		RunID:           "import-run-001",
		Inputs:          []application.ImportedHomepageInput{input},
	})
	if err != nil {
		t.Fatalf("initial import: %v", err)
	}
	homepageID := first.EntityRefToHomepageID[input.EntityRef]
	if _, err := service.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
		Mode:            application.HomepageImportModeSync,
		SourceOwner:     "qwq_data",
		SourceReleaseID: "release-002",
		RunID:           "import-run-002",
		Inputs:          []application.ImportedHomepageInput{},
	}); err != nil {
		t.Fatalf("sync offline: %v", err)
	}
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+homepageID, nil, http.StatusGone)
	if _, err := service.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
		Mode:            application.HomepageImportModeSync,
		SourceOwner:     "qwq_data",
		SourceReleaseID: "release-001",
		RunID:           "import-run-003",
		Inputs:          []application.ImportedHomepageInput{input},
	}); err != nil {
		t.Fatalf("replay published release: %v", err)
	}
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+homepageID, nil, http.StatusOK)
	if _, err := service.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
		Mode:            application.HomepageImportModeSync,
		SourceOwner:     "qwq_data",
		SourceReleaseID: "release-002",
		RunID:           "import-run-004",
		Inputs:          []application.ImportedHomepageInput{},
	}); err != nil {
		t.Fatalf("replay empty release: %v", err)
	}
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+homepageID, nil, http.StatusGone)
}

func importedHomepageInput(entityRef string, title string) application.ImportedHomepageInput {
	return application.ImportedHomepageInput{
		EntityRef: entityRef, Title: title, HomepageType: "sight", City: "杭州",
	}
}

func newHomepageImportVisibilityMongoStore(t *testing.T) *homepagepersistence.MongoHomepageStore {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	container, err := tryRunReviewMongoContainer(ctx)
	if err != nil {
		cancel()
		t.Fatalf("mongo testcontainer unavailable: %v", err)
	}
	uri, err := container.ConnectionString(ctx)
	if err != nil {
		cancel()
		_ = container.Terminate(context.Background())
		t.Fatalf("mongo connection string: %v", err)
	}
	client, err := mongo.Connect(mongoopts.Client().ApplyURI(uri).SetDirect(true))
	if err != nil {
		cancel()
		_ = container.Terminate(context.Background())
		t.Fatalf("mongo connect: %v", err)
	}
	t.Cleanup(func() {
		_ = client.Disconnect(context.Background())
		_ = container.Terminate(context.Background())
		cancel()
	})
	store := homepagepersistence.NewMongoHomepageStore(
		client.Database("entity_homepage_import_visibility_it"),
		true,
	)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure homepage indexes: %v", err)
	}
	return store
}
