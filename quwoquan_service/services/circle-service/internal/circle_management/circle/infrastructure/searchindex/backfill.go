package searchindex

import (
	"context"
	"fmt"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
)

// defaultBackfillBatchSize bounds how many circles are pulled (and pushed) per
// page / _bulk round trip.
const defaultBackfillBatchSize = 500

// BulkIndexer is the subset of the ES client backfill needs: ensure the index
// exists, then write batches of change events. *es.Client satisfies it.
type BulkIndexer interface {
	EnsureIndex(ctx context.Context) error
	Bulk(ctx context.Context, index string, events []es.ChangeEvent) error
}

type CircleLister interface {
	ListForSearch(
		ctx context.Context,
		afterID string,
		limit int,
	) ([]model.Circle, error)
}

// BackfillReport summarizes a full rebuild for logging / cold-start audit.
type BackfillReport struct {
	TotalCircles   int `json:"totalCircles"`
	IndexedCircles int `json:"indexedCircles"`
	DeletedCircles int `json:"deletedCircles"`
	BatchesPushed  int `json:"batchesPushed"`
}

// Backfill rebuilds the unified index from the live store: it ensures the index
// exists, pages through every circle, projects the eligible (active + public)
// ones through the shared projection, and bulk-upserts them per page. It is the
// cold-start / reconcile entry for the circle search index. batchSize <= 0 uses
// the default.
func Backfill(
	ctx context.Context,
	indexer BulkIndexer,
	lister CircleLister,
	batchSize int,
) (BackfillReport, error) {
	var report BackfillReport
	if indexer == nil || lister == nil {
		return report, fmt.Errorf(
			"Circle search backfill requires indexer and lister",
		)
	}
	if batchSize <= 0 {
		batchSize = defaultBackfillBatchSize
	}
	if err := indexer.EnsureIndex(ctx); err != nil {
		return report, err
	}

	afterID := ""
	for {
		page, err := lister.ListForSearch(ctx, afterID, batchSize)
		if err != nil {
			return report, err
		}
		if len(page) == 0 {
			break
		}
		report.TotalCircles += len(page)
		batch := make([]es.ChangeEvent, 0, len(page))
		for i := range page {
			if !application.CircleSearchEligible(page[i]) {
				batch = append(batch, es.ChangeEvent{
					Op: es.OpDelete,
					Doc: rtsearch.Document{
						ObjectType: rtsearch.ObjectTypeCircle,
						ObjectID:   page[i].ID,
					},
				})
				report.DeletedCircles++
				continue
			}
			batch = append(batch, es.ChangeEvent{
				Op:  es.OpUpsert,
				Doc: application.ProjectCircleToSearchDocument(page[i]),
			})
			report.IndexedCircles++
		}
		if err := indexer.Bulk(ctx, "", batch); err != nil {
			return report, err
		}
		report.BatchesPushed++
		nextID := page[len(page)-1].ID
		if nextID == "" || nextID == afterID {
			return report, fmt.Errorf(
				"Circle search backfill cursor did not advance",
			)
		}
		afterID = nextID
		if len(page) < batchSize {
			break
		}
	}
	return report, nil
}
