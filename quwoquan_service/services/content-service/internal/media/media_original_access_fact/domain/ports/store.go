package ports

import (
	"context"

	originalaccessmodel "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/model"
)

type AppendRequest struct {
	Fact          originalaccessmodel.Fact
	CommandDigest string
}

type AppendResult struct {
	Fact     originalaccessmodel.Fact
	Replayed bool
}

// Store is the only write port for original access audit facts.
// Implementations must atomically append the fact and its idempotency receipt.
// The fact is a durable audit record only: quota counters and grant TTL are
// owned by the OriginalAccessQuota aggregate and must not appear here.
type Store interface {
	Append(
		context.Context,
		AppendRequest,
	) (AppendResult, error)
}
