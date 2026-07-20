package local_contract

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	filtercatalogmodel "quwoquan_service/services/content-service/internal/domain/content/filter_catalog_release/model"
	filtercatalogcache "quwoquan_service/services/content-service/internal/infrastructure/content/filter_catalog_release/cache"
)

type filterCatalogActiveReaderStub struct {
	release *filtercatalogmodel.FilterCatalogRelease
	reads   int
}

func (stub *filterCatalogActiveReaderStub) GetActive(
	context.Context,
) (*filtercatalogmodel.FilterCatalogRelease, bool, error) {
	stub.reads++
	return stub.release, stub.release != nil, nil
}

func TestFilterCatalogActiveReaderCachesAndInvalidates(t *testing.T) {
	categories, presets, fallbacks := validFilterCatalogPayload()
	digest, err := filtercatalogmodel.ComputeCanonicalDigest(categories, presets, fallbacks)
	if err != nil {
		t.Fatal(err)
	}
	release, err := filtercatalogmodel.NewStaged(filtercatalogmodel.NewStagedParams{
		ReleaseID:                    "filter-release-cache",
		SourceOwner:                  "qwq-data",
		CanonicalDigest:              digest,
		Categories:                   categories,
		Presets:                      presets,
		RecommendedFallbackPresetIDs: fallbacks,
		ImportedAt:                   time.Date(2026, 7, 20, 12, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatal(err)
	}
	if err := release.Activate(time.Date(2026, 7, 20, 12, 1, 0, 0, time.UTC)); err != nil {
		t.Fatal(err)
	}

	source := &filterCatalogActiveReaderStub{release: release}
	client := rtredis.NewMemoryClient()
	t.Cleanup(func() {
		if err := client.Close(); err != nil {
			t.Errorf("close Redis memory client: %v", err)
		}
	})
	reader := filtercatalogcache.NewActiveReader(source, client, nil)
	ctx := context.Background()

	for index := 0; index < 2; index++ {
		cached, found, err := reader.GetActive(ctx)
		if err != nil || !found || cached.ID() != release.ID() {
			t.Fatalf("read active cache: found=%v release=%v err=%v", found, cached, err)
		}
	}
	if source.reads != 1 {
		t.Fatalf("cache miss source reads=%d want=1", source.reads)
	}
	if err := reader.InvalidateActive(ctx); err != nil {
		t.Fatal(err)
	}
	if _, found, err := reader.GetActive(ctx); err != nil || !found {
		t.Fatalf("read after invalidation: found=%v err=%v", found, err)
	}
	if source.reads != 2 {
		t.Fatalf("invalidation did not force source read: reads=%d", source.reads)
	}
}
