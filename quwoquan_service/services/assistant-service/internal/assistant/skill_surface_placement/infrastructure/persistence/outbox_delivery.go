package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/ports"
)

var _ ports.TransactionalOutbox = (*PgStore)(nil)

func (store *PgStore) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	now time.Time,
	lease time.Duration,
) (ports.OutboxEvent, bool, error) {
	ownerID = strings.TrimSpace(ownerID)
	now = now.UTC()
	if store == nil || store.pool == nil || ownerID == "" || now.IsZero() || lease <= 0 {
		return ports.OutboxEvent{}, false, model.ErrStorageUnavailable
	}
	var event ports.OutboxEvent
	err := store.pool.QueryRow(ctx, `
WITH head AS (
  SELECT event_id
  FROM skill_surface_placement_outbox
  WHERE dispatched_at IS NULL
  ORDER BY occurred_at ASC, event_id ASC
  LIMIT 1
), claimed AS (
  UPDATE skill_surface_placement_outbox AS target
  SET claim_owner=$1, claimed_at=$2, attempt_count=attempt_count+1
  FROM head
  WHERE target.event_id=head.event_id
    AND target.dispatched_at IS NULL
    AND target.next_attempt_at <= $2
    AND (target.claim_owner IS NULL OR target.claimed_at <= $3)
  RETURNING target.event_id, target.event_type, target.aggregate_id,
            target.aggregate_revision, target.payload_json, target.occurred_at,
            target.attempt_count
)
SELECT event_id, event_type, aggregate_id, aggregate_revision,
       payload_json, occurred_at, attempt_count
FROM claimed`, ownerID, now, now.Add(-lease)).Scan(
		&event.EventID,
		&event.EventType,
		&event.AggregateID,
		&event.AggregateVersion,
		&event.Payload,
		&event.OccurredAt,
		&event.AttemptCount,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return ports.OutboxEvent{}, false, nil
	}
	if err != nil {
		return ports.OutboxEvent{}, false, unavailable("claim placement outbox", err)
	}
	return event, true, nil
}

func (store *PgStore) MarkOutboxPublished(
	ctx context.Context,
	eventID string,
	ownerID string,
	publishedAt time.Time,
) error {
	tag, err := store.pool.Exec(ctx, `
UPDATE skill_surface_placement_outbox
SET dispatched_at=$3, claim_owner=NULL, claimed_at=NULL,
    next_attempt_at=$3, last_error_code=NULL
WHERE event_id=$1 AND claim_owner=$2 AND dispatched_at IS NULL`,
		strings.TrimSpace(eventID), strings.TrimSpace(ownerID), publishedAt.UTC(),
	)
	if err != nil {
		return unavailable("mark placement outbox published", err)
	}
	if tag.RowsAffected() != 1 {
		return ports.ErrOutboxClaimLost
	}
	return nil
}

func (store *PgStore) ScheduleOutboxRetry(
	ctx context.Context,
	eventID string,
	ownerID string,
	nextAttemptAt time.Time,
	failureCode string,
) error {
	tag, err := store.pool.Exec(ctx, `
UPDATE skill_surface_placement_outbox
SET next_attempt_at=$3, last_error_code=$4,
    claim_owner=NULL, claimed_at=NULL
WHERE event_id=$1 AND claim_owner=$2 AND dispatched_at IS NULL`,
		strings.TrimSpace(eventID), strings.TrimSpace(ownerID), nextAttemptAt.UTC(),
		boundedOutboxFailureCode(failureCode),
	)
	if err != nil {
		return unavailable("schedule placement outbox retry", err)
	}
	if tag.RowsAffected() != 1 {
		return ports.ErrOutboxClaimLost
	}
	return nil
}

func boundedOutboxFailureCode(value string) string {
	value = strings.TrimSpace(value)
	if value == "" || len(value) > 64 {
		return "delivery_failed"
	}
	return value
}
