package placeindex

import (
	"context"
	"fmt"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/content-service/internal/content/post/application/searchprojection"
)

// VersionedIndexer is the only write surface backfill may use: every
// location.place document is written under the place record's own version so a
// rebuild can never regress a newer write-time projection (DEC-002).
// *es.Indexer satisfies it.
type VersionedIndexer interface {
	ApplyVersioned(ctx context.Context, event es.VersionedChangeEvent) (bool, error)
}

// BackfillReport summarizes a full place rebuild for cold-start audit.
type BackfillReport struct {
	TotalPosts       int `json:"totalPosts"`
	ReferencedPosts  int `json:"referencedPosts"`
	SkippedPosts     int `json:"skippedPosts"`
	IndexedPlaces    int `json:"indexedPlaces"`
	TombstonedPlaces int `json:"tombstonedPlaces"`
	// StaleWrites counts documents the provider rejected as not newer than the
	// version it already holds (idempotent replay). They are not failures.
	StaleWrites int `json:"staleWrites"`
}

// Backfill rebuilds first-party place snapshots + their unified index docs from
// the live post store: it aggregates every eligible post (published+public,
// free-text location not bound to a canonical entity) into deduplicated place
// snapshots through the shared application derivation, persists each snapshot
// authoritatively to the store (bumping its version), and upserts the
// location.place docs under that version. Places that no longer have a live
// reference are retired in the store first and then tombstoned under the
// retired version, so an interrupted run remains retryable. Index existence is
// the assembly's responsibility (searchindex.Built.EnsureIndex).
func Backfill(ctx context.Context, indexer VersionedIndexer, reader PostReader, store PlaceStore) (BackfillReport, error) {
	var report BackfillReport
	if indexer == nil || reader == nil || store == nil {
		return report, fmt.Errorf(
			"Place search backfill requires indexer, reader and store",
		)
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

	for _, id := range order {
		stored, err := store.Upsert(ctx, *agg[id])
		if err != nil {
			return report, err
		}
		applied, err := indexer.ApplyVersioned(ctx, es.VersionedChangeEvent{
			Op:            es.OpUpsert,
			Doc:           searchprojection.ProjectPlaceToSearchDocument(stored),
			SourceVersion: stored.Version,
		})
		if err != nil {
			return report, fmt.Errorf("place backfill upsert %s: %w", id, err)
		}
		report.IndexedPlaces++
		if !applied {
			report.StaleWrites++
		}
	}
	for _, existing := range existingPlaces {
		if _, stillReferenced := agg[existing.PlaceID]; stillReferenced {
			continue
		}
		retired := existing
		if len(existing.RefPostIDs) > 0 {
			// A place that just lost its last live reference: retire it first so
			// the tombstone is fenced by a version the store already committed.
			retired, err = store.Retire(ctx, existing.PlaceID)
			if err != nil {
				return report, fmt.Errorf("retire obsolete place snapshot %s: %w", existing.PlaceID, err)
			}
		}
		applied, err := indexer.ApplyVersioned(ctx, es.VersionedChangeEvent{
			Op: es.OpDelete,
			Doc: rtsearch.Document{
				ObjectType: rtsearch.ObjectTypeLocation,
				ObjectID:   retired.PlaceID,
			},
			SourceVersion: retired.Version,
		})
		if err != nil {
			return report, fmt.Errorf("place backfill tombstone %s: %w", retired.PlaceID, err)
		}
		report.TombstonedPlaces++
		if !applied {
			report.StaleWrites++
		}
	}
	return report, nil
}
