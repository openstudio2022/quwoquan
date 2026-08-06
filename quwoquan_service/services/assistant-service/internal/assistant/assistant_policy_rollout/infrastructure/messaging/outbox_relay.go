// Package messaging delivers AssistantPolicyRollout audit events. It owns the
// rollout adapter independently from AssistantPolicyRelease so the two
// aggregates cannot acquire each other's private persistence authority.
package messaging

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/ports"
)

const (
	PolicyRolloutAuditStream          = "events.assistant.policy_audit"
	PolicyRolloutAuditStreamRetention = 7 * 24 * time.Hour
	policyRolloutClaimLease           = time.Minute
)

type DurablePublisher interface {
	AppendDurable(context.Context, runtimemessaging.DurableMessage) (string, error)
	SetDurableRetention(context.Context, string, time.Duration) error
}

type OutboxRelay struct {
	store     ports.TransactionalOutbox
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

type RelayOption func(*OutboxRelay)

// WithRelayClock makes retry scheduling deterministic in contract tests while
// production continues to use the process UTC clock.
func WithRelayClock(now func() time.Time) RelayOption {
	return func(relay *OutboxRelay) {
		if now != nil {
			relay.now = now
		}
	}
}

func NewOutboxRelay(
	store ports.TransactionalOutbox,
	publisher DurablePublisher,
	interval time.Duration,
	batchSize int,
	logger *slog.Logger,
	options ...RelayOption,
) (*OutboxRelay, error) {
	if store == nil || publisher == nil || interval <= 0 {
		return nil, errors.New("policy rollout outbox store, publisher, and interval are required")
	}
	if batchSize <= 0 {
		batchSize = 128
	}
	if logger == nil {
		logger = slog.Default()
	}
	relay := &OutboxRelay{
		store: store, publisher: publisher, interval: interval, batchSize: batchSize,
		logger: logger, ownerID: "assistant-policy-rollout-" + uuid.NewString(), now: time.Now,
	}
	for _, option := range options {
		if option != nil {
			option(relay)
		}
	}
	return relay, nil
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
	published := 0
	for published < relay.batchSize {
		now := relay.now().UTC()
		event, found, err := relay.store.ClaimPendingOutbox(
			ctx, relay.ownerID, now, policyRolloutClaimLease,
		)
		if err != nil {
			return published, err
		}
		if !found {
			return published, nil
		}
		if err := validateRolloutEvent(event); err != nil {
			return published, errors.Join(
				err,
				relay.scheduleRetry(ctx, event, "invalid_event"),
			)
		}
		reference, err := relay.publisher.AppendDurable(ctx, runtimemessaging.DurableMessage{
			Stream: PolicyRolloutAuditStream,
			Fields: runtimemessaging.DurableFieldsFromMap(map[string]string{
				"eventId": event.EventID, "eventName": event.EventType,
				"aggregateType": "AssistantPolicyRollout", "aggregateId": event.AggregateID,
				"aggregateRevision": strconv.Itoa(event.AggregateVersion),
				"occurredAt":        event.OccurredAt.UTC().Format(time.RFC3339Nano),
				"payload":           string(event.Payload),
			}),
		})
		if err != nil {
			return published, errors.Join(
				err,
				relay.scheduleRetry(ctx, event, "publish_failed"),
			)
		}
		if err := relay.publisher.SetDurableRetention(
			ctx, PolicyRolloutAuditStream, PolicyRolloutAuditStreamRetention,
		); err != nil {
			return published, errors.Join(
				err,
				relay.scheduleRetry(ctx, event, "retention_failed"),
			)
		}
		if err := relay.store.MarkOutboxPublished(
			ctx, event.EventID, relay.ownerID, reference, relay.now().UTC(),
		); err != nil {
			return published, errors.Join(
				err,
				relay.scheduleRetry(ctx, event, "checkpoint_failed"),
			)
		}
		published++
	}
	return published, nil
}

func (relay *OutboxRelay) Healthy(_ context.Context, maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	relay.healthMu.RLock()
	lastScan, lastFailure := relay.lastSuccessfulScan, relay.lastFailure
	relay.healthMu.RUnlock()
	if lastFailure != nil {
		return fmt.Errorf("assistant policy rollout outbox relay unhealthy: %w", lastFailure)
	}
	if lastScan.IsZero() || relay.now().UTC().Sub(lastScan) > maxStaleness {
		return errors.New("assistant policy rollout outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) flushAndObserve(ctx context.Context) {
	_, err := relay.FlushOnce(ctx)
	relay.healthMu.Lock()
	defer relay.healthMu.Unlock()
	if err != nil {
		relay.lastFailure = err
		relay.logger.ErrorContext(ctx, "assistant policy rollout outbox relay failed", "err", err)
		return
	}
	relay.lastSuccessfulScan = relay.now().UTC()
	relay.lastFailure = nil
}

func (relay *OutboxRelay) scheduleRetry(
	ctx context.Context,
	event ports.OutboxEvent,
	failureCode string,
) error {
	failedAt := relay.now().UTC()
	return relay.store.ScheduleOutboxRetry(
		ctx,
		event.EventID,
		relay.ownerID,
		failedAt,
		failedAt.Add(policyRolloutRetryDelay(event.AttemptCount)),
		failureCode,
	)
}

func validateRolloutEvent(event ports.OutboxEvent) error {
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 ||
		event.OccurredAt.IsZero() || len(event.Payload) == 0 || event.AttemptCount <= 0 {
		return errors.New("assistant policy rollout outbox event is incomplete")
	}
	switch event.EventType {
	case "AssistantPolicyRolloutActivated", "AssistantPolicyRolloutRolledBack":
	default:
		return errors.New("assistant policy rollout outbox event type is unknown")
	}
	if err := validateExactRolloutPayloadKeys(event.Payload); err != nil {
		return err
	}
	var payload struct {
		PolicyID    string                   `json:"policyId"`
		Revision    int                      `json:"revision"`
		Status      string                   `json:"status"`
		Assignments []model.CohortAssignment `json:"assignments"`
		ActivatedAt time.Time                `json:"activatedAt"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode assistant policy rollout payload: %w", err)
	}
	if payload.PolicyID != event.AggregateID ||
		payload.Revision != event.AggregateVersion ||
		payload.Status != "active" || len(payload.Assignments) == 0 ||
		payload.ActivatedAt.IsZero() || !payload.ActivatedAt.Equal(event.OccurredAt) {
		return errors.New("assistant policy rollout payload identity does not match its envelope")
	}
	cohorts := make(map[string]struct{}, len(payload.Assignments))
	for _, assignment := range payload.Assignments {
		cohort := strings.TrimSpace(assignment.Cohort)
		if cohort == "" || strings.TrimSpace(assignment.ReleaseDigest) == "" {
			return errors.New("assistant policy rollout assignment is incomplete")
		}
		if _, duplicate := cohorts[cohort]; duplicate {
			return errors.New("assistant policy rollout assignment cohort is duplicated")
		}
		cohorts[cohort] = struct{}{}
	}
	return nil
}

func validateExactRolloutPayloadKeys(payload []byte) error {
	expected := map[string]struct{}{
		"policyId": {}, "revision": {}, "status": {}, "assignments": {}, "activatedAt": {},
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return errors.New("assistant policy rollout payload must be one JSON object")
	}
	seen := make(map[string]struct{}, len(expected))
	for decoder.More() {
		keyToken, err := decoder.Token()
		key, ok := keyToken.(string)
		if err != nil || !ok {
			return errors.New("assistant policy rollout payload key is invalid")
		}
		if _, allowed := expected[key]; !allowed {
			return fmt.Errorf("assistant policy rollout payload has undeclared key %s", key)
		}
		if _, duplicate := seen[key]; duplicate {
			return fmt.Errorf("assistant policy rollout payload duplicates key %s", key)
		}
		seen[key] = struct{}{}
		var value json.RawMessage
		if err := decoder.Decode(&value); err != nil {
			return fmt.Errorf("decode assistant policy rollout payload key %s: %w", key, err)
		}
	}
	if _, err := decoder.Token(); err != nil || len(seen) != len(expected) {
		return errors.New("assistant policy rollout payload omits a declared key")
	}
	var trailing json.RawMessage
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("assistant policy rollout payload has trailing content")
	}
	return nil
}

func policyRolloutRetryDelay(attempt int) time.Duration {
	if attempt < 1 {
		attempt = 1
	}
	if attempt > 6 {
		attempt = 6
	}
	return time.Second * time.Duration(1<<(attempt-1))
}
