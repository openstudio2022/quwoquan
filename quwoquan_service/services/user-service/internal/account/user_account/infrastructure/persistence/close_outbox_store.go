package persistence

import (
	"context"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
)

const maxUserAccountOutboxTerminalFailurePageSize = 100

// UserAccountOutboxStore 持久化 UserAccount 生命周期事件的租约与投递结果。
type UserAccountOutboxStore struct {
	pool *pgxpool.Pool
}

func NewUserAccountOutboxStore(pool *pgxpool.Pool) (*UserAccountOutboxStore, error) {
	if pool == nil {
		return nil, errors.New("UserAccount outbox store requires PostgreSQL")
	}
	return &UserAccountOutboxStore{pool: pool}, nil
}

var _ accountports.UserAccountOutboxStore = (*UserAccountOutboxStore)(nil)

func (store *UserAccountOutboxStore) ClaimReady(
	ctx context.Context,
	owner string,
	now time.Time,
	lease time.Duration,
) (accountports.UserAccountOutboxEvent, bool, error) {
	owner = strings.TrimSpace(owner)
	if owner == "" || lease <= 0 {
		return accountports.UserAccountOutboxEvent{}, false, errors.New(
			"UserAccount outbox claim requires owner and positive lease",
		)
	}
	var event accountports.UserAccountOutboxEvent
	err := store.pool.QueryRow(ctx, `
WITH candidate AS (
  SELECT outbox.event_id
  FROM user_account_outbox AS outbox
  WHERE outbox.published_at IS NULL
    AND outbox.terminal_failure_at IS NULL
    AND outbox.next_attempt_at <= $2
    AND (outbox.lease_until IS NULL OR outbox.lease_until <= $2)
    -- 同一账号的较早事件（包括 terminal failure）必须先被发布或显式重放，
    -- 避免 Suspend/Restore 或 Closed 事件在重试期间被后来事件跨越。
    AND NOT EXISTS (
      SELECT 1
      FROM user_account_outbox AS earlier
      WHERE earlier.aggregate_id = outbox.aggregate_id
        AND earlier.published_at IS NULL
        AND (earlier.occurred_at, earlier.event_id) <
            (outbox.occurred_at, outbox.event_id)
    )
  ORDER BY outbox.occurred_at, outbox.event_id
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
UPDATE user_account_outbox AS outbox
SET lease_owner=$1,
    lease_until=$3,
    retry_count=retry_count+1
FROM candidate
WHERE outbox.event_id=candidate.event_id
RETURNING
  outbox.event_id,
  outbox.aggregate_id,
  outbox.aggregate_version,
  outbox.event_type,
  outbox.payload_json,
  outbox.occurred_at,
  outbox.retry_count`,
		owner,
		now.UTC(),
		now.UTC().Add(lease),
	).Scan(
		&event.EventID,
		&event.AccountID,
		&event.AccountVersion,
		&event.EventType,
		&event.PayloadJSON,
		&event.OccurredAt,
		&event.DeliveryAttempt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return accountports.UserAccountOutboxEvent{}, false, nil
	}
	if err != nil {
		return accountports.UserAccountOutboxEvent{}, false, fmt.Errorf(
			"claim UserAccount outbox: %w",
			err,
		)
	}
	return event, true, nil
}

func (store *UserAccountOutboxStore) MarkPublished(
	ctx context.Context,
	eventID string,
	owner string,
	publishedAt time.Time,
) error {
	tag, err := store.pool.Exec(ctx, `
UPDATE user_account_outbox
SET published_at=$3,
    lease_owner=NULL,
    lease_until=NULL,
    last_failure_code='',
    last_failure_digest='',
    last_failed_at=NULL
WHERE event_id=$1
  AND lease_owner=$2
  AND published_at IS NULL
  AND terminal_failure_at IS NULL`,
		eventID,
		owner,
		publishedAt.UTC(),
	)
	if err != nil {
		return fmt.Errorf("mark UserAccount outbox published: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return errors.New("UserAccount outbox lease lost before publish ack")
	}
	return nil
}

func (store *UserAccountOutboxStore) MarkFailed(
	ctx context.Context,
	eventID string,
	owner string,
	failedAt time.Time,
	nextAttemptAt time.Time,
	failure accountports.UserAccountOutboxFailure,
) error {
	failure, err := normalizeUserAccountOutboxFailure(failure)
	if err != nil {
		return err
	}
	tag, err := store.pool.Exec(ctx, `
UPDATE user_account_outbox
SET next_attempt_at=$3,
    last_failure_code=$4,
    last_failure_digest=$5,
    last_failed_at=$6,
    lease_owner=NULL,
    lease_until=NULL
WHERE event_id=$1
  AND lease_owner=$2
  AND published_at IS NULL
  AND terminal_failure_at IS NULL`,
		eventID,
		owner,
		nextAttemptAt.UTC(),
		failure.Code,
		failure.Digest,
		failedAt.UTC(),
	)
	if err != nil {
		return fmt.Errorf("mark UserAccount outbox failed: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return errors.New("UserAccount outbox lease lost before failure ack")
	}
	return nil
}

// MarkTerminalFailure atomically releases the source lease and persists a
// payload-free dead-letter record. The original outbox row remains terminal so
// later events for the same account cannot overtake it before an explicit replay.
func (store *UserAccountOutboxStore) MarkTerminalFailure(
	ctx context.Context,
	eventID string,
	owner string,
	failedAt time.Time,
	expiresAt time.Time,
	failure accountports.UserAccountOutboxFailure,
) error {
	failure, err := normalizeUserAccountOutboxFailure(failure)
	if err != nil {
		return err
	}
	failedAt = failedAt.UTC()
	expiresAt = expiresAt.UTC()
	if !expiresAt.After(failedAt) {
		return errors.New(
			"UserAccount outbox terminal failure expiry must follow failure time",
		)
	}

	var persistedEventID string
	err = store.pool.QueryRow(ctx, `
WITH terminal AS (
  UPDATE user_account_outbox
  SET terminal_failure_at=$3,
      last_failure_code=$5,
      last_failure_digest=$6,
      last_failed_at=$3,
      lease_owner=NULL,
      lease_until=NULL
  WHERE event_id=$1
    AND lease_owner=$2
    AND published_at IS NULL
    AND terminal_failure_at IS NULL
  RETURNING event_id, event_type, aggregate_version, retry_count
)
INSERT INTO user_account_outbox_dead_letters(
  event_id,
  event_type,
  aggregate_version,
  delivery_attempt,
  failure_code,
  failure_digest,
  failed_at,
  expires_at
)
SELECT
  event_id,
  event_type,
  aggregate_version,
  retry_count,
  $5,
  $6,
  $3,
  $4
FROM terminal
ON CONFLICT (event_id) DO UPDATE
SET event_type=EXCLUDED.event_type,
    aggregate_version=EXCLUDED.aggregate_version,
    delivery_attempt=EXCLUDED.delivery_attempt,
    failure_code=EXCLUDED.failure_code,
    failure_digest=EXCLUDED.failure_digest,
    failed_at=EXCLUDED.failed_at,
    expires_at=EXCLUDED.expires_at
RETURNING event_id`,
		eventID,
		owner,
		failedAt,
		expiresAt,
		failure.Code,
		failure.Digest,
	).Scan(&persistedEventID)
	if errors.Is(err, pgx.ErrNoRows) {
		return errors.New("UserAccount outbox lease lost before terminal failure ack")
	}
	if err != nil {
		return fmt.Errorf("mark UserAccount outbox terminal failure: %w", err)
	}
	return nil
}

// ListTerminalFailures returns only the payload-free, unexpired operator view.
func (store *UserAccountOutboxStore) ListTerminalFailures(
	ctx context.Context,
	now time.Time,
	limit int,
) ([]accountports.UserAccountOutboxTerminalFailure, error) {
	if limit <= 0 || limit > maxUserAccountOutboxTerminalFailurePageSize {
		return nil, errors.New("invalid UserAccount outbox terminal failure limit")
	}
	rows, err := store.pool.Query(ctx, `
SELECT
  event_id,
  event_type,
  aggregate_version,
  delivery_attempt,
  failure_code,
  failure_digest,
  failed_at,
  expires_at
FROM user_account_outbox_dead_letters
WHERE expires_at > $1
ORDER BY failed_at ASC, event_id ASC
LIMIT $2`,
		now.UTC(),
		limit,
	)
	if err != nil {
		return nil, fmt.Errorf("list UserAccount outbox terminal failures: %w", err)
	}
	defer rows.Close()

	result := make([]accountports.UserAccountOutboxTerminalFailure, 0)
	for rows.Next() {
		var record accountports.UserAccountOutboxTerminalFailure
		if err := rows.Scan(
			&record.EventID,
			&record.EventType,
			&record.AccountVersion,
			&record.DeliveryAttempt,
			&record.Failure.Code,
			&record.Failure.Digest,
			&record.FailedAt,
			&record.ExpiresAt,
		); err != nil {
			return nil, fmt.Errorf("scan UserAccount outbox terminal failure: %w", err)
		}
		result = append(result, record)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("read UserAccount outbox terminal failures: %w", err)
	}
	return result, nil
}

// ReplayTerminalFailure reopens the original durable event without changing
// its event ID. Downstream consumers therefore retain their existing dedupe
// semantics, and later events remain ordered behind this replay.
func (store *UserAccountOutboxStore) ReplayTerminalFailure(
	ctx context.Context,
	eventID string,
	replayedAt time.Time,
) error {
	var replayedEventID string
	err := store.pool.QueryRow(ctx, `
WITH reactivated AS (
  UPDATE user_account_outbox
  SET retry_count=0,
      next_attempt_at=$2,
      last_failure_code='',
      last_failure_digest='',
      last_failed_at=NULL,
      terminal_failure_at=NULL,
      lease_owner=NULL,
      lease_until=NULL
  WHERE event_id=$1
    AND published_at IS NULL
    AND terminal_failure_at IS NOT NULL
  RETURNING event_id
),
removed_dead_letter AS (
  DELETE FROM user_account_outbox_dead_letters
  WHERE event_id IN (SELECT event_id FROM reactivated)
)
SELECT event_id FROM reactivated`,
		strings.TrimSpace(eventID),
		replayedAt.UTC(),
	).Scan(&replayedEventID)
	if errors.Is(err, pgx.ErrNoRows) {
		return errors.New("UserAccount outbox terminal failure not found for replay")
	}
	if err != nil {
		return fmt.Errorf("replay UserAccount outbox terminal failure: %w", err)
	}
	return nil
}

// PruneExpiredTerminalFailures enforces the finite retention window for
// payload-free DLQ diagnostics. The source outbox event remains terminal to
// preserve delivery order until an operator explicitly replays it.
func (store *UserAccountOutboxStore) PruneExpiredTerminalFailures(
	ctx context.Context,
	now time.Time,
) (int64, error) {
	tag, err := store.pool.Exec(ctx, `
DELETE FROM user_account_outbox_dead_letters
WHERE expires_at <= $1`, now.UTC())
	if err != nil {
		return 0, fmt.Errorf("prune UserAccount outbox terminal failures: %w", err)
	}
	return tag.RowsAffected(), nil
}

// TerminalFailureCount intentionally reads the source status rather than the
// TTL-bounded DLQ table, so readiness still exposes a terminal ordering block
// after its diagnostic record has expired.
func (store *UserAccountOutboxStore) TerminalFailureCount(
	ctx context.Context,
) (int, error) {
	var count int
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM user_account_outbox
WHERE published_at IS NULL
  AND terminal_failure_at IS NOT NULL`).Scan(&count); err != nil {
		return 0, fmt.Errorf("count UserAccount outbox terminal failures: %w", err)
	}
	return count, nil
}

func normalizeUserAccountOutboxFailure(
	failure accountports.UserAccountOutboxFailure,
) (accountports.UserAccountOutboxFailure, error) {
	failure.Code = accountports.UserAccountOutboxFailureCode(
		strings.TrimSpace(string(failure.Code)),
	)
	failure.Digest = strings.ToLower(strings.TrimSpace(failure.Digest))
	switch failure.Code {
	case accountports.UserAccountOutboxFailurePayloadDecode,
		accountports.UserAccountOutboxFailureUnsupportedType,
		accountports.UserAccountOutboxFailurePublish,
		accountports.UserAccountOutboxFailurePublishAck,
		accountports.UserAccountOutboxFailureRetryRecord,
		accountports.UserAccountOutboxFailureTerminalRecord,
		accountports.UserAccountOutboxFailureClaim,
		accountports.UserAccountOutboxFailureRetentionPrune,
		accountports.UserAccountOutboxFailureHealthStore,
		accountports.UserAccountOutboxFailureUnexpected:
	default:
		return accountports.UserAccountOutboxFailure{}, errors.New(
			"UserAccount outbox failure code is invalid",
		)
	}
	if len(failure.Digest) != 64 {
		return accountports.UserAccountOutboxFailure{}, errors.New(
			"UserAccount outbox failure digest is invalid",
		)
	}
	if _, err := hex.DecodeString(failure.Digest); err != nil {
		return accountports.UserAccountOutboxFailure{}, errors.New(
			"UserAccount outbox failure digest is invalid",
		)
	}
	return failure, nil
}
