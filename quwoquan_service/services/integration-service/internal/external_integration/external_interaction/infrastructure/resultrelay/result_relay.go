package resultrelay

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/reliabletask"
)

const (
	ResultStream          = "events.integration.external_interaction"
	ResultStreamRetention = 7 * 24 * time.Hour

	pollInterval = 500 * time.Millisecond
	maxBackoff   = 30 * time.Second
	leaseTTL     = 15 * time.Second
)

type OutboxStore interface {
	LeaseNextExternalInteractionResultOutbox(
		context.Context,
		string,
		time.Duration,
	) (reliabletask.ExternalInteractionResultOutboxRecord, bool, error)
	AcknowledgeExternalInteractionResultOutbox(
		context.Context,
		string,
		string,
	) (bool, error)
	ReleaseExternalInteractionResultOutboxLease(
		context.Context,
		string,
		string,
	) error
}

type Transport interface {
	AppendDurable(
		context.Context,
		runtimemessaging.DurableMessage,
	) (string, error)
	SetDurableRetention(context.Context, string, time.Duration) error
}

// Relay is the only integration component allowed to emit
// ExternalInteractionResultReported. It consumes no provider credentials and
// never invokes a provider: an unacknowledged append only replays transport.
type Relay struct {
	store     OutboxStore
	transport Transport
	logger    *slog.Logger
	relayID   string

	healthMu sync.RWMutex
	lastScan time.Time
	lastErr  error
}

func New(
	store OutboxStore,
	transport Transport,
	logger *slog.Logger,
) (*Relay, error) {
	if store == nil {
		return nil, fmt.Errorf("external interaction result relay requires an outbox store")
	}
	if transport == nil {
		return nil, fmt.Errorf("external interaction result relay requires a message transport")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Relay{
		store:     store,
		transport: transport,
		logger:    logger,
		relayID:   "integration-result-relay-" + bson.NewObjectID().Hex(),
	}, nil
}

func (relay *Relay) ProcessOnce(ctx context.Context) (bool, error) {
	if relay == nil || relay.store == nil || relay.transport == nil {
		return false, fmt.Errorf("external interaction result relay is not configured")
	}
	record, found, err := relay.store.LeaseNextExternalInteractionResultOutbox(
		ctx,
		relay.relayID,
		leaseTTL,
	)
	if err != nil {
		relay.recordFailure(err)
		return false, err
	}
	if !found {
		relay.recordSuccess()
		return false, nil
	}
	if err := validateRecord(record); err != nil {
		_ = relay.store.ReleaseExternalInteractionResultOutboxLease(
			ctx,
			record.EventID,
			relay.relayID,
		)
		relay.recordFailure(err)
		return true, err
	}
	if _, err := relay.transport.AppendDurable(
		ctx,
		runtimemessaging.DurableMessage{
			Stream: ResultStream,
			Fields: resultFields(record),
		},
	); err != nil {
		releaseErr := relay.store.ReleaseExternalInteractionResultOutboxLease(
			ctx,
			record.EventID,
			relay.relayID,
		)
		if releaseErr != nil {
			err = fmt.Errorf("%w; release result outbox lease: %v", err, releaseErr)
		}
		relay.recordFailure(err)
		return true, err
	}
	if err := relay.transport.SetDurableRetention(
		ctx,
		ResultStream,
		ResultStreamRetention,
	); err != nil {
		relay.recordFailure(err)
		return true, fmt.Errorf("set external interaction result retention: %w", err)
	}
	acknowledged, err := relay.store.AcknowledgeExternalInteractionResultOutbox(
		ctx,
		record.EventID,
		relay.relayID,
	)
	if err != nil {
		relay.recordFailure(err)
		return true, fmt.Errorf("acknowledge external interaction result outbox: %w", err)
	}
	if !acknowledged {
		err := fmt.Errorf("external interaction result outbox relay lease lost")
		relay.recordFailure(err)
		return true, err
	}
	relay.recordSuccess()
	return true, nil
}

func (relay *Relay) Run(ctx context.Context) {
	retryDelay := pollInterval
	for {
		didWork, err := relay.ProcessOnce(ctx)
		if err != nil {
			if ctx.Err() == nil {
				relay.logger.ErrorContext(
					ctx,
					"external interaction result relay failed",
					slog.String("err", err.Error()),
				)
			}
			if !wait(ctx, retryDelay) {
				return
			}
			retryDelay = min(retryDelay*2, maxBackoff)
			continue
		}
		retryDelay = pollInterval
		if didWork {
			continue
		}
		if !wait(ctx, pollInterval) {
			return
		}
	}
}

func (relay *Relay) Healthy(
	_ context.Context,
	maxStaleness time.Duration,
) error {
	if relay == nil {
		return fmt.Errorf("external interaction result relay is not configured")
	}
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.healthMu.RLock()
	lastScan := relay.lastScan
	lastErr := relay.lastErr
	relay.healthMu.RUnlock()
	if lastErr != nil {
		return fmt.Errorf("external interaction result relay unhealthy: %w", lastErr)
	}
	if lastScan.IsZero() || time.Since(lastScan) > maxStaleness {
		return fmt.Errorf("external interaction result relay heartbeat is stale")
	}
	return nil
}

func validateRecord(record reliabletask.ExternalInteractionResultOutboxRecord) error {
	if record.EventID == "" ||
		record.RequestID == "" ||
		record.Operation == "" ||
		record.ResultStatus == "" ||
		record.Provider == "" ||
		record.ProviderRequestDigest == "" ||
		record.RecoveryAction == "" ||
		record.OccurredAt.IsZero() {
		return fmt.Errorf("external interaction result outbox record is incomplete")
	}
	return nil
}

func resultFields(
	record reliabletask.ExternalInteractionResultOutboxRecord,
) []runtimemessaging.DurableField {
	return []runtimemessaging.DurableField{
		{Name: "eventType", Value: "ExternalInteractionResultReported"},
		{Name: "eventId", Value: record.EventID},
		{Name: "attemptId", Value: record.EventID},
		{Name: "requestId", Value: record.RequestID},
		{Name: "operation", Value: record.Operation},
		{Name: "status", Value: record.ResultStatus},
		{Name: "provider", Value: record.Provider},
		{Name: "providerRequestDigest", Value: record.ProviderRequestDigest},
		{Name: "normalizedError", Value: record.NormalizedError},
		{Name: "recoveryAction", Value: record.RecoveryAction},
		{Name: "occurredAt", Value: record.OccurredAt.UTC().Format(time.RFC3339Nano)},
	}
}

func (relay *Relay) recordSuccess() {
	relay.healthMu.Lock()
	relay.lastScan = time.Now().UTC()
	relay.lastErr = nil
	relay.healthMu.Unlock()
}

func (relay *Relay) recordFailure(err error) {
	relay.healthMu.Lock()
	relay.lastScan = time.Now().UTC()
	relay.lastErr = err
	relay.healthMu.Unlock()
}

func wait(ctx context.Context, delay time.Duration) bool {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-timer.C:
		return true
	}
}
