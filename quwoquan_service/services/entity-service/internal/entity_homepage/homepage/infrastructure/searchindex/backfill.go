package searchindex

import (
	"context"
	"fmt"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
)

// defaultBackfillBatchSize bounds how many docs go into one _bulk round trip.
const defaultBackfillBatchSize = 500

// HomepageLister enumerates every homepage for cold-start backfill. The live
// HomepageService satisfies it via ListHomepagesForIndex.
type HomepageLister interface {
	ScanHomepagesForIndex(
		ctx context.Context,
		cursor string,
		limit int,
	) ([]application.Homepage, string, error)
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
	DeletedHomepages int `json:"deletedHomepages"`
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
		return report, fmt.Errorf(
			"Homepage search backfill requires indexer and lister",
		)
	}
	if batchSize <= 0 {
		batchSize = defaultBackfillBatchSize
	}
	if err := indexer.EnsureIndex(ctx); err != nil {
		return report, err
	}

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

	cursor := ""
	for {
		homepages, nextCursor, err := lister.ScanHomepagesForIndex(ctx, cursor, batchSize)
		if err != nil {
			return report, err
		}
		report.TotalHomepages += len(homepages)
		for i := range homepages {
			if !application.HomepageSearchEligible(homepages[i]) {
				batch = append(batch, es.ChangeEvent{
					Op: es.OpDelete,
					Doc: rtsearch.Document{
						ObjectType: rtsearch.ObjectTypeEntityHomepage,
						ObjectID:   homepages[i].ID,
					},
				})
				report.DeletedHomepages++
				if len(batch) >= batchSize {
					if err := flush(); err != nil {
						return report, err
					}
				}
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
		if nextCursor == "" {
			break
		}
		cursor = nextCursor
	}
	if err := flush(); err != nil {
		return report, err
	}
	return report, nil
}
