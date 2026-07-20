package api_integration

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"
	httpadapter "quwoquan_service/services/entity-service/internal/adapters/http"
	"quwoquan_service/services/entity-service/internal/application"
	homepagepersistence "quwoquan_service/services/entity-service/internal/infrastructure/homepage/persistence"
)

func TestReloadHomepageStateReconcilesAuthoritativeCollectionWithoutSnapshot(t *testing.T) {
	ctx := context.Background()
	store := newReloadHomepageMongoStore(t)
	runtimeService := application.NewHomepageServiceWithStore(ctx, store)
	importerService := application.NewHomepageServiceWithStore(ctx, store)
	server := httptest.NewServer(httpadapter.NewHandler(runtimeService).Routes())
	defer server.Close()

	input := importedHomepageInput("地点/景区/权威集合验证", "权威集合验证")
	report, err := importerService.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
		Mode:            application.HomepageImportModeSync,
		SourceOwner:     "qwq_data",
		SourceReleaseID: "release-001",
		Inputs:          []application.ImportedHomepageInput{input},
	})
	if err != nil {
		t.Fatalf("import homepage: %v", err)
	}
	homepageID := report.EntityRefToHomepageID[input.EntityRef]
	// importer 与在线查询共享权威集合，写入后无需进程内 reload 即刻可读。
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+homepageID, nil, http.StatusOK)

	reload := requestJSON(
		t,
		server.Client(),
		http.MethodPost,
		server.URL+"/homepages:reload",
		nil,
		http.StatusOK,
	)
	if got := intField(t, reload, "snapshotSize"); got != 0 {
		t.Fatalf("reconciliation must not read a global snapshot, size=%d", got)
	}
	if before, after := intField(t, reload, "homepagesBefore"), intField(t, reload, "homepagesAfter"); before != 1 || after != 1 {
		t.Fatalf("authoritative collection count changed during reconciliation: %v", reload)
	}
}

func TestDataSyncOfflineIsVisibleWithoutReload(t *testing.T) {
	ctx := context.Background()
	store := newReloadHomepageMongoStore(t)
	service := application.NewHomepageServiceWithStore(ctx, store)
	server := httptest.NewServer(httpadapter.NewHandler(service).Routes())
	defer server.Close()

	input := importedHomepageInput("地点/景区/同步下线验证", "同步下线验证")
	first, err := service.ReconcileImportedHomepages(ctx, application.HomepageImportRequest{
		Mode:            application.HomepageImportModeSync,
		SourceOwner:     "qwq_data",
		SourceReleaseID: "release-001",
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
		Inputs:          []application.ImportedHomepageInput{},
	}); err != nil {
		t.Fatalf("sync offline: %v", err)
	}
	requestJSON(t, server.Client(), http.MethodGet, server.URL+"/homepages/"+homepageID, nil, http.StatusGone)
}

func importedHomepageInput(entityRef string, title string) application.ImportedHomepageInput {
	return application.ImportedHomepageInput{
		EntityRef: entityRef, Title: title, HomepageType: "sight", City: "杭州",
	}
}

func newReloadHomepageMongoStore(
	t *testing.T,
) *homepagepersistence.MongoHomepageStore {
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
		client.Database("entity_homepage_reload_it"),
		true,
	)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure homepage indexes: %v", err)
	}
	return store
}
