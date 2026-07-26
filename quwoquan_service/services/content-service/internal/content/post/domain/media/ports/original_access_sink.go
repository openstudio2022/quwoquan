package ports

import (
	"context"
	"time"

	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
)

type MediaOriginalAccessAppendRequest struct {
	Fact          mediamodel.MediaOriginalAccessFact
	CommandDigest string
	RateLimit     MediaOriginalAccessRateLimit
}

type MediaOriginalAccessRateLimit struct {
	MaxGrants int
	Window    time.Duration
}

func (limit MediaOriginalAccessRateLimit) IsValid() bool {
	return limit.MaxGrants > 0 && limit.Window > 0
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
