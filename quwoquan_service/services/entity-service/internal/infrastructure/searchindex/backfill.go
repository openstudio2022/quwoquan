package searchindex

import (
	"context"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/entity-service/internal/application"
)

// defaultBackfillBatchSize bounds how many docs go into one _bulk round trip.
const defaultBackfillBatchSize = 500

// HomepageLister enumerates every homepage for cold-start backfill. The live
// HomepageService satisfies it via ListHomepagesForIndex.
type HomepageLister interface {
	ListHomepagesForIndex(ctx context.Context) []application.Homepage
}

// BulkIndexer is the subset of the ES client backfill needs: ensure the index
// exists, then write batches of change events. *es.Client satisfies it.
type BulkIndexer interface {
	EnsureIndex(ctx context.Context) error
	Bulk(ctx context.Context, index string, events []es.ChangeEvent) error
}

// BackfillReport summarizes a full rebuild for logging / cold-start audit.
type BackfillReport struct {
	TotalHomepages   int `json:"totalHomepages"`
	IndexedHomepages int `json:"indexedHomepages"`
	SkippedHomepages int `json:"skippedHomepages"`
	BatchesPushed    int `json:"batchesPushed"`
}

// Backfill rebuilds the unified index from the live store: it ensures the index
// exists, lists every homepage, projects the eligible (published) ones through
// the shared projection, and bulk-upserts them in batches. It is the cold-start
// / reconcile entry for the entity search index. batchSize <= 0 uses the
// default.
func Backfill(ctx context.Context, indexer BulkIndexer, lister HomepageLister, batchSize int) (BackfillReport, error) {
	var report BackfillReport
	if indexer == nil || lister == nil {
		return report, nil
	}
	if batchSize <= 0 {
		batchSize = defaultBackfillBatchSize
	}
	if err := indexer.EnsureIndex(ctx); err != nil {
		return report, err
	}

	homepages := lister.ListHomepagesForIndex(ctx)
	report.TotalHomepages = len(homepages)
	batch := make([]es.ChangeEvent, 0, batchSize)
	flush := func() error {
		if len(batch) == 0 {
			return nil
		}
		if err := indexer.Bulk(ctx, "", batch); err != nil {
			return err
		}
		report.BatchesPushed++
		batch = batch[:0]
		return nil
	}

	for i := range homepages {
		if !application.HomepageSearchEligible(homepages[i]) {
			report.SkippedHomepages++
			continue
		}
		doc := application.ProjectHomepageToSearchDocument(homepages[i])
		batch = append(batch, es.ChangeEvent{Op: es.OpUpsert, Doc: doc})
		report.IndexedHomepages++
		if len(batch) >= batchSize {
			if err := flush(); err != nil {
				return report, err
			}
		}
	}
	if err := flush(); err != nil {
		return report, err
	}
	return report, nil
}
