package application

import (
	"context"
	"errors"

	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
)

var (
	ErrNotFound          = errors.New("feed delivery page not found or expired")
	ErrStoreUnavailable  = errors.New("feed delivery page store unavailable")
	ErrAtomicUnavailable = errors.New("feed delivery page atomic append unavailable")
	ErrPayloadTooLarge   = errors.New("feed delivery page payload exceeds hard limit")
	ErrConflict          = errors.New("feed delivery page id conflicts with a different payload")
	ErrShardKeyQuota     = errors.New("feed delivery page shard live-key quota exceeded")
	ErrShardByteQuota    = errors.New("feed delivery page shard live-byte quota exceeded")
	ErrRepairBound       = errors.New("feed delivery page shard index exceeds repair bound")
)

// Store is the only persistence port for the FeedDeliveryPage fact. Append is
// immutable/idempotent and Load must never extend TTL.
type Store interface {
	Append(context.Context, deliverymodel.Page) (deliverymodel.Page, error)
	Load(context.Context, string, string) (deliverymodel.Page, error)
}
