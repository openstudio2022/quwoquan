package messaging

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	runtimemessaging "quwoquan_service/runtime/messaging"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	sessionpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
)

const (
	// SessionEventStream is the event_store channel declared by
	// contracts/assistant/assistant_session/events.yaml.
	SessionEventStream          = "events.assistant.sessions"
	SessionEventStreamRetention = 7 * 24 * time.Hour
	sessionOutboxClaimLease     = time.Minute
)

var (
	assistantSessionOutboxRelayTickTotal = promauto.NewCounterVec(
		prometheus.CounterOpts{
			Name: "assistant_session_outbox_relay_tick_total",
			Help: "Assistant session outbox relay outcomes.",
		},
		[]string{"outcome"},
	)
	assistantSessionOutboxPublishedTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "assistant_session_outbox_published_total",
			Help: "AssistantSession domain events confirmed by durable transport.",
		},
	)
)

// SessionEventPublisher is the durable transport half of the relay.
type SessionEventPublisher interface {
	AppendDurable(
		context.Context,
		runtimemessaging.DurableMessage,
	) (string, error)
	SetDurableRetention(context.Context, string, time.Duration) error
}

// SessionOutboxRelay drains the AssistantSession transactional outbox onto the
// declared durable event stream. It follows the same claim/publish/mark
// protocol as the assistant learning fact relay; there is no second outbox
// mechanism in this service.
type SessionOutboxRelay struct {
	store     sessionports.SessionOutboxStore
	publisher SessionEventPublisher
	interval  time.Duration
	batchSize int
	logger    *slog.Logger
	ownerID   string
	now       func() time.Time

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewSessionOutboxRelay(
	store sessionports.SessionOutboxStore,
	publisher SessionEventPublisher,
	interval time.Duration,
	batchSize int,
	logger *slog.Logger,
) (*SessionOutboxRelay, error) {
	if store == nil || publisher == nil {
		return nil, errors.New(
			"assistant session outbox store and publisher are required",
		)
	}
	if interval <= 0 {
		return nil, errors.New("assistant session outbox interval must be positive")
	}
	if batchSize <= 0 {
		batchSize = 128
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &SessionOutboxRelay{
		store:     store,
		publisher: publisher,
		interval:  interval,
		batchSize: batchSize,
		logger:    logger,
		ownerID:   uuid.NewString(),
		now:       time.Now,
	}, nil
}

func (relay *SessionOutboxRelay) Run(ctx context.Context) {
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

func (relay *SessionOutboxRelay) FlushOnce(ctx context.Context) (int, error) {
	events, err := relay.store.ClaimPendingSessionEvents(
		ctx,
		relay.ownerID,
		sessionOutboxClaimLease,
		relay.batchSize,
	)
	if err != nil {
		return 0, err
	}
	published := 0
	for index, event := range events {
		payload, marshalErr := json.Marshal(event.Payload)
		if marshalErr != nil {
			return published, errors.Join(
				marshalErr,
				relay.releaseClaims(ctx, events[index:]),
			)
		}
		ref, appendErr := relay.publisher.AppendDurable(
			ctx,
			runtimemessaging.DurableMessage{
				Stream: SessionEventStream,
				Fields: []runtimemessaging.DurableField{
					{Name: "eventId", Value: event.EventID},
					{Name: "eventType", Value: event.EventType},
					{Name: "aggregateType", Value: "AssistantSession"},
					{Name: "aggregateId", Value: event.SessionID},
					{
						Name:  "occurredAt",
						Value: event.OccurredAt.UTC().Format(time.RFC3339Nano),
					},
					{Name: "payload", Value: string(payload)},
				},
			},
		)
		if appendErr != nil {
			return published, errors.Join(
				appendErr,
				relay.releaseClaims(ctx, events[index:]),
			)
		}
		if retentionErr := relay.publisher.SetDurableRetention(
			ctx,
			SessionEventStream,
			SessionEventStreamRetention,
		); retentionErr != nil {
			return published, errors.Join(
				retentionErr,
				relay.releaseClaims(ctx, events[index:]),
			)
		}
		if markErr := relay.store.MarkSessionEventPublished(
			ctx,
			event.EventID,
			relay.ownerID,
			ref,
			relay.now().UTC(),
		); markErr != nil {
			if errors.Is(markErr, sessionpersistence.ErrSessionOutboxClaimLost) {
				continue
			}
			return published, errors.Join(
				markErr,
				relay.releaseClaims(ctx, events[index:]),
			)
		}
		published++
	}
	return published, nil
}

// FlushAndObserve executes one relay tick and records health and metrics.
func (relay *SessionOutboxRelay) FlushAndObserve(ctx context.Context) {
	published, err := relay.FlushOnce(ctx)
	if err != nil {
		assistantSessionOutboxRelayTickTotal.WithLabelValues("failed").Inc()
		relay.recordFailure(err)
		relay.logger.ErrorContext(
			ctx,
			"assistant session outbox relay failed",
			slog.String("error", err.Error()),
		)
		return
	}
	assistantSessionOutboxRelayTickTotal.WithLabelValues("succeeded").Inc()
	assistantSessionOutboxPublishedTotal.Add(float64(published))
	relay.recordSuccessfulScan()
	if published == relay.batchSize {
		relay.logger.WarnContext(
			ctx,
			"assistant session outbox remains backlogged",
			slog.Int("batchSize", relay.batchSize),
		)
	}
}

func (relay *SessionOutboxRelay) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if relay == nil {
		return errors.New("assistant session outbox relay is not configured")
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
		return errors.New("assistant session outbox relay has not completed a scan")
	}
	if relay.now().UTC().Sub(lastSuccessfulScan) > maxStaleness {
		return errors.New("assistant session outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *SessionOutboxRelay) releaseClaims(
	ctx context.Context,
	events []sessionports.PendingSessionEvent,
) error {
	var result error
	for _, event := range events {
		result = errors.Join(
			result,
			relay.store.ReleaseSessionEventClaim(ctx, event.EventID, relay.ownerID),
		)
	}
	return result
}

func (relay *SessionOutboxRelay) recordSuccessfulScan() {
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	relay.lastSuccessfulScan = relay.now().UTC()
	relay.lastFailure = nil
}

func (relay *SessionOutboxRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	relay.lastFailure = err
}
