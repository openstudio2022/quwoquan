package ports

import (
	"context"
	"time"

	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
)

type MediaOriginalAccessEvent struct {
	EventID    string
	EventType  string
	Payload    []byte
	OccurredAt time.Time
}

type MediaOriginalAccessAppendRequest struct {
	Fact          mediamodel.MediaOriginalAccessFact
	CommandDigest string
	Event         MediaOriginalAccessEvent
}

type MediaOriginalAccessAppendResult struct {
	Fact     mediamodel.MediaOriginalAccessFact
	Replayed bool
}

// MediaOriginalAccessAppendSink is the only write port for original access
// audit facts. Implementations must atomically append fact, receipt and outbox.
type MediaOriginalAccessAppendSink interface {
	AppendMediaOriginalAccess(
		context.Context,
		MediaOriginalAccessAppendRequest,
	) (MediaOriginalAccessAppendResult, error)
}
