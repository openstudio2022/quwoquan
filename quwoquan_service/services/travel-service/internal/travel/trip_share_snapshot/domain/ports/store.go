package ports

import (
	"context"
	"errors"
	"time"

	mapmodel "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/model"
	timelinemodel "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/model"
)

var (
	ErrNotFound            = errors.New("trip share snapshot not found")
	ErrCommitConflict      = errors.New("trip share snapshot commit conflict")
	ErrIdempotencyConflict = errors.New("trip share snapshot idempotency conflict")
)

type Source struct {
	Timeline timelinemodel.View
	Map      mapmodel.View
}

type SourceReader interface {
	ReadShareSource(context.Context, string, string) (Source, error)
}

type CommandResult struct {
	Snapshot         model.Snapshot
	IdempotentReplay bool
}

type Receipt struct {
	IdempotencyKey string
	CommandDigest  string
	Result         CommandResult
	ExpiresAt      time.Time
}

type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          map[string]any
	OccurredAt       time.Time
}

type Commit struct {
	Snapshot model.Snapshot
	Receipt  Receipt
	Event    OutboxEvent
}

type Store interface {
	Get(context.Context, string) (model.Snapshot, error)
	FindReceipt(context.Context, string) (Receipt, bool, error)
	Commit(context.Context, Commit) error
}

type IDGenerator interface {
	NewTripShareSnapshotID() (string, error)
	NewEventID() (string, error)
}
