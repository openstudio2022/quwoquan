package ports

import (
	"context"

	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
)

type MediaOriginalAccessAppendRequest struct {
	Fact          mediamodel.MediaOriginalAccessFact
	CommandDigest string
}

type MediaOriginalAccessAppendResult struct {
	Fact     mediamodel.MediaOriginalAccessFact
	Replayed bool
}

// MediaOriginalAccessAppendSink is the only write port for original access
// audit facts. Implementations must atomically append the fact and idempotency
// receipt; the fact itself is the durable audit record.
type MediaOriginalAccessAppendSink interface {
	AppendMediaOriginalAccess(
		context.Context,
		MediaOriginalAccessAppendRequest,
	) (MediaOriginalAccessAppendResult, error)
}
