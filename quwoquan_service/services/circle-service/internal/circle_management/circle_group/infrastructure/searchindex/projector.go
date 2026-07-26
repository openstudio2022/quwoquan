package searchindex

import (
	"context"
	"fmt"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	groupapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	groupevent "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/event"
	groupmodel "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/model"
	groupports "quwoquan_service/services/circle-service/internal/circle_management/circle_group/domain/ports"
)

type GroupLoader interface {
	Load(
		ctx context.Context,
		groupID string,
	) (groupmodel.CircleGroup, bool, error)
}

type ChangeIndexer interface {
	Apply(context.Context, es.ChangeEvent) error
}

// Projector reconciles CircleGroup outbox records into the shared search index.
// Errors propagate so the dedicated outbox checkpoint cannot advance past an
// uncommitted projection.
type Projector struct {
	indexer ChangeIndexer
	groups  GroupLoader
}

var _ groupports.OutboxPublisher = (*Projector)(nil)

func NewProjector(
	indexer ChangeIndexer,
	groups GroupLoader,
) *Projector {
	return &Projector{indexer: indexer, groups: groups}
}

func (projector *Projector) Publish(
	ctx context.Context,
	event groupports.OutboxEvent,
) error {
	if projector == nil || projector.indexer == nil || projector.groups == nil {
		return fmt.Errorf("CircleGroup search projector is not configured")
	}
	groupID := strings.TrimSpace(event.AggregateID)
	if groupID == "" {
		return fmt.Errorf("CircleGroup search event has no aggregate id")
	}
	switch event.EventType {
	case groupevent.CircleGroupArchived:
		return projector.delete(ctx, groupID)
	case groupevent.CircleGroupCreated, groupevent.CircleGroupUpdated:
		return projector.reconcile(ctx, groupID)
	default:
		return nil
	}
}

func (projector *Projector) reconcile(
	ctx context.Context,
	groupID string,
) error {
	group, found, err := projector.groups.Load(ctx, groupID)
	if err != nil {
		return fmt.Errorf(
			"load CircleGroup %s for search projection: %w",
			groupID,
			err,
		)
	}
	if !found || !groupapp.CircleGroupSearchEligible(group) {
		return projector.delete(ctx, groupID)
	}
	if err := projector.indexer.Apply(ctx, es.ChangeEvent{
		Op:  es.OpUpsert,
		Doc: groupapp.ProjectCircleGroupToSearchDocument(group),
	}); err != nil {
		return fmt.Errorf("index CircleGroup %s: %w", groupID, err)
	}
	return nil
}

func (projector *Projector) delete(
	ctx context.Context,
	groupID string,
) error {
	if err := projector.indexer.Apply(ctx, es.ChangeEvent{
		Op: es.OpDelete,
		Doc: rtsearch.Document{
			ObjectType: rtsearch.ObjectTypeCircleGroup,
			ObjectID:   groupID,
		},
	}); err != nil {
		return fmt.Errorf("delete CircleGroup %s from search index: %w", groupID, err)
	}
	return nil
}
