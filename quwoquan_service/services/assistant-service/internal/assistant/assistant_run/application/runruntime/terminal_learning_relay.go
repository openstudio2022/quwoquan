package runruntime

import (
	"context"
	"errors"
	"strings"
	"time"
)

const terminalEventClaimLease = time.Minute

var ErrTerminalEventClaimLost = errors.New(
	"assistant run terminal event claim lost",
)

// TerminalEvent is the immutable, typed subscription source emitted in the
// same transaction as the AssistantRun terminal snapshot and journal event.
type TerminalEvent struct {
	EventID    string
	RunID      string
	UserID     string
	PersonaID  string
	SessionID  string
	DomainID   string
	Outcome    string
	OccurredAt time.Time
}

type TerminalEventStore interface {
	ClaimPendingTerminalEvents(
		context.Context,
		string,
		time.Duration,
		int,
	) ([]TerminalEvent, error)
	MarkTerminalEventProcessed(context.Context, string, string, time.Time) error
	ReleaseTerminalEventClaim(context.Context, string, string) error
}

type ServiceScorecardCommand struct {
	EventID        string
	AssistantRunID string
	DomainID       string
	MetricID       string
	MetricValue    float64
	MetricSource   string
	OccurredAt     time.Time
}

type ServiceScorecardAppender interface {
	AppendServiceScorecard(context.Context, ServiceScorecardCommand) error
}

type ServiceScorecardAppenderFunc func(
	context.Context,
	ServiceScorecardCommand,
) error

func (appendFact ServiceScorecardAppenderFunc) AppendServiceScorecard(
	ctx context.Context,
	command ServiceScorecardCommand,
) error {
	return appendFact(ctx, command)
}

// TerminalLearningRelay consumes the AssistantRun-owned transactional outbox
// and appends a service scorecard through the AssistantLearningFact facade.
// A stable event identity makes replay after a crash safe without dual writes.
type TerminalLearningRelay struct {
	store     TerminalEventStore
	appender  ServiceScorecardAppender
	ownerID   string
	interval  time.Duration
	batchSize int
	now       func() time.Time
}

func NewTerminalLearningRelay(
	store TerminalEventStore,
	appender ServiceScorecardAppender,
	ownerID string,
	interval time.Duration,
	batchSize int,
) *TerminalLearningRelay {
	ownerID = strings.TrimSpace(ownerID)
	if store == nil || appender == nil || ownerID == "" || interval <= 0 {
		panic("assistant run terminal learning relay dependencies are required")
	}
	if batchSize <= 0 {
		batchSize = 128
	}
	return &TerminalLearningRelay{
		store:     store,
		appender:  appender,
		ownerID:   ownerID,
		interval:  interval,
		batchSize: batchSize,
		now:       time.Now,
	}
}

func (relay *TerminalLearningRelay) Run(ctx context.Context) {
	if relay == nil {
		return
	}
	_, _ = relay.FlushOnce(ctx)
	ticker := time.NewTicker(relay.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			_, _ = relay.FlushOnce(ctx)
		}
	}
}

func (relay *TerminalLearningRelay) FlushOnce(ctx context.Context) (int, error) {
	events, err := relay.store.ClaimPendingTerminalEvents(
		ctx,
		relay.ownerID,
		terminalEventClaimLease,
		relay.batchSize,
	)
	if err != nil {
		return 0, err
	}
	processed := 0
	for index, event := range events {
		value := 0.0
		if event.Outcome == "completed" {
			value = 1.0
		}
		if err := relay.appender.AppendServiceScorecard(
			ctx,
			ServiceScorecardCommand{
				EventID:        "turn:" + event.RunID + ":completion",
				AssistantRunID: event.RunID,
				DomainID:       event.DomainID,
				MetricID:       "turn_completion",
				MetricValue:    value,
				MetricSource:   "service_auto",
				OccurredAt:     event.OccurredAt,
			},
		); err != nil {
			return processed, errors.Join(
				err,
				relay.releaseClaims(ctx, events[index:]),
			)
		}
		if err := relay.store.MarkTerminalEventProcessed(
			ctx,
			event.EventID,
			relay.ownerID,
			relay.now().UTC(),
		); err != nil {
			return processed, errors.Join(
				err,
				relay.releaseClaims(ctx, events[index:]),
			)
		}
		processed++
	}
	return processed, nil
}

func (relay *TerminalLearningRelay) releaseClaims(
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
