package bootstrap

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	rthealth "quwoquan_service/runtime/health"
	runtimemessaging "quwoquan_service/runtime/messaging"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	mediamessaging "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/messaging"
)

func startMediaAssetOutboxRelay(
	ctx context.Context,
	workers *workerRegistry,
	reader mediaports.MediaAssetOutboxReader,
	checkpoints mediaports.ProjectionCheckpointStore,
	transport runtimemessaging.DurableRecordAppender,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) error {
	if healthChecker == nil {
		return fmt.Errorf("MediaAsset relay health checker is required")
	}
	publisher, err := mediamessaging.NewEventPublisher(transport)
	if err != nil {
		return err
	}
	relay, err := mediaapp.NewMediaAssetOutboxRelay(
		reader,
		checkpoints,
		publisher,
		"content.media-asset-event-stream",
	)
	if err != nil {
		return err
	}
	if err := transport.SetDurableRetention(
		ctx,
		mediamessaging.MediaAssetEventStream,
		mediamessaging.MediaAssetEventStreamRetention,
	); err != nil {
		return fmt.Errorf("preflight MediaAsset event stream retention: %w", err)
	}
	healthChecker.Register("media-asset-outbox-relay", func(context.Context) error {
		return relay.Healthy(5 * time.Second)
	})
	workers.Add(func(workerCtx context.Context) {
		if err := relay.Run(workerCtx, 250*time.Millisecond); err != nil && workerCtx.Err() == nil && logger != nil {
			logger.Error("MediaAsset outbox relay stopped", "error", err)
		}
	})
	return nil
}
