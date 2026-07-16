package ports

import (
	"context"
	"time"

	sharemodel "quwoquan_service/services/content-service/internal/domain/content/outbound_share_fact/model"
)

type OutboxEvent struct {
	EventID    string
	EventType  string
	Payload    []byte
	OccurredAt time.Time
}

type AppendRequest struct {
	Fact          sharemodel.Fact
	CommandDigest string
	Outbox        OutboxEvent
}

type AppendResult struct {
	Fact     sharemodel.Fact
	Replayed bool
}

type AppendSink interface {
	Append(context.Context, AppendRequest) (AppendResult, error)
}
