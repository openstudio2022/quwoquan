package searchindex

import (
	"context"
	"fmt"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	groupmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/model"
)

const defaultBackfillBatchSize = 500

// VersionedIndexer is the only search write surface backfill may use: every
// document carries the CircleGroup's own version so a rebuild can never regress
// a newer write-time projection (DEC-002). *es.Indexer satisfies it.
type VersionedIndexer interface {
	ApplyVersioned(context.Context, es.VersionedChangeEvent) (bool, error)
}

type GroupLister interface {
	ListForSearch(
		ctx context.Context,
		afterID string,
		limit int,
	) ([]groupmodel.CircleGroup, error)
}

type BackfillReport struct {
	TotalGroups      int `json:"totalGroups"`
	IndexedGroups    int `json:"indexedGroups"`
	TombstonedGroups int `json:"tombstonedGroups"`
	// StaleWrites counts documents the provider rejected as not newer than the
	// version it already holds (idempotent replay). They are not failures.
	StaleWrites int `json:"staleWrites"`
	BatchesRead int `json:"batchesRead"`
}

// Backfill reconciles every CircleGroup into the shared index. Public active
// groups are upserted and private or archived groups receive tombstones, each
// under the group's own version. Index existence is the assembly's
// responsibility; batchSize only bounds the source page size.
func Backfill(
	ctx context.Context,
	indexer VersionedIndexer,
	groups GroupLister,
	batchSize int,
) (BackfillReport, error) {
	var report BackfillReport
	if indexer == nil || groups == nil {
		return report, fmt.Errorf(
			"CircleGroup search backfill requires indexer and lister",
		)
	}
	if batchSize <= 0 {
		batchSize = defaultBackfillBatchSize
	}

	afterID := ""
	for {
		page, err := groups.ListForSearch(ctx, afterID, batchSize)
		if err != nil {
			return report, err
		}
		if len(page) == 0 {
			break
		}
		report.TotalGroups += len(page)
		for index := range page {
			group := page[index]
			if group.Version <= 0 {
				return report, fmt.Errorf("CircleGroup %s has no positive version for search backfill", group.ID)
			}
			event := es.VersionedChangeEvent{SourceVersion: group.Version}
			if groupapp.CircleGroupSearchEligible(group) {
				event.Op = es.OpUpsert
				event.Doc = groupapp.ProjectCircleGroupToSearchDocument(group)
				report.IndexedGroups++
			} else {
				event.Op = es.OpDelete
				event.Doc = rtsearch.Document{
					ObjectType: rtsearch.ObjectTypeCircleGroup,
					ObjectID:   group.ID,
				}
				report.TombstonedGroups++
			}
			applied, err := indexer.ApplyVersioned(ctx, event)
			if err != nil {
				return report, fmt.Errorf("CircleGroup search backfill %s %s: %w", event.Op, group.ID, err)
			}
			if !applied {
				report.StaleWrites++
			}
		}
		report.BatchesRead++

		nextID := page[len(page)-1].ID
		if nextID == "" || nextID == afterID {
			return report, fmt.Errorf(
				"CircleGroup search backfill cursor did not advance",
			)
		}
		afterID = nextID
		if len(page) < batchSize {
			break
		}
	}
	return report, nil
}
