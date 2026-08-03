package ports

import (
	"context"
	"time"

	originalaccessmodel "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/model"
)

type AppendRequest struct {
	Fact          originalaccessmodel.Fact
	CommandDigest string
	RateLimit     RateLimit
}

type RateLimit struct {
	MaxGrants int
	Window    time.Duration
}

func (limit RateLimit) IsValid() bool {
	return limit.MaxGrants > 0 && limit.Window > 0
}

type AppendResult struct {
	Fact     originalaccessmodel.Fact
	Replayed bool
}

// Store is the only write port for original access
// audit facts. Implementations must atomically append the fact and idempotency
// receipt; the fact itself is the durable audit record.
type Store interface {
	Append(
		context.Context,
		AppendRequest,
	) (AppendResult, error)
}
