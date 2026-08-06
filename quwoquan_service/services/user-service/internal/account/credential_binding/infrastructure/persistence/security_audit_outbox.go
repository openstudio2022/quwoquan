package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"

	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
)

// ClaimPendingOutbox 用 next_attempt_at 作为单记录租约代次。候选选择与租约推进在
// 同一 SQL statement 内完成，进程崩溃后到期记录可被重新认领。
func (store *PostgresStore) ClaimPendingOutbox(
	ctx context.Context,
	now time.Time,
	lease time.Duration,
) (bindingports.SecurityAuditEvent, bool, error) {
	if store == nil || store.pool == nil || now.IsZero() || lease <= 0 {
		return bindingports.SecurityAuditEvent{}, false, errors.New(
			"CredentialBinding audit outbox claim is invalid",
		)
	}
	now = now.UTC()
	var event bindingports.SecurityAuditEvent
	err := store.pool.QueryRow(ctx, `
WITH candidate AS (
  SELECT event_id
  FROM credential_bindings_outbox
  WHERE published_at IS NULL AND next_attempt_at <= $1
  ORDER BY occurred_at, event_id
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
UPDATE credential_bindings_outbox AS outbox
SET next_attempt_at=$2,
    retry_count=outbox.retry_count+1,
    last_error=''
FROM candidate
WHERE outbox.event_id=candidate.event_id
RETURNING outbox.event_id, outbox.aggregate_id, outbox.aggregate_version,
          outbox.event_type, outbox.payload_json, outbox.occurred_at,
          outbox.retry_count, outbox.next_attempt_at`, now, now.Add(lease)).Scan(
		&event.EventID,
		&event.AggregateID,
		&event.AggregateVersion,
		&event.EventType,
		&event.PayloadJSON,
		&event.OccurredAt,
		&event.AttemptCount,
		&event.ClaimUntil,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return bindingports.SecurityAuditEvent{}, false, nil
	}
	if err != nil {
		return bindingports.SecurityAuditEvent{}, false, fmt.Errorf(
			"claim CredentialBinding audit outbox: %w",
			err,
		)
	}
	return event, true, nil
}

func (store *PostgresStore) MarkOutboxPublished(
	ctx context.Context,
	eventID string,
	claimUntil time.Time,
	publishedAt time.Time,
) error {
	result, err := store.pool.Exec(ctx, `
UPDATE credential_bindings_outbox
SET published_at=$2, next_attempt_at=$2, last_error=''
WHERE event_id=$1 AND published_at IS NULL AND next_attempt_at=$3`,
		strings.TrimSpace(eventID), publishedAt.UTC(), claimUntil.UTC())
	if err != nil {
		return fmt.Errorf("mark CredentialBinding audit published: %w", err)
	}
	if result.RowsAffected() != 1 {
		return errors.New("CredentialBinding audit outbox checkpoint was lost")
	}
	return nil
}

func (store *PostgresStore) ScheduleOutboxRetry(
	ctx context.Context,
	eventID string,
	claimUntil time.Time,
	nextAttemptAt time.Time,
	failureDigest string,
) error {
	failureDigest = strings.TrimSpace(failureDigest)
	if len(failureDigest) > 96 {
		failureDigest = failureDigest[:96]
	}
	result, err := store.pool.Exec(ctx, `
UPDATE credential_bindings_outbox
SET next_attempt_at=$2, last_error=$3
WHERE event_id=$1 AND published_at IS NULL AND next_attempt_at=$4`,
		strings.TrimSpace(eventID), nextAttemptAt.UTC(), failureDigest, claimUntil.UTC())
	if err != nil {
		return fmt.Errorf("schedule CredentialBinding audit retry: %w", err)
	}
	if result.RowsAffected() != 1 {
		return errors.New("CredentialBinding audit outbox retry lease was lost")
	}
	return nil
}

var _ bindingports.SecurityAuditOutbox = (*PostgresStore)(nil)
