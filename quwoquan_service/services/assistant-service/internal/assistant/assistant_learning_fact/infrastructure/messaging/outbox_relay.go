package messaging

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"strconv"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	runtimemessaging "quwoquan_service/runtime/messaging"
	learningpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/persistence"
)

const (
	LearningFactStream          = "events.assistant.learning_facts"
	LearningFactStreamRetention = 7 * 24 * time.Hour
	outboxClaimLease            = time.Minute
)

var (
	assistantLearningOutboxRelayTickTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "assistant_learning_outbox_relay_tick_total",
			Help: "Assistant learning outbox relay outcomes.",
		},
		[]string{"outcome"},
	)
	assistantLearningOutboxPublishedTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "assistant_learning_outbox_published_total",
			Help: "Redacted assistant learning events confirmed by durable transport.",
		},
	)
)

type OutboxStore interface {
	ClaimPendingOutbox(
		context.Context,
		string,
		time.Duration,
		int,
	) ([]learningpersistence.PendingOutboxEvent, error)
	MarkOutboxPublished(context.Context, string, string, string, time.Time) error
	ReleaseOutboxClaim(context.Context, string, string) error
}

type DurablePublisher interface {
	AppendDurable(
		context.Context,
		runtimemessaging.DurableMessage,
	) (string, error)
	SetDurableRetention(context.Context, string, time.Duration) error
}

type OutboxRelay struct {
	store     OutboxStore
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
	store OutboxStore,
	publisher DurablePublisher,
	interval time.Duration,
	batchSize int,
	logger *slog.Logger,
) (*OutboxRelay, error) {
	if store == nil || publisher == nil {
		return nil, errors.New("learning fact outbox store and publisher are required")
	}
	if interval <= 0 {
		return nil, errors.New("learning fact outbox interval must be positive")
	}
	if batchSize <= 0 {
		batchSize = 128
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &OutboxRelay{
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
	relay.FlushAndObserve(ctx)
	ticker := time.NewTicker(relay.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			relay.FlushAndObserve(ctx)
		}
	}
}

func (relay *OutboxRelay) FlushOnce(ctx context.Context) (int, error) {
	events, err := relay.store.ClaimPendingOutbox(
		ctx,
		relay.ownerID,
		outboxClaimLease,
		relay.batchSize,
	)
	if err != nil {
		return 0, err
	}
	published := 0
	for index, event := range events {
		payload, err := json.Marshal(event.Payload)
		if err != nil {
			return published, errors.Join(
				err,
				relay.releaseClaims(ctx, events[index:]),
			)
		}
		ref, err := relay.publisher.AppendDurable(
			ctx,
			runtimemessaging.DurableMessage{
				Stream: LearningFactStream,
				Fields: []runtimemessaging.DurableField{
					{Name: "eventId", Value: event.ID},
					{Name: "eventType", Value: event.EventType},
					{Name: "aggregateType", Value: "AssistantLearningFact"},
					{Name: "aggregateId", Value: event.Payload.EventID},
					{
						Name:  "aggregateVersion",
						Value: strconv.FormatInt(event.AppendSequence, 10),
					},
					{
						Name:  "appendSequence",
						Value: strconv.FormatInt(event.AppendSequence, 10),
					},
					{
						Name:  "occurredAt",
						Value: event.OccurredAt.UTC().Format(time.RFC3339Nano),
					},
					{Name: "payload", Value: string(payload)},
				},
			},
		)
		if err != nil {
			return published, errors.Join(
				err,
				relay.releaseClaims(ctx, events[index:]),
			)
		}
		if err := relay.publisher.SetDurableRetention(
			ctx,
			LearningFactStream,
			LearningFactStreamRetention,
		); err != nil {
			return published, errors.Join(
				err,
				relay.releaseClaims(ctx, events[index:]),
			)
		}
		if err := relay.store.MarkOutboxPublished(
			ctx,
			event.ID,
			relay.ownerID,
			ref,
			relay.now().UTC(),
		); err != nil {
			if errors.Is(err, learningpersistence.ErrOutboxClaimLost) {
				continue
			}
			return published, errors.Join(
				err,
				relay.releaseClaims(ctx, events[index:]),
			)
		}
		published++
	}
	return published, nil
}

// FlushAndObserve executes one relay tick and records health and metrics.
func (relay *OutboxRelay) FlushAndObserve(ctx context.Context) {
	published, err := relay.FlushOnce(ctx)
	if err != nil {
		assistantLearningOutboxRelayTickTotal.WithLabelValues("failed").Inc()
		relay.recordFailure(err)
		relay.logger.ErrorContext(
			ctx,
			"assistant learning fact outbox relay failed",
			slog.String("error", err.Error()),
		)
		return
	}
	assistantLearningOutboxRelayTickTotal.WithLabelValues("succeeded").Inc()
	assistantLearningOutboxPublishedTotal.Add(float64(published))
	relay.recordSuccessfulScan()
	if published == relay.batchSize {
		relay.logger.WarnContext(
			ctx,
			"assistant learning fact outbox remains backlogged",
			slog.Int("batchSize", relay.batchSize),
		)
	}
}

func (relay *OutboxRelay) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if relay == nil {
		return errors.New("assistant learning fact outbox relay is not configured")
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
		return errors.New("assistant learning fact outbox relay has not completed a scan")
	}
	if relay.now().UTC().Sub(lastSuccessfulScan) > maxStaleness {
		return errors.New("assistant learning fact outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) releaseClaims(
	ctx context.Context,
	events []learningpersistence.PendingOutboxEvent,
) error {
	var result error
	for _, event := range events {
		result = errors.Join(
			result,
			relay.store.ReleaseOutboxClaim(ctx, event.ID, relay.ownerID),
		)
	}
	return result
}

func (relay *OutboxRelay) recordSuccessfulScan() {
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	relay.lastSuccessfulScan = relay.now().UTC()
	relay.lastFailure = nil
}

func (relay *OutboxRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	relay.lastFailure = err
}
