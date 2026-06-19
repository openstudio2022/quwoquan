package searchindex

import (
	"context"

	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/content-service/internal/application"
)

// defaultBackfillBatchSize bounds how many docs go into one _bulk round trip.
const defaultBackfillBatchSize = 500

// BulkIndexer is the subset of the ES client backfill needs: ensure the index
// exists, then write batches of change events. *es.Client satisfies it.
type BulkIndexer interface {
	EnsureIndex(ctx context.Context) error
	Bulk(ctx context.Context, index string, events []es.ChangeEvent) error
}

// BackfillReport summarizes a full rebuild for logging / cold-start audit.
type BackfillReport struct {
	TotalPosts    int `json:"totalPosts"`
	IndexedPosts  int `json:"indexedPosts"`
	SkippedPosts  int `json:"skippedPosts"`
	BatchesPushed int `json:"batchesPushed"`
}

// Backfill rebuilds the unified index from the live store: it ensures the index
// exists, lists every post, projects the eligible (published + public) ones
// through the shared projection, and bulk-upserts them in batches. It is the
// cold-start / reconcile entry for the content search index. batchSize <= 0 uses
// the default.
func Backfill(ctx context.Context, indexer BulkIndexer, reader PostReader, batchSize int) (BackfillReport, error) {
	var report BackfillReport
	if indexer == nil || reader == nil {
		return report, nil
	}
	if batchSize <= 0 {
		batchSize = defaultBackfillBatchSize
	}
	if err := indexer.EnsureIndex(ctx); err != nil {
		return report, err
	}

	posts := reader.ListAll(ctx)
	report.TotalPosts = len(posts)
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

	for i := range posts {
		if !searchEligible(&posts[i]) {
			report.SkippedPosts++
			continue
		}
		doc := application.ProjectPostToSearchDocument(posts[i])
		batch = append(batch, es.ChangeEvent{Op: es.OpUpsert, Doc: doc})
		report.IndexedPosts++
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
