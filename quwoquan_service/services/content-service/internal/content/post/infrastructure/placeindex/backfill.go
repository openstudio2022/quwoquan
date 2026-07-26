package placeindex

import (
	"context"
	"fmt"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/content-service/internal/content/post/application/searchprojection"
)

// defaultBackfillBatchSize bounds how many place docs go into one _bulk round trip.
const defaultBackfillBatchSize = 500

// BulkIndexer is the subset of the ES client backfill needs: ensure the index
// exists, then write batches of change events. *es.Client satisfies it.
type BulkIndexer interface {
	EnsureIndex(ctx context.Context) error
	Bulk(ctx context.Context, index string, events []es.ChangeEvent) error
}

// BackfillReport summarizes a full place rebuild for cold-start audit.
type BackfillReport struct {
	TotalPosts      int `json:"totalPosts"`
	ReferencedPosts int `json:"referencedPosts"`
	SkippedPosts    int `json:"skippedPosts"`
	IndexedPlaces   int `json:"indexedPlaces"`
	DeletedPlaces   int `json:"deletedPlaces"`
	BatchesPushed   int `json:"batchesPushed"`
}

// Backfill rebuilds first-party place snapshots + their unified index docs from
// the live post store: it ensures the index exists, aggregates every eligible
// post (published+public, free-text location not bound to a canonical entity)
// into deduplicated place snapshots through the shared application derivation,
// persists each snapshot authoritatively to the store, and bulk-upserts the
// location.place docs in batches. batchSize <= 0 uses the default.
func Backfill(ctx context.Context, indexer BulkIndexer, reader PostReader, store PlaceStore, batchSize int) (BackfillReport, error) {
	var report BackfillReport
	if indexer == nil || reader == nil || store == nil {
		return report, fmt.Errorf(
			"Place search backfill requires indexer, reader and store",
		)
	}
	if batchSize <= 0 {
		batchSize = defaultBackfillBatchSize
	}
	if err := indexer.EnsureIndex(ctx); err != nil {
		return report, err
	}

	posts, err := reader.ListAll(ctx)
	if err != nil {
		return report, fmt.Errorf("list posts: %w", err)
	}
	report.TotalPosts = len(posts)
	existingPlaces, err := store.ListAll(ctx)
	if err != nil {
		return report, fmt.Errorf("list existing place snapshots: %w", err)
	}

	// Aggregate posts → canonical place snapshots (preserving first-seen order
	// so the rebuild is deterministic).
	agg := map[string]*searchprojection.PlaceSnapshot{}
	order := make([]string, 0)
	for i := range posts {
		ref, ok := searchprojection.DerivePlaceRef(posts[i])
		if !ok {
			report.SkippedPosts++
			continue
		}
		report.ReferencedPosts++
		snap := agg[ref.PlaceID]
		if snap == nil {
			snap = &searchprojection.PlaceSnapshot{PlaceID: ref.PlaceID, Name: ref.Name, Geo: ref.Geo}
			agg[ref.PlaceID] = snap
			order = append(order, ref.PlaceID)
		}
		snap.RefPostIDs = append(snap.RefPostIDs, posts[i].ID)
		if snap.Geo == nil && ref.Geo != nil {
			snap.Geo = ref.Geo
		}
	}

	batch := make([]es.ChangeEvent, 0, batchSize)
	pendingPlaceDeletes := make([]string, 0, batchSize)
	flush := func() error {
		if len(batch) == 0 {
			return nil
		}
		if err := indexer.Bulk(ctx, "", batch); err != nil {
			return err
		}
		for _, placeID := range pendingPlaceDeletes {
			if err := store.Delete(ctx, placeID); err != nil {
				return fmt.Errorf(
					"delete obsolete place snapshot %s: %w",
					placeID,
					err,
				)
			}
			report.DeletedPlaces++
		}
		report.BatchesPushed++
		batch = batch[:0]
		pendingPlaceDeletes = pendingPlaceDeletes[:0]
		return nil
	}

	for _, id := range order {
		snap := *agg[id]
		if err := store.Upsert(ctx, snap); err != nil {
			return report, err
		}
		batch = append(batch, es.ChangeEvent{Op: es.OpUpsert, Doc: searchprojection.ProjectPlaceToSearchDocument(snap)})
		report.IndexedPlaces++
		if len(batch) >= batchSize {
			if err := flush(); err != nil {
				return report, err
			}
		}
	}
	for _, existing := range existingPlaces {
		if _, stillReferenced := agg[existing.PlaceID]; stillReferenced {
			continue
		}
		batch = append(batch, es.ChangeEvent{
			Op: es.OpDelete,
			Doc: rtsearch.Document{
				ObjectType: rtsearch.ObjectTypeLocation,
				ObjectID:   existing.PlaceID,
			},
		})
		pendingPlaceDeletes = append(
			pendingPlaceDeletes,
			existing.PlaceID,
		)
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
