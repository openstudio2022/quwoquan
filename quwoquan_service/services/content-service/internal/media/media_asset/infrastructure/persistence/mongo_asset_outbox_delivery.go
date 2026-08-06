package persistence

import (
	"context"

	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
)

// ReadMediaAssetOutboxAfter reads only media_asset_outbox. The broader
// ReadMediaOutboxAfter method remains reserved for the local media processor,
// which also consumes MediaUploadSession facts.
func (s *MongoMediaStore) ReadMediaAssetOutboxAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]mediaports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	return readMediaOutboxCollection(ctx, s.assetOutbox, checkpoint, limit)
}

var _ mediaports.MediaAssetOutboxReader = (*MongoMediaStore)(nil)
