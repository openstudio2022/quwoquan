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

type BulkIndexer interface {
	EnsureIndex(context.Context) error
	Bulk(context.Context, string, []es.ChangeEvent) error
}

type GroupLister interface {
	ListForSearch(
		ctx context.Context,
		afterID string,
		limit int,
	) ([]groupmodel.CircleGroup, error)
}

type BackfillReport struct {
	TotalGroups   int `json:"totalGroups"`
	IndexedGroups int `json:"indexedGroups"`
	DeletedGroups int `json:"deletedGroups"`
	BatchesPushed int `json:"batchesPushed"`
}

// Backfill reconciles every CircleGroup into the shared index. Public active
// groups are upserted; private or archived groups emit idempotent deletes.
func Backfill(
	ctx context.Context,
	indexer BulkIndexer,
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
	if err := indexer.EnsureIndex(ctx); err != nil {
		return report, err
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
		batch := make([]es.ChangeEvent, 0, len(page))
		for index := range page {
			group := page[index]
			if groupapp.CircleGroupSearchEligible(group) {
				batch = append(batch, es.ChangeEvent{
					Op:  es.OpUpsert,
					Doc: groupapp.ProjectCircleGroupToSearchDocument(group),
				})
				report.IndexedGroups++
				continue
			}
			batch = append(batch, es.ChangeEvent{
				Op: es.OpDelete,
				Doc: rtsearch.Document{
					ObjectType: rtsearch.ObjectTypeCircleGroup,
					ObjectID:   group.ID,
				},
			})
			report.DeletedGroups++
		}
		if err := indexer.Bulk(ctx, "", batch); err != nil {
			return report, err
		}
		report.BatchesPushed++

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
