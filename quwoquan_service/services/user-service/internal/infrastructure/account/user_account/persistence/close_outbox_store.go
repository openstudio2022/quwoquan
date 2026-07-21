package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
)

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
  SELECT event_id
  FROM user_account_outbox
  WHERE published_at IS NULL
    AND next_attempt_at <= $2
    AND (lease_until IS NULL OR lease_until <= $2)
  ORDER BY occurred_at, event_id
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
    last_error=''
WHERE event_id=$1 AND lease_owner=$2 AND published_at IS NULL`,
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
	nextAttemptAt time.Time,
	lastError string,
) error {
	lastError = strings.TrimSpace(lastError)
	if len(lastError) > 1024 {
		lastError = lastError[:1024]
	}
	tag, err := store.pool.Exec(ctx, `
UPDATE user_account_outbox
SET next_attempt_at=$3,
    last_error=$4,
    lease_owner=NULL,
    lease_until=NULL
WHERE event_id=$1 AND lease_owner=$2 AND published_at IS NULL`,
		eventID,
		owner,
		nextAttemptAt.UTC(),
		lastError,
	)
	if err != nil {
		return fmt.Errorf("mark UserAccount outbox failed: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return errors.New("UserAccount outbox lease lost before failure ack")
	}
	return nil
}
