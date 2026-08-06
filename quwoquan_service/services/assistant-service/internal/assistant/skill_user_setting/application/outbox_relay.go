package application

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/ports"
)

const settingOutboxClaimLease = 30 * time.Second

type OutboxEventPublisher interface {
	PublishSkillUserSetting(context.Context, ports.OutboxEvent) error
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
		return nil, errors.New("skill user setting outbox and publisher are required")
	}
	return &OutboxRelay{
		outbox: outbox, publisher: publisher,
		ownerID: "skill-user-setting-relay-" + uuid.NewString(), now: time.Now,
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
			ctx, relay.ownerID, now, settingOutboxClaimLease,
		)
		if err != nil {
			relay.recordFailure(err)
			return published, err
		}
		if !found {
			relay.recordSuccessfulScan(now, published > 0)
			return published, nil
		}
		if err := validateSettingOutboxEvent(event); err != nil {
			retryErr := relay.outbox.ScheduleOutboxRetry(
				ctx, event.EventID, relay.ownerID,
				now.Add(outboxRetryDelay(event.AttemptCount)), "invalid_event",
			)
			if retryErr != nil {
				err = errors.Join(err, retryErr)
			}
			relay.recordFailure(err)
			return published, err
		}
		if err := relay.publisher.PublishSkillUserSetting(ctx, event); err != nil {
			retryErr := relay.outbox.ScheduleOutboxRetry(
				ctx, event.EventID, relay.ownerID,
				now.Add(outboxRetryDelay(event.AttemptCount)), "publish_failed",
			)
			wrapped := fmt.Errorf("publish setting event %s: %w", event.EventID, err)
			if retryErr != nil {
				wrapped = errors.Join(wrapped, retryErr)
			}
			relay.recordFailure(wrapped)
			return published, wrapped
		}
		if err := relay.outbox.MarkOutboxPublished(
			ctx, event.EventID, relay.ownerID, relay.now().UTC(),
		); err != nil {
			wrapped := fmt.Errorf("checkpoint setting event %s: %w", event.EventID, err)
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
		return fmt.Errorf("skill user setting outbox relay unhealthy: %w", lastFailure)
	}
	if lastScan.IsZero() || relay.now().UTC().Sub(lastScan) > maxStaleness {
		return errors.New("skill user setting outbox relay heartbeat is stale")
	}
	return nil
}

func (relay *OutboxRelay) drainAndObserve(ctx context.Context) {
	if _, err := relay.Drain(ctx, 100); err != nil && ctx.Err() == nil {
		slog.ErrorContext(ctx, "skill user setting outbox drain failed", "err", err)
	}
}

func validateSettingOutboxEvent(event ports.OutboxEvent) error {
	var payload struct {
		ID                        string   `json:"id"`
		AccountID                 string   `json:"accountId"`
		SkillID                   string   `json:"skillId"`
		Status                    string   `json:"status"`
		ConfigurationSchemaDigest string   `json:"configurationSchemaDigest"`
		MemoryPolicy              string   `json:"memoryPolicy"`
		ConnectorConnectionRefs   []string `json:"connectorConnectionRefs"`
		Revision                  int64    `json:"revision"`
		UpdatedAt                 string   `json:"updatedAt"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode setting outbox payload: %w", err)
	}
	if event.EventType != model.EventChanged || strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.AggregateID) == "" || event.AggregateVersion <= 0 ||
		event.OccurredAt.IsZero() || strings.TrimSpace(payload.ID) == "" ||
		payload.ID != event.AggregateID || payload.Revision != event.AggregateVersion ||
		strings.TrimSpace(payload.AccountID) == "" || strings.TrimSpace(payload.SkillID) == "" ||
		strings.TrimSpace(payload.Status) == "" || strings.TrimSpace(payload.ConfigurationSchemaDigest) == "" ||
		strings.TrimSpace(payload.MemoryPolicy) == "" || strings.TrimSpace(payload.UpdatedAt) == "" {
		return errors.New("skill user setting outbox event is incomplete")
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
