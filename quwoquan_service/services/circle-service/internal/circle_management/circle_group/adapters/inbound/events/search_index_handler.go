package events

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
	Load(context.Context, string) (groupmodel.CircleGroup, bool, error)
}

type ChangeIndexer interface {
	Apply(context.Context, es.ChangeEvent) error
}

// CircleGroupSearchIndexHandler is the object-owned inbound lifecycle adapter.
// It is the only write-time path from CircleGroup events to the shared search
// index; relay checkpoints advance only after Apply returns successfully.
type CircleGroupSearchIndexHandler struct {
	indexer ChangeIndexer
	groups  GroupLoader
}

func NewCircleGroupSearchIndexHandler(
	indexer ChangeIndexer,
	groups GroupLoader,
) *CircleGroupSearchIndexHandler {
	return &CircleGroupSearchIndexHandler{indexer: indexer, groups: groups}
}

func (handler *CircleGroupSearchIndexHandler) Apply(
	ctx context.Context,
	event groupports.OutboxEvent,
) error {
	if handler == nil || handler.indexer == nil || handler.groups == nil {
		return fmt.Errorf("CircleGroup search handler is not configured")
	}
	groupID := strings.TrimSpace(event.AggregateID)
	if groupID == "" {
		return fmt.Errorf("CircleGroup search event has no aggregate id")
	}
	switch event.EventType {
	case groupevent.CircleGroupArchived:
		return handler.delete(ctx, groupID)
	case groupevent.CircleGroupCreated, groupevent.CircleGroupUpdated:
		return handler.reconcile(ctx, groupID)
	default:
		return nil
	}
}

// Publish is the source outbox port; it deliberately delegates to the same
// object lifecycle method rather than maintaining a second projection path.
func (handler *CircleGroupSearchIndexHandler) Publish(
	ctx context.Context,
	event groupports.OutboxEvent,
) error {
	return handler.Apply(ctx, event)
}

func (handler *CircleGroupSearchIndexHandler) reconcile(
	ctx context.Context,
	groupID string,
) error {
	group, found, err := handler.groups.Load(ctx, groupID)
	if err != nil {
		return fmt.Errorf("load CircleGroup %s for search projection: %w", groupID, err)
	}
	if !found || !groupapp.CircleGroupSearchEligible(group) {
		return handler.delete(ctx, groupID)
	}
	if err := handler.indexer.Apply(ctx, es.ChangeEvent{
		Op:  es.OpUpsert,
		Doc: groupapp.ProjectCircleGroupToSearchDocument(group),
	}); err != nil {
		return fmt.Errorf("index CircleGroup %s: %w", groupID, err)
	}
	return nil
}

func (handler *CircleGroupSearchIndexHandler) delete(
	ctx context.Context,
	groupID string,
) error {
	if err := handler.indexer.Apply(ctx, es.ChangeEvent{
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

var _ groupports.OutboxPublisher = (*CircleGroupSearchIndexHandler)(nil)
