package application

import (
	"context"
	"fmt"

	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
)

const homepageSearchConsumer = "entity.homepage-search-index"

type HomepageSearchRelay struct {
	store     HomepageDataStore
	projector Projector
}

func NewHomepageSearchRelay(
	store HomepageDataStore,
	projector Projector,
) (*HomepageSearchRelay, error) {
	if store == nil || projector == nil {
		return nil, fmt.Errorf("homepage search relay requires store and projector")
	}
	return &HomepageSearchRelay{store: store, projector: projector}, nil
}

func (r *HomepageSearchRelay) RunOnce(
	ctx context.Context,
	limit int,
) (int, error) {
	checkpoint, err := r.store.LoadCheckpoint(ctx, homepageSearchConsumer)
	if err != nil {
		return 0, err
	}
	events, err := r.store.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, err
	}
	processed := 0
	for _, event := range events {
		aggregate, found, err := r.store.Load(ctx, event.AggregateID)
		if err != nil {
			return processed, err
		}
		if !found {
			return processed, fmt.Errorf(
				"homepage aggregate %s not found for search projection",
				event.AggregateID,
			)
		}
		snapshot := aggregate.Snapshot()
		view := homepageapp.ViewFromSnapshot(snapshot)
		projection := ProjectorEvent{
			Type: ProjectorEventHomepageUpserted, HomepageID: view.ID,
			SourceVersion: snapshot.Version, Homepage: &view,
		}
		if snapshot.Status == homepagemodel.StatusOffline {
			projection.Type = ProjectorEventHomepageRemoved
			projection.Homepage = nil
		}
		if err := r.projector.Project(ctx, projection); err != nil {
			return processed, err
		}
		if err := r.store.SaveCheckpoint(
			ctx,
			homepageSearchConsumer,
			event.EventID,
		); err != nil {
			return processed, err
		}
		processed++
	}
	return processed, nil
}
