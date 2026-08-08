package ports

import (
	"context"

	quotamodel "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/model"
)

// ReserveResult reports whether the slot was consumed now or had already been
// consumed by the same idempotency key. Reservation always carries the
// authoritative grant deadline, which replay must not extend.
type ReserveResult struct {
	Reservation quotamodel.Reservation
	Replayed    bool
}

// Store is the only write port of the OriginalAccessQuota aggregate.
// Implementations must commit the counter increment and the reservation
// receipt atomically and must reject the request with the generated
// original_access_rate_limited error once the window is exhausted.
type Store interface {
	Reserve(context.Context, quotamodel.Reservation, quotamodel.Policy) (ReserveResult, error)
}
