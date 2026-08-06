package persona

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

const personaOutboxLease = 30 * time.Second

type PersonaEventPublisher interface {
	PublishPersona(context.Context, personaports.PersonaOutboxEvent) error
}

type OutboxRelay struct {
	outbox    personaports.PersonaPublicationOutbox
	publisher PersonaEventPublisher
	now       func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewOutboxRelay(outbox personaports.PersonaPublicationOutbox, publisher PersonaEventPublisher) (*OutboxRelay, error) {
	if outbox == nil || publisher == nil {
		return nil, errors.New("Persona outbox and durable publisher are required")
	}
	return &OutboxRelay{outbox: outbox, publisher: publisher, now: time.Now}, nil
}

func (relay *OutboxRelay) Drain(ctx context.Context, limit int) (int, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	published := 0
	for published < limit {
		now := relay.now().UTC()
		event, found, err := relay.outbox.ClaimPendingOutbox(ctx, now, personaOutboxLease)
		if err != nil {
			relay.recordFailure(err)
			return published, err
		}
		if !found {
			relay.recordSuccessfulScan(now)
			return published, nil
		}
		if err := relay.publisher.PublishPersona(ctx, event); err != nil {
			wrapped := fmt.Errorf("publish Persona event %s: %w", event.EventID, err)
			digest := fmt.Sprintf("sha256:%x", sha256.Sum256([]byte(wrapped.Error())))
			retryErr := relay.outbox.SchedulePublicationRetry(
				ctx,
				event.EventID,
				event.ClaimUntil,
				now.Add(personaOutboxRetryDelay(event.AttemptCount)),
				digest,
			)
			if retryErr != nil {
				wrapped = errors.Join(wrapped, retryErr)
			}
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		if err := relay.outbox.MarkPublished(ctx, event.EventID, event.ClaimUntil, relay.now().UTC()); err != nil {
			wrapped := fmt.Errorf("acknowledge Persona event %s: %w", event.EventID, err)
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
			slog.ErrorContext(ctx, "Persona outbox drain failed", "err", err)
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
		return fmt.Errorf("Persona outbox relay unhealthy: %w", lastFailure)
	}
	if lastScan.IsZero() || relay.now().UTC().Sub(lastScan) > maxStaleness {
		return errors.New("Persona outbox relay heartbeat is stale")
	}
	return nil
}

func personaOutboxRetryDelay(attempt int) time.Duration {
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
