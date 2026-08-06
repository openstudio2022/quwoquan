package runruntime

import (
	"context"
	"errors"
	"log/slog"
	"strings"
	"sync"
	"time"
)

const terminalEventClaimLease = time.Minute

var ErrTerminalEventClaimLost = errors.New(
	"assistant run terminal event claim lost",
)

// TerminalEvent is the immutable, typed subscription source emitted in the
// same transaction as the AssistantRun terminal snapshot and journal event.
type TerminalEvent struct {
	EventID               string
	RunID                 string
	UserID                string
	PersonaID             string
	PersonaContextVersion *int64
	SessionID             string
	DomainID              string
	Outcome               string
	ToolsCalled           *[]string
	LLMModel              *string
	LLMTokensUsed         *int64
	LatencyMS             *int64
	SatisfactionScore     *float64
	OccurredAt            time.Time
	AttemptCount          int
}

type TerminalEventStore interface {
	ClaimPendingTerminalEvents(
		context.Context,
		string,
		time.Time,
		time.Duration,
		int,
	) ([]TerminalEvent, error)
	AcknowledgeTerminalEvent(context.Context, string, string, time.Time) error
	ScheduleTerminalEventRetry(
		context.Context, string, string, time.Time, time.Time, string,
	) error
	ReleaseTerminalEventClaim(context.Context, string, string) error
}

type TerminalRelayOption func(*TerminalRunRelay)

func WithTerminalRelayClock(now func() time.Time) TerminalRelayOption {
	return func(relay *TerminalRunRelay) {
		if now != nil {
			relay.now = now
		}
	}
}

type TerminalEventHandler interface {
	HandleTerminalEvent(context.Context, TerminalEvent) error
}

// TerminalEventPublisher hands the externally declared terminal event to the
// durable transport before any source checkpoint is advanced. Failed and
// cancelled runs still flow through internal idempotent handlers but have no
// undeclared public event fabricated for them.
type TerminalEventPublisher interface {
	PublishTerminalEvent(context.Context, TerminalEvent) error
}

type TerminalEventPublisherFunc func(context.Context, TerminalEvent) error

func (publish TerminalEventPublisherFunc) PublishTerminalEvent(
	ctx context.Context,
	event TerminalEvent,
) error {
	return publish(ctx, event)
}

type TerminalEventHandlerFunc func(context.Context, TerminalEvent) error

func (handle TerminalEventHandlerFunc) HandleTerminalEvent(
	ctx context.Context,
	event TerminalEvent,
) error {
	return handle(ctx, event)
}

// TerminalRunRelay consumes the AssistantRun-owned transactional outbox and
// applies every registered idempotent terminal projection before acknowledging
// the source event. A crash can replay handlers, but can never lose one while
// marking the terminal event processed.
type TerminalRunRelay struct {
	store     TerminalEventStore
	publisher TerminalEventPublisher
	handlers  []TerminalEventHandler
	ownerID   string
	interval  time.Duration
	batchSize int
	now       func() time.Time
	logger    *slog.Logger

	healthMu           sync.RWMutex
	lastSuccessfulScan time.Time
	lastFailure        error
}

func NewTerminalRunRelay(
	store TerminalEventStore,
	publisher TerminalEventPublisher,
	handlers []TerminalEventHandler,
	ownerID string,
	interval time.Duration,
	batchSize int,
	options ...TerminalRelayOption,
) *TerminalRunRelay {
	ownerID = strings.TrimSpace(ownerID)
	if store == nil || publisher == nil || len(handlers) == 0 || ownerID == "" || interval <= 0 {
		panic("assistant run terminal relay dependencies are required")
	}
	for _, handler := range handlers {
		if handler == nil {
			panic("assistant run terminal relay handler is required")
		}
	}
	if batchSize <= 0 {
		batchSize = 128
	}
	relay := &TerminalRunRelay{
		store:     store,
		publisher: publisher,
		handlers:  append([]TerminalEventHandler(nil), handlers...),
		ownerID:   ownerID,
		interval:  interval,
		batchSize: batchSize,
		now:       time.Now,
		logger:    slog.Default(),
	}
	for _, option := range options {
		if option != nil {
			option(relay)
		}
	}
	return relay
}

func (relay *TerminalRunRelay) Run(ctx context.Context) {
	if relay == nil {
		return
	}
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

func (relay *TerminalRunRelay) FlushOnce(ctx context.Context) (int, error) {
	now := relay.now().UTC()
	events, err := relay.store.ClaimPendingTerminalEvents(
		ctx,
		relay.ownerID,
		now,
		terminalEventClaimLease,
		relay.batchSize,
	)
	if err != nil {
		return 0, err
	}
	processed := 0
	for index, event := range events {
		if err := relay.publisher.PublishTerminalEvent(ctx, event); err != nil {
			return processed, errors.Join(
				err,
				relay.scheduleRetry(ctx, event, "publish_failed"),
				relay.releaseClaims(ctx, events[index+1:]),
			)
		}
		for _, handler := range relay.handlers {
			if err := handler.HandleTerminalEvent(ctx, event); err != nil {
				return processed, errors.Join(
					err,
					relay.scheduleRetry(ctx, event, "handler_failed"),
					relay.releaseClaims(ctx, events[index+1:]),
				)
			}
		}
		if err := relay.store.AcknowledgeTerminalEvent(
			ctx,
			event.EventID,
			relay.ownerID,
			relay.now().UTC(),
		); err != nil {
			return processed, errors.Join(
				err,
				relay.scheduleRetry(ctx, event, "checkpoint_failed"),
				relay.releaseClaims(ctx, events[index+1:]),
			)
		}
		processed++
	}
	return processed, nil
}

func (relay *TerminalRunRelay) scheduleRetry(
	ctx context.Context,
	event TerminalEvent,
	failureCode string,
) error {
	failedAt := relay.now().UTC()
	return relay.store.ScheduleTerminalEventRetry(
		ctx,
		event.EventID,
		relay.ownerID,
		failedAt,
		failedAt.Add(terminalEventRetryDelay(event.AttemptCount)),
		failureCode,
	)
}

func terminalEventRetryDelay(attempt int) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	if attempt > 6 {
		attempt = 6
	}
	return time.Second * time.Duration(1<<(attempt-1))
}

func (relay *TerminalRunRelay) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if relay == nil {
		return errors.New("assistant run terminal relay is not configured")
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
		return errors.New("assistant run terminal relay has not completed a scan")
	}
	if relay.now().UTC().Sub(lastSuccessfulScan) > maxStaleness {
		return errors.New("assistant run terminal relay heartbeat is stale")
	}
	return nil
}

func (relay *TerminalRunRelay) flushAndObserve(ctx context.Context) {
	processed, err := relay.FlushOnce(ctx)
	if err != nil {
		relay.recordFailure(err)
		relay.logger.ErrorContext(
			ctx,
			"assistant run terminal relay failed",
			slog.String("error", err.Error()),
		)
		return
	}
	relay.recordSuccessfulScan()
	if processed == relay.batchSize {
		relay.logger.WarnContext(
			ctx,
			"assistant run terminal relay remains backlogged",
			slog.Int("batchSize", relay.batchSize),
		)
	}
}

func (relay *TerminalRunRelay) recordSuccessfulScan() {
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	relay.lastSuccessfulScan = relay.now().UTC()
	relay.lastFailure = nil
}

func (relay *TerminalRunRelay) recordFailure(err error) {
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	relay.lastFailure = err
}

func (relay *TerminalRunRelay) releaseClaims(
	ctx context.Context,
	events []TerminalEvent,
) error {
	var result error
	for _, event := range events {
		result = errors.Join(
			result,
			relay.store.ReleaseTerminalEventClaim(
				ctx,
				event.EventID,
				relay.ownerID,
			),
		)
	}
	return result
}
