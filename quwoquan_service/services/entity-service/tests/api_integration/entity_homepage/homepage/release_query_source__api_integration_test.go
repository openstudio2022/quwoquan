package api_integration

import (
	"context"
	"quwoquan_service/internal/platform/testinfra"
	rt "quwoquan_service/runtime/search"
	app "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	ports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
	persistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestVerifiedHomepageSourceIsQueryableWithoutActive(t *testing.T) {
	ctx, cancel := context.WithTimeout(t.Context(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("homepage_source"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		c, stop := context.WithTimeout(context.Background(), 30*time.Second)
		defer stop()
		_ = runtime.Close(c)
	}()
	store := persistence.NewMongoHomepageStore(runtime.Database)
	if err = store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	d := "sha256:" + strings.Repeat("a", 64)
	identity := ports.ReleaseIdentity{Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: "source", ManifestDigest: d}
	_, err = app.StageReleaseCandidate(ctx, store, app.ReleaseStageRequest{Identity: identity, Inputs: []app.ImportedInput{{EntityRef: "entities/place/source", Title: "真实候选", HomepageType: "sight", IntroductionMarkdown: "候选主页说明", CategoryTags: []string{}}}}, time.Now().UTC())
	if err != nil {
		t.Fatal(err)
	}
	snapshot, err := store.ReadHomepageCandidate(ctx, rt.ReleaseCandidateBinding{Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: "source", ManifestDigest: d})
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshot.Homepages) != 1 || snapshot.Validate() != nil {
		t.Fatal("source closure invalid")
	}
}
