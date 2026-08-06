package application

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
)

const subscriptionOutboxClaimLease = 30 * time.Second

type OutboxEventPublisher interface {
	PublishSkillSubscription(context.Context, ports.OutboxEvent) error
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
		return nil, errors.New("skill subscription outbox and publisher are required")
	}
	return &OutboxRelay{
		outbox: outbox, publisher: publisher,
		ownerID: "skill-subscription-relay-" + uuid.NewString(), now: time.Now,
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
			ctx, relay.ownerID, now, subscriptionOutboxClaimLease,
		)
		if err != nil {
			relay.recordFailure(err)
			return published, err
		}
		if !found {
			relay.recordSuccessfulScan(now, published > 0)
			return published, nil
		}
		if err := validateSubscriptionOutboxEvent(event); err != nil {
			failedAt := relay.now().UTC()
			retryErr := relay.outbox.ScheduleOutboxRetry(
				ctx, event.EventID, relay.ownerID,
				failedAt, failedAt.Add(outboxRetryDelay(event.AttemptCount)), "invalid_event",
			)
			if retryErr != nil {
				err = errors.Join(err, retryErr)
			}
			relay.recordFailure(err)
			return published, err
		}
		if err := relay.publisher.PublishSkillSubscription(ctx, event); err != nil {
			failedAt := relay.now().UTC()
			retryErr := relay.outbox.ScheduleOutboxRetry(
				ctx, event.EventID, relay.ownerID,
				failedAt, failedAt.Add(outboxRetryDelay(event.AttemptCount)), "publish_failed",
			)
			wrapped := fmt.Errorf("publish subscription event %s: %w", event.EventID, err)
			if retryErr != nil {
				wrapped = errors.Join(wrapped, retryErr)
			}
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		if err := relay.outbox.MarkOutboxPublished(
			ctx, event.EventID, relay.ownerID, relay.now().UTC(),
		); err != nil {
			wrapped := fmt.Errorf("checkpoint subscription event %s: %w", event.EventID, err)
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		published++
	}
	relay.recordSuccessfulScan(relay.now().UTC(), published > 0)
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
		return fmt.Errorf("skill subscription outbox relay unhealthy: %w", lastFailure)
	}
	if lastScan.IsZero() || relay.now().UTC().Sub(lastScan) > maxStaleness {
		return errors.New("skill subscription outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) drainAndObserve(ctx context.Context) {
	if _, err := relay.Drain(ctx, 100); err != nil && ctx.Err() == nil {
		slog.ErrorContext(ctx, "skill subscription outbox drain failed", "err", err)
	}
}

func validateSubscriptionOutboxEvent(event ports.OutboxEvent) error {
	if err := validateExactSubscriptionPayloadKeys(event.Payload); err != nil {
		return err
	}
	var payload struct {
		SubscriptionID string `json:"subscriptionId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode subscription outbox payload: %w", err)
	}
	switch event.EventType {
	case model.EventCreated, model.EventStatusChanged, model.EventTriggered:
	default:
		return errors.New("unknown skill subscription event")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.AggregateID) == "" ||
		event.AggregateVersion <= 0 || event.OccurredAt.IsZero() ||
		strings.TrimSpace(payload.SubscriptionID) == "" || payload.SubscriptionID != event.AggregateID {
		return errors.New("skill subscription outbox event is incomplete")
	}
	return nil
}

func validateExactSubscriptionPayloadKeys(payload []byte) error {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return errors.New("skill subscription payload must be one JSON object")
	}
	seen := false
	for decoder.More() {
		keyToken, err := decoder.Token()
		key, ok := keyToken.(string)
		if err != nil || !ok || key != "subscriptionId" || seen {
			return errors.New("skill subscription payload keys do not match the event contract")
		}
		seen = true
		var value json.RawMessage
		if err := decoder.Decode(&value); err != nil {
			return fmt.Errorf("decode skill subscription id: %w", err)
		}
	}
	if _, err := decoder.Token(); err != nil || !seen {
		return errors.New("skill subscription payload omits subscriptionId")
	}
	var trailing json.RawMessage
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("skill subscription payload has trailing content")
	}
	return nil
}

func outboxRetryDelay(attempt int) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	if attempt > 6 {
		attempt = 6
	}
	return time.Second * time.Duration(1<<(attempt-1))
}

func (relay *OutboxRelay) recordSuccessfulScan(at time.Time, recovered bool) {
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = at
	if recovered {
		relay.lastFailure = nil
	}
	relay.healthMu.Unlock()
}

func (relay *OutboxRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	relay.lastFailure = err
	relay.healthMu.Unlock()
}
