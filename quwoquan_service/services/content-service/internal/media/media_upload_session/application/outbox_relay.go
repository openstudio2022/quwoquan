package application

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"

	"quwoquan_service/services/content-service/internal/media/media_upload_session/domain/ports"
)

const mediaUploadOutboxClaimLease = 30 * time.Second

type OutboxEventPublisher interface {
	PublishMediaUploadSession(context.Context, ports.OutboxEvent) error
}

type OutboxRelay struct {
	outbox    ports.TransactionalOutbox
	publisher OutboxEventPublisher
	ownerID   string
	now       func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewOutboxRelay(
	outbox ports.TransactionalOutbox,
	publisher OutboxEventPublisher,
) (*OutboxRelay, error) {
	if outbox == nil || publisher == nil {
		return nil, errors.New("media upload session outbox and publisher are required")
	}
	return &OutboxRelay{
		outbox: outbox, publisher: publisher,
		ownerID: "media-upload-session-relay-" + uuid.NewString(), now: time.Now,
	}, nil
}

func (relay *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	published := 0
	for published < limit {
		now := relay.now().UTC()
		event, found, err := relay.outbox.ClaimPendingOutbox(
			ctx, relay.ownerID, now, mediaUploadOutboxClaimLease,
		)
		if err != nil {
			relay.recordFailure(err)
			return published, err
		}
		if !found {
			relay.recordSuccessfulScan(now)
			return published, nil
		}
		if err := validateMediaUploadOutboxEvent(event); err != nil {
			retryErr := relay.outbox.ScheduleOutboxRetry(
				ctx, event.EventID, relay.ownerID,
				now.Add(mediaUploadOutboxRetryDelay(event.AttemptCount)), "invalid_event",
			)
			if retryErr != nil {
				err = errors.Join(err, retryErr)
			}
			relay.recordFailure(err)
			return published, err
		}
		if err := relay.publisher.PublishMediaUploadSession(ctx, event); err != nil {
			retryErr := relay.outbox.ScheduleOutboxRetry(
				ctx, event.EventID, relay.ownerID,
				now.Add(mediaUploadOutboxRetryDelay(event.AttemptCount)), "publish_failed",
			)
			wrapped := fmt.Errorf("publish media upload event %s: %w", event.EventID, err)
			if retryErr != nil {
				wrapped = errors.Join(wrapped, retryErr)
			}
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		if err := relay.outbox.MarkOutboxPublished(
			ctx, event.EventID, relay.ownerID, relay.now().UTC(),
		); err != nil {
			wrapped := fmt.Errorf("checkpoint media upload event %s: %w", event.EventID, err)
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		published++
	}
	relay.recordSuccessfulScan(relay.now().UTC())
	return published, nil
}

func (relay *OutboxRelay) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = time.Second
	}
	relay.drainAndObserve(ctx)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			relay.drainAndObserve(ctx)
		}
	}
}

func (relay *OutboxRelay) Healthy(_ context.Context, maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Second
	}
	relay.healthMu.RLock()
	lastScan, lastFailure := relay.lastSuccessfulScan, relay.lastFailure
	relay.healthMu.RUnlock()
	if lastFailure != nil {
		return fmt.Errorf("media upload session outbox relay unhealthy: %w", lastFailure)
	}
	if lastScan.IsZero() || relay.now().UTC().Sub(lastScan) > maxStaleness {
		return errors.New("media upload session outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) drainAndObserve(ctx context.Context) {
	if _, err := relay.Drain(ctx, 100); err != nil && ctx.Err() == nil {
		slog.ErrorContext(ctx, "media upload session outbox drain failed", "err", err)
	}
}

func validateMediaUploadOutboxEvent(event ports.OutboxEvent) error {
	switch event.EventType {
	case "content.media_upload.initialized", "content.media_upload.completed", "content.media_upload.aborted":
	default:
		return errors.New("media upload session outbox event type is not declared")
	}
	if strings.TrimSpace(event.EventID) == "" || event.AggregateType != "MediaUploadSession" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 ||
		event.OccurredAt.IsZero() || len(event.Payload) == 0 || !json.Valid(event.Payload) {
		return errors.New("media upload session outbox event is incomplete")
	}
	return nil
}

func mediaUploadOutboxRetryDelay(attempt int) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	if attempt > 6 {
		attempt = 6
	}
	return time.Second * time.Duration(1<<(attempt-1))
}

func (relay *OutboxRelay) recordSuccessfulScan(at time.Time) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = at
	// A complete, error-free scan proves that the outbox dependency has
	// recovered even when the queue is empty. Requiring a published event here
	// would permanently latch a transient storage failure on idle runtimes.
	relay.lastFailure = nil
	relay.healthMu.Unlock()
}

func (relay *OutboxRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	relay.lastFailure = err
	relay.healthMu.Unlock()
}
