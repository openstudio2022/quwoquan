package events

import (
	"context"
	"errors"
	"fmt"
	"strings"

	viewapp "quwoquan_service/services/circle-service/internal/circle_management/circle_search_item_view/application"
)

// CircleSearchItemViewProjector is the object-owned lifecycle adapter.  It
// resolves the current authoritative snapshot before applying an idempotent
// index mutation, so a transport relay cannot bypass visibility/tombstone
// semantics.
type CircleSearchItemViewProjector struct {
	projector *viewapp.Projector
	snapshots viewapp.SnapshotReader
}

func NewSink(projector *viewapp.Projector, snapshots viewapp.SnapshotReader) *CircleSearchItemViewProjector {
	if projector == nil || snapshots == nil {
		panic("CircleSearchItemView event sink requires projector and snapshot reader")
	}
	return &CircleSearchItemViewProjector{projector: projector, snapshots: snapshots}
}

func (sink *CircleSearchItemViewProjector) Apply(ctx context.Context, event viewapp.LifecycleEvent) error {
	circleID := strings.TrimSpace(event.CircleID)
	version := event.SourceVersion
	if circleID == "" || version <= 0 {
		return errors.New("CircleSearchItemView event requires circleId and source version")
	}
	switch event.Type {
	case "CircleArchived", "CircleDeleted":
		_, err := sink.projector.Delete(ctx, circleID, version)
		return err
	case "CircleCreated", "CircleUpdated":
		item, visible, err := sink.snapshots.LoadSearchItem(ctx, circleID)
		if err != nil {
			return fmt.Errorf("load CircleSearchItemView snapshot: %w", err)
		}
		if !visible {
			_, err = sink.projector.Delete(ctx, circleID, version)
			return err
		}
		if item.SourceVersion < version {
			item.SourceVersion = version
		}
		_, err = sink.projector.Upsert(ctx, item)
		return err
	default:
		return nil
	}
}

var _ viewapp.EventHandler = (*CircleSearchItemViewProjector)(nil)
