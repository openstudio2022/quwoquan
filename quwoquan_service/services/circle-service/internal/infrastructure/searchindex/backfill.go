package searchindex

import (
	"context"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/circle-service/internal/application"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
)

// defaultBackfillBatchSize bounds how many circles are pulled (and pushed) per
// page / _bulk round trip.
const defaultBackfillBatchSize = 500

// CircleLister enumerates circles for cold-start backfill via cursor pagination.
// The circle store (persistence.CircleStore) satisfies it.
type CircleLister interface {
	List(ctx context.Context, opts persistence.ListCirclesOpts) ([]model.Circle, string)
}

// BulkIndexer is the subset of the ES client backfill needs: ensure the index
// exists, then write batches of change events. *es.Client satisfies it.
type BulkIndexer interface {
	EnsureIndex(ctx context.Context) error
	Bulk(ctx context.Context, index string, events []es.ChangeEvent) error
}

// BackfillReport summarizes a full rebuild for logging / cold-start audit.
type BackfillReport struct {
	TotalCircles   int `json:"totalCircles"`
	IndexedCircles int `json:"indexedCircles"`
	SkippedCircles int `json:"skippedCircles"`
	BatchesPushed  int `json:"batchesPushed"`
}

// Backfill rebuilds the unified index from the live store: it ensures the index
// exists, pages through every circle, projects the eligible (active + public)
// ones through the shared projection, and bulk-upserts them per page. It is the
// cold-start / reconcile entry for the circle search index. batchSize <= 0 uses
// the default.
func Backfill(ctx context.Context, indexer BulkIndexer, lister CircleLister, batchSize int) (BackfillReport, error) {
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

	cursor := ""
	for {
		page, next := lister.List(ctx, persistence.ListCirclesOpts{Cursor: cursor, Limit: batchSize})
		report.TotalCircles += len(page)
		batch := make([]es.ChangeEvent, 0, len(page))
		for i := range page {
			if !application.CircleSearchEligible(page[i]) {
				report.SkippedCircles++
				continue
			}
			batch = append(batch, es.ChangeEvent{
				Op:  es.OpUpsert,
				Doc: application.ProjectCircleToSearchDocument(page[i]),
			})
			report.IndexedCircles++
		}
		if len(batch) > 0 {
			if err := indexer.Bulk(ctx, "", batch); err != nil {
				return report, err
			}
			report.BatchesPushed++
		}
		// Stop when pagination is exhausted; guard against a store that fails to
		// advance the cursor so backfill cannot spin forever.
		if next == "" || next == cursor || len(page) == 0 {
			break
		}
		cursor = next
	}
	return report, nil
}
