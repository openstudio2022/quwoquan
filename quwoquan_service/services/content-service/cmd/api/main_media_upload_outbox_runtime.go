package bootstrap

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	rthealth "quwoquan_service/runtime/health"
	runtimemessaging "quwoquan_service/runtime/messaging"
	uploadapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
	uploadports "quwoquan_service/services/content-service/internal/media/media_upload_session/domain/ports"
	uploadmessaging "quwoquan_service/services/content-service/internal/media/media_upload_session/infrastructure/messaging"
)

func startMediaUploadSessionOutboxRelay(
	ctx context.Context,
	workers *workerRegistry,
	outbox uploadports.TransactionalOutbox,
	transport runtimemessaging.DurableRecordAppender,
	healthChecker *rthealth.Checker,
	logger *slog.Logger,
) error {
	if healthChecker == nil {
		return fmt.Errorf("media upload session relay health checker is required")
	}
	publisher, err := uploadmessaging.NewEventPublisher(transport)
	if err != nil {
		return err
	}
	relay, err := uploadapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		return err
	}
	if err := transport.SetDurableRetention(
		ctx,
		uploadmessaging.MediaUploadSessionEventStream,
		uploadmessaging.MediaUploadSessionEventRetention,
	); err != nil {
		return fmt.Errorf("preflight media upload event stream retention: %w", err)
	}
	healthChecker.Register("media-upload-session-outbox-relay", func(hctx context.Context) error {
		return relay.Healthy(hctx, 3*time.Second)
	})
	workers.Add(func(workerCtx context.Context) {
		relay.Run(workerCtx, time.Second)
	})
	if logger != nil {
		logger.Info(
			"MediaUploadSession outbox relay enabled",
			"stream", uploadmessaging.MediaUploadSessionEventStream,
		)
	}
	return nil
}
