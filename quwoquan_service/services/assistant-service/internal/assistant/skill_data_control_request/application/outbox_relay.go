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

	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/ports"
)

const dataControlOutboxClaimLease = 30 * time.Second

type OutboxEventPublisher interface {
	PublishSkillDataControl(context.Context, ports.OutboxEvent) error
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
		return nil, errors.New("skill data control outbox and publisher are required")
	}
	return &OutboxRelay{
		outbox: outbox, publisher: publisher,
		ownerID: "skill-data-control-relay-" + uuid.NewString(), now: time.Now,
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
			ctx, relay.ownerID, now, dataControlOutboxClaimLease,
		)
		if err != nil {
			relay.recordFailure(err)
			return published, err
		}
		if !found {
			relay.recordSuccessfulScan(now, published > 0)
			return published, nil
		}
		if err := validateDataControlOutboxEvent(event); err != nil {
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
		if err := relay.publisher.PublishSkillDataControl(ctx, event); err != nil {
			failedAt := relay.now().UTC()
			retryErr := relay.outbox.ScheduleOutboxRetry(
				ctx, event.EventID, relay.ownerID,
				failedAt, failedAt.Add(outboxRetryDelay(event.AttemptCount)), "publish_failed",
			)
			wrapped := fmt.Errorf("publish data control event %s: %w", event.EventID, err)
			if retryErr != nil {
				wrapped = errors.Join(wrapped, retryErr)
			}
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		if err := relay.outbox.MarkOutboxPublished(
			ctx, event.EventID, relay.ownerID, relay.now().UTC(),
		); err != nil {
			wrapped := fmt.Errorf("checkpoint data control event %s: %w", event.EventID, err)
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
		return fmt.Errorf("skill data control outbox relay unhealthy: %w", lastFailure)
	}
	if lastScan.IsZero() || relay.now().UTC().Sub(lastScan) > maxStaleness {
		return errors.New("skill data control outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) drainAndObserve(ctx context.Context) {
	if _, err := relay.Drain(ctx, 100); err != nil && ctx.Err() == nil {
		slog.ErrorContext(ctx, "skill data control outbox drain failed", "err", err)
	}
}

func validateDataControlOutboxEvent(event ports.OutboxEvent) error {
	expectedKeys := map[string][]string{
		model.EventRequested: {
			"requestId", "accountId", "skillId", "requestedActions", "status", "revision", "createdAt",
		},
		model.EventConfirmed: {
			"requestId", "accountId", "skillId", "status", "confirmedAt", "revision", "updatedAt",
		},
		model.EventCompleted: {
			"requestId", "accountId", "skillId", "completedActions", "status", "completedAt", "revision", "updatedAt",
		},
		model.EventCancelled: {
			"requestId", "accountId", "skillId", "status", "completedAt", "revision", "updatedAt",
		},
		model.EventFailed: {
			"requestId", "accountId", "skillId", "completedActions", "status", "failedAction", "failureCode", "revision", "updatedAt",
		},
	}
	keys, known := expectedKeys[event.EventType]
	if !known {
		return errors.New("unknown skill data control event")
	}
	if err := validateExactDataControlPayloadKeys(event.Payload, keys); err != nil {
		return err
	}
	var payload struct {
		RequestID        string     `json:"requestId"`
		AccountID        string     `json:"accountId"`
		SkillID          string     `json:"skillId"`
		RequestedActions []string   `json:"requestedActions"`
		CompletedActions []string   `json:"completedActions"`
		Status           string     `json:"status"`
		FailedAction     string     `json:"failedAction"`
		FailureCode      string     `json:"failureCode"`
		ConfirmedAt      *time.Time `json:"confirmedAt"`
		CompletedAt      *time.Time `json:"completedAt"`
		CreatedAt        time.Time  `json:"createdAt"`
		UpdatedAt        time.Time  `json:"updatedAt"`
		Revision         int64      `json:"revision"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode data control outbox payload: %w", err)
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.AggregateID) == "" ||
		event.AggregateVersion <= 0 || event.OccurredAt.IsZero() ||
		strings.TrimSpace(payload.RequestID) == "" || payload.RequestID != event.AggregateID ||
		payload.Revision != event.AggregateVersion || strings.TrimSpace(payload.AccountID) == "" ||
		strings.TrimSpace(payload.SkillID) == "" || strings.TrimSpace(payload.Status) == "" {
		return errors.New("skill data control outbox event is incomplete")
	}
	switch event.EventType {
	case model.EventRequested:
		if payload.Status != model.StatusPendingConfirmation ||
			!validDataControlActions(payload.RequestedActions, false) ||
			payload.CreatedAt.IsZero() || !payload.CreatedAt.Equal(event.OccurredAt) {
			return errors.New("requested data control event is incomplete")
		}
	case model.EventConfirmed:
		if payload.Status != model.StatusExecuting || payload.ConfirmedAt == nil ||
			payload.ConfirmedAt.IsZero() || payload.UpdatedAt.IsZero() ||
			!payload.ConfirmedAt.Equal(event.OccurredAt) ||
			!payload.UpdatedAt.Equal(event.OccurredAt) {
			return errors.New("confirmed data control event is incomplete")
		}
	case model.EventCompleted:
		if payload.Status != model.StatusCompleted ||
			!validDataControlActions(payload.CompletedActions, false) ||
			payload.CompletedAt == nil ||
			payload.CompletedAt.IsZero() || payload.UpdatedAt.IsZero() ||
			!payload.CompletedAt.Equal(event.OccurredAt) ||
			!payload.UpdatedAt.Equal(event.OccurredAt) {
			return errors.New("completed data control event is incomplete")
		}
	case model.EventCancelled:
		if payload.Status != model.StatusCancelled || payload.CompletedAt == nil ||
			payload.CompletedAt.IsZero() || payload.UpdatedAt.IsZero() ||
			!payload.CompletedAt.Equal(event.OccurredAt) ||
			!payload.UpdatedAt.Equal(event.OccurredAt) {
			return errors.New("cancelled data control event is incomplete")
		}
	case model.EventFailed:
		if payload.Status != model.StatusFailed ||
			!validDataControlActions(payload.CompletedActions, true) ||
			strings.TrimSpace(payload.FailedAction) == "" ||
			strings.TrimSpace(payload.FailureCode) == "" ||
			payload.UpdatedAt.IsZero() || !payload.UpdatedAt.Equal(event.OccurredAt) {
			return errors.New("failed data control event is incomplete")
		}
	}
	return nil
}

func validDataControlActions(actions []string, allowEmpty bool) bool {
	if actions == nil || (!allowEmpty && len(actions) == 0) {
		return false
	}
	seen := make(map[string]struct{}, len(actions))
	for _, action := range actions {
		action = strings.TrimSpace(action)
		if action == "" {
			return false
		}
		if _, duplicate := seen[action]; duplicate {
			return false
		}
		seen[action] = struct{}{}
	}
	return true
}

func validateExactDataControlPayloadKeys(payload []byte, keys []string) error {
	expected := make(map[string]struct{}, len(keys))
	for _, key := range keys {
		expected[key] = struct{}{}
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return errors.New("skill data control payload must be one JSON object")
	}
	seen := make(map[string]struct{}, len(expected))
	for decoder.More() {
		keyToken, err := decoder.Token()
		key, ok := keyToken.(string)
		if err != nil || !ok {
			return errors.New("skill data control payload key is invalid")
		}
		if _, allowed := expected[key]; !allowed {
			return fmt.Errorf("skill data control payload has undeclared key %s", key)
		}
		if _, duplicate := seen[key]; duplicate {
			return fmt.Errorf("skill data control payload duplicates key %s", key)
		}
		seen[key] = struct{}{}
		var value json.RawMessage
		if err := decoder.Decode(&value); err != nil {
			return fmt.Errorf("decode skill data control payload key %s: %w", key, err)
		}
	}
	if _, err := decoder.Token(); err != nil || len(seen) != len(expected) {
		return errors.New("skill data control payload omits a declared key")
	}
	var trailing json.RawMessage
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("skill data control payload has trailing content")
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
