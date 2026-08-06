package application

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"
)

const notificationDeliveryJobOutboxLease = 30 * time.Second

var ErrOutboxClaimLost = errors.New("NotificationDeliveryJob outbox claim lost")

type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          map[string]string
	OccurredAt       time.Time
	AttemptCount     int
}

type PublicationOutbox interface {
	ClaimPendingOutbox(context.Context, string, time.Time, time.Duration) (OutboxEvent, bool, error)
	MarkPublished(context.Context, string, string, time.Time) error
	SchedulePublicationRetry(context.Context, string, string, time.Time, string) error
}

type OutboxPublisher interface {
	PublishNotificationDeliveryJob(context.Context, OutboxEvent) error
}

// OutboxRelay performs an at-least-once handoff from the object-owned Mongo
// outbox to the canonical durable event stream. Only a successful durable
// append can acknowledge a claimed row; failures release it with backoff.
type OutboxRelay struct {
	outbox    PublicationOutbox
	publisher OutboxPublisher
	ownerID   string
	now       func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewOutboxRelay(outbox PublicationOutbox, publisher OutboxPublisher, ownerID string) (*OutboxRelay, error) {
	ownerID = strings.TrimSpace(ownerID)
	if outbox == nil || publisher == nil || ownerID == "" {
		return nil, errors.New("NotificationDeliveryJob outbox, publisher and owner are required")
	}
	return &OutboxRelay{outbox: outbox, publisher: publisher, ownerID: ownerID, now: time.Now}, nil
}

func (relay *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	published := 0
	for published < limit {
		now := relay.now().UTC()
		event, found, err := relay.outbox.ClaimPendingOutbox(ctx, relay.ownerID, now, notificationDeliveryJobOutboxLease)
		if err != nil {
			relay.recordFailure(err)
			return published, err
		}
		if !found {
			relay.recordSuccessfulScan(now)
			return published, nil
		}
		if err := validatePublicationEvent(event); err != nil {
			err = relay.scheduleRetry(ctx, event, now, err)
			relay.recordFailure(err)
			return published, err
		}
		if err := relay.publisher.PublishNotificationDeliveryJob(ctx, event); err != nil {
			wrapped := fmt.Errorf("publish NotificationDeliveryJob event %s: %w", event.EventID, err)
			wrapped = relay.scheduleRetry(ctx, event, now, wrapped)
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		if err := relay.outbox.MarkPublished(ctx, event.EventID, relay.ownerID, relay.now().UTC()); err != nil {
			wrapped := fmt.Errorf("acknowledge NotificationDeliveryJob event %s: %w", event.EventID, err)
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		published++
	}
	relay.recordSuccessfulScan(relay.now().UTC())
	return published, nil
}

func (relay *OutboxRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := relay.Drain(ctx, 100); err != nil && ctx.Err() == nil {
			slog.ErrorContext(ctx, "NotificationDeliveryJob outbox drain failed", "err", err)
		}
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
		}
	}
}

func (relay *OutboxRelay) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 15 * time.Second
	}
	relay.healthMu.RLock()
	lastScan, lastFailure := relay.lastSuccessfulScan, relay.lastFailure
	relay.healthMu.RUnlock()
	if lastFailure != nil {
		return fmt.Errorf("NotificationDeliveryJob outbox relay unhealthy: %w", lastFailure)
	}
	if lastScan.IsZero() || relay.now().UTC().Sub(lastScan) > maxStaleness {
		return errors.New("NotificationDeliveryJob outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) scheduleRetry(ctx context.Context, event OutboxEvent, now time.Time, failure error) error {
	digest := fmt.Sprintf("sha256:%x", sha256.Sum256([]byte(failure.Error())))
	retryErr := relay.outbox.SchedulePublicationRetry(
		ctx, event.EventID, relay.ownerID,
		now.Add(publicationRetryDelay(event.AttemptCount)), digest,
	)
	if retryErr != nil {
		return errors.Join(failure, retryErr)
	}
	return failure
}

func validatePublicationEvent(event OutboxEvent) error {
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 ||
		event.OccurredAt.IsZero() || event.Payload == nil {
		return errors.New("NotificationDeliveryJob outbox event is incomplete")
	}
	return nil
}

func publicationRetryDelay(attempt int) time.Duration {
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
	relay.lastFailure = nil
	relay.healthMu.Unlock()
}

func (relay *OutboxRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	relay.lastFailure = err
	relay.healthMu.Unlock()
}
