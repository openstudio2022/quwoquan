// Package messaging relays redacted audit events for Assistant policy
// aggregates. It never emits policy prompt or template bodies.
package messaging

import (
	"context"
	"errors"
	"log/slog"
	"strconv"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

const (
	PolicyAuditStream          = "events.assistant.policy_audit"
	PolicyAuditStreamRetention = 7 * 24 * time.Hour
	policyOutboxClaimLease     = time.Minute
)

var (
	policyOutboxRelayTickTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "assistant_policy_outbox_relay_tick_total",
			Help: "Assistant policy audit outbox relay outcomes.",
		},
		[]string{"aggregate", "outcome"},
	)
	policyOutboxPublishedTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "assistant_policy_outbox_published_total",
			Help: "Assistant policy audit events confirmed by durable transport.",
		},
		[]string{"aggregate"},
	)
)

type DurablePublisher interface {
	AppendDurable(context.Context, runtimemessaging.DurableMessage) (string, error)
	SetDurableRetention(context.Context, string, time.Duration) error
}

type OutboxRelay struct {
	aggregate string
	store     runtimemessaging.LeasedDurableOutboxStore
	publisher DurablePublisher
	interval  time.Duration
	batchSize int
	logger    *slog.Logger
	ownerID   string
	now       func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewOutboxRelay(
	aggregate string,
	store runtimemessaging.LeasedDurableOutboxStore,
	publisher DurablePublisher,
	interval time.Duration,
	batchSize int,
	logger *slog.Logger,
) (*OutboxRelay, error) {
	if aggregate == "" || store == nil || publisher == nil {
		return nil, errors.New("policy outbox aggregate, store, and publisher are required")
	}
	if interval <= 0 {
		return nil, errors.New("policy outbox interval must be positive")
	}
	if batchSize <= 0 {
		batchSize = 128
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &OutboxRelay{
		aggregate: aggregate,
		store:     store,
		publisher: publisher,
		interval:  interval,
		batchSize: batchSize,
		logger:    logger,
		ownerID:   uuid.NewString(),
		now:       time.Now,
	}, nil
}

func (relay *OutboxRelay) Run(ctx context.Context) {
	relay.flushAndObserve(ctx)
	ticker := time.NewTicker(relay.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			relay.flushAndObserve(ctx)
		}
	}
}

func (relay *OutboxRelay) FlushOnce(ctx context.Context) (int, error) {
	events, err := relay.store.ClaimPendingOutbox(
		ctx, relay.ownerID, policyOutboxClaimLease, relay.batchSize,
	)
	if err != nil {
		return 0, err
	}
	published := 0
	for index, event := range events {
		reference, err := relay.publisher.AppendDurable(ctx, runtimemessaging.DurableMessage{
			Stream: PolicyAuditStream,
			Fields: []runtimemessaging.DurableField{
				{Name: "eventId", Value: event.ID},
				{Name: "eventType", Value: event.EventType},
				{Name: "aggregateType", Value: event.AggregateType},
				{Name: "aggregateId", Value: event.AggregateID},
				{Name: "aggregateVersion", Value: strconv.Itoa(event.AggregateVersion)},
				{Name: "occurredAt", Value: event.OccurredAt.UTC().Format(time.RFC3339Nano)},
				{Name: "payload", Value: event.Payload},
			},
		})
		if err != nil {
			return published, errors.Join(err, relay.releaseClaims(ctx, events[index:]))
		}
		if err := relay.publisher.SetDurableRetention(
			ctx, PolicyAuditStream, PolicyAuditStreamRetention,
		); err != nil {
			return published, errors.Join(err, relay.releaseClaims(ctx, events[index:]))
		}
		if err := relay.store.MarkOutboxPublished(
			ctx, event.ID, relay.ownerID, reference, relay.now().UTC(),
		); err != nil {
			return published, errors.Join(err, relay.releaseClaims(ctx, events[index:]))
		}
		published++
	}
	return published, nil
}

func (relay *OutboxRelay) Healthy(_ context.Context, maxStaleness time.Duration) error {
	if relay == nil {
		return errors.New("assistant policy outbox relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.healthMu.RLock()
	lastSuccessfulScan := relay.lastSuccessfulScan
	lastFailure := relay.lastFailure
	relay.healthMu.RUnlock()
	if lastFailure != nil {
		return lastFailure
	}
	if lastSuccessfulScan.IsZero() {
		return errors.New("assistant policy outbox relay has not completed a scan")
	}
	if relay.now().UTC().Sub(lastSuccessfulScan) > maxStaleness {
		return errors.New("assistant policy outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) flushAndObserve(ctx context.Context) {
	published, err := relay.FlushOnce(ctx)
	if err != nil {
		policyOutboxRelayTickTotal.WithLabelValues(relay.aggregate, "failed").Inc()
		relay.healthMu.Lock()
		relay.lastFailure = err
		relay.healthMu.Unlock()
		relay.logger.ErrorContext(ctx, "assistant policy outbox relay failed",
			slog.String("aggregate", relay.aggregate), slog.String("error", err.Error()))
		return
	}
	policyOutboxRelayTickTotal.WithLabelValues(relay.aggregate, "succeeded").Inc()
	policyOutboxPublishedTotal.WithLabelValues(relay.aggregate).Add(float64(published))
	relay.healthMu.Lock()
	relay.lastSuccessfulScan = relay.now().UTC()
	relay.lastFailure = nil
	relay.healthMu.Unlock()
}

func (relay *OutboxRelay) releaseClaims(
	ctx context.Context,
	events []runtimemessaging.LeasedDurableOutboxEvent,
) error {
	var result error
	for _, event := range events {
		result = errors.Join(result, relay.store.ReleaseOutboxClaim(ctx, event.ID, relay.ownerID))
	}
	return result
}
