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

// VersionedIndexer is the only search write surface the handler may use: every
// document carries the CircleGroup's own version so out-of-order relays can
// never regress a newer projection (DEC-002). *es.Indexer satisfies it.
type VersionedIndexer interface {
	ApplyVersioned(context.Context, es.VersionedChangeEvent) (bool, error)
}

// CircleGroupSearchIndexHandler is the object-owned inbound lifecycle adapter.
// It is the only write-time path from CircleGroup events to the shared search
// index; relay checkpoints advance only after the versioned write returns
// successfully (a stale/replayed write is a success, not a failure).
type CircleGroupSearchIndexHandler struct {
	indexer VersionedIndexer
	groups  GroupLoader
}

func NewCircleGroupSearchIndexHandler(
	indexer VersionedIndexer,
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
	case groupevent.CircleGroupCreated, groupevent.CircleGroupUpdated, groupevent.CircleGroupArchived:
		return handler.reconcile(ctx, groupID, event)
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

// reconcile 读回 CircleGroup 并按当前可见性决定 upsert 或 tombstone。
// sourceVersion 来源（DEC-002）：读到聚合时用其自身 version（乐观并发单调
// 递增，含 archive）；聚合已不可读时用触发本次投影的 outbox 事实的
// AggregateVersion，它是该聚合最后一次已提交的版本。
func (handler *CircleGroupSearchIndexHandler) reconcile(
	ctx context.Context,
	groupID string,
	event groupports.OutboxEvent,
) error {
	group, found, err := handler.groups.Load(ctx, groupID)
	if err != nil {
		return fmt.Errorf("load CircleGroup %s for search projection: %w", groupID, err)
	}
	if !found {
		if event.AggregateVersion <= 0 {
			return fmt.Errorf(
				"CircleGroup %s is unreadable and event %s carries no aggregate version for its search tombstone",
				groupID, event.EventType,
			)
		}
		return handler.tombstone(ctx, groupID, event.AggregateVersion)
	}
	if group.Version <= 0 {
		return fmt.Errorf("CircleGroup %s has no positive version for search projection", groupID)
	}
	if !groupapp.CircleGroupSearchEligible(group) {
		return handler.tombstone(ctx, groupID, group.Version)
	}
	if _, err := handler.indexer.ApplyVersioned(ctx, es.VersionedChangeEvent{
		Op:            es.OpUpsert,
		Doc:           groupapp.ProjectCircleGroupToSearchDocument(group),
		SourceVersion: group.Version,
	}); err != nil {
		return fmt.Errorf("index CircleGroup %s: %w", groupID, err)
	}
	return nil
}

func (handler *CircleGroupSearchIndexHandler) tombstone(
	ctx context.Context,
	groupID string,
	sourceVersion int64,
) error {
	if _, err := handler.indexer.ApplyVersioned(ctx, es.VersionedChangeEvent{
		Op: es.OpDelete,
		Doc: rtsearch.Document{
			ObjectType: rtsearch.ObjectTypeCircleGroup,
			ObjectID:   groupID,
		},
		SourceVersion: sourceVersion,
	}); err != nil {
		return fmt.Errorf("tombstone CircleGroup %s in search index: %w", groupID, err)
	}
	return nil
}

var _ groupports.OutboxPublisher = (*CircleGroupSearchIndexHandler)(nil)
