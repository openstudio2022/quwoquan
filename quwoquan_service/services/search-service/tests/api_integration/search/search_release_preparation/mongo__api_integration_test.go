package preparation_test

import (
	"context"
	"errors"
	"quwoquan_service/internal/platform/testinfra"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/search/search_release_preparation/domain"
	persistence "quwoquan_service/services/search-service/internal/search/search_release_preparation/infrastructure/persistence"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t7
func TestMongoPreparationCASReceiptAndExpiredWriter(t *testing.T) {
	ctx, cancel := context.WithTimeout(t.Context(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(ctx, testinfra.UniqueDatabaseName("creator_preparation"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		shutdown, stop := context.WithTimeout(context.Background(), 30*time.Second)
		defer stop()
		if err := runtime.Close(shutdown); err != nil {
			t.Error(err)
		}
	}()
	store := persistence.NewMongoStore(runtime.Database)
	if err = store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	generation := "sha256:" + strings.Repeat("a", 64)
	release := rt.ReleaseCandidateBinding{"gamma", "qwq_data", "isolated-candidate", generation}
	snapshot := rt.CreatorSearchCandidateSnapshot{Release: release, SourceClosureDigest: generation, Profiles: []rt.CreatorSearchPublicSnapshot{}}
	_ = snapshot.Seal()
	command := domain.Command{Binding: rt.ReleaseQueryPreparationBinding{Release: release, Slice: "creator_search", SchemaGeneration: generation, ProviderBindingGeneration: generation}, Snapshot: rt.SearchReleaseCandidateSnapshot{Kind: "creator", Creator: &snapshot}}
	now := time.Now().UTC().Truncate(time.Millisecond)
	state := domain.NewState(command, now)
	if err = store.Create(ctx, state); err != nil {
		t.Fatal(err)
	}
	if err = store.Create(ctx, state); !errors.Is(err, domain.ErrConflict) {
		t.Fatal("duplicate identity accepted", err)
	}
	first := state
	if err = first.Claim(1, "first", now, now.Add(time.Second)); err != nil {
		t.Fatal(err)
	}
	if err = store.Claim(ctx, first, 1, now); err != nil {
		t.Fatal(err)
	}
	second := state
	_ = second.Claim(1, "second", now, now.Add(time.Second))
	if err = store.Claim(ctx, second, 1, now); !errors.Is(err, domain.ErrConflict) {
		t.Fatal("concurrent claim accepted", err)
	}
	loaded, err := store.Load(ctx, state.PreparationID)
	if err != nil {
		t.Fatal(err)
	}
	later := now.Add(2 * time.Second)
	_ = loaded.Claim(2, "replacement", later, later.Add(time.Second))
	if err = store.Claim(ctx, loaded, 2, later); err != nil {
		t.Fatal(err)
	}
	stale := first
	stale.Finish(nil, "provider_unavailable", later)
	if err = store.Commit(ctx, stale, 2, "first", "old-key", "old-digest", later); !errors.Is(err, domain.ErrConflict) {
		t.Fatal("stale writer committed", err)
	}
	version := loaded.Version
	loaded.Finish(nil, "provider_unavailable", later)
	if err = store.Commit(ctx, loaded, version, "replacement", "key", "digest", later); err != nil {
		t.Fatal(err)
	}
	view, found, err := store.Receipt(ctx, state.PreparationID, "key", "digest")
	if err != nil || !found || view.Status != "blocked" {
		t.Fatal(view, found, err)
	}
	if _, _, err = store.Receipt(ctx, state.PreparationID, "key", "different"); !errors.Is(err, domain.ErrConflict) {
		t.Fatal("receipt conflict missing", err)
	}
	history, err := store.ListReceipts(ctx, state.PreparationID, 10)
	if err != nil || len(history) != 1 {
		t.Fatal(history, err)
	}
}
