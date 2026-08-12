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

	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

// UserProfileSearchOutboxStore persists the replay checkpoint for ordinary
// profile search projection. Each row retains the exact public projection
// payload committed with its Persona/account mutation so transport retries
// cannot observe a later profile version.
type UserProfileSearchOutboxStore struct {
	pool *pgxpool.Pool
}

var _ userports.UserProfileSearchOutboxStore = (*UserProfileSearchOutboxStore)(nil)

func NewUserProfileSearchOutboxStore(
	pool *pgxpool.Pool,
) (*UserProfileSearchOutboxStore, error) {
	if pool == nil {
		return nil, errors.New("UserProfile search outbox store requires PostgreSQL")
	}
	return &UserProfileSearchOutboxStore{pool: pool}, nil
}

func (store *UserProfileSearchOutboxStore) ClaimPendingOutbox(
	ctx context.Context,
	owner string,
	now time.Time,
	lease time.Duration,
) (userports.UserProfileSearchOutboxEvent, bool, error) {
	owner = strings.TrimSpace(owner)
	if owner == "" || lease <= 0 {
		return userports.UserProfileSearchOutboxEvent{}, false, errors.New(
			"UserProfile search outbox claim requires owner and positive lease",
		)
	}

	var event userports.UserProfileSearchOutboxEvent
	err := store.pool.QueryRow(ctx, `
WITH candidate AS (
  SELECT outbox.event_id
  FROM user_profile_search_outbox AS outbox
  WHERE outbox.published_at IS NULL
    AND outbox.next_attempt_at <= $2
    AND (outbox.lease_until IS NULL OR outbox.lease_until <= $2)
    -- Keep projection order per profile. Reconciliation reads the latest
    -- authoritative state, but an older pending checkpoint must not be skipped.
    AND NOT EXISTS (
      SELECT 1
      FROM user_profile_search_outbox AS earlier
      WHERE earlier.user_id = outbox.user_id
        AND earlier.published_at IS NULL
        AND (earlier.occurred_at, earlier.event_id) <
            (outbox.occurred_at, outbox.event_id)
    )
  ORDER BY outbox.occurred_at, outbox.event_id
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
UPDATE user_profile_search_outbox AS outbox
SET lease_owner=$1,
    lease_until=$3,
    retry_count=retry_count+1
FROM candidate
WHERE outbox.event_id=candidate.event_id
RETURNING
  outbox.event_id,
  outbox.user_id,
  outbox.profile_version,
  outbox.event_type,
  outbox.occurred_at,
  outbox.payload_json,
  outbox.retry_count`,
		owner,
		now.UTC(),
		now.UTC().Add(lease),
	).Scan(
		&event.EventID,
		&event.UserID,
		&event.ProfileVersion,
		&event.EventType,
		&event.OccurredAt,
		&event.PayloadJSON,
		&event.DeliveryAttempt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return userports.UserProfileSearchOutboxEvent{}, false, nil
	}
	if err != nil {
		return userports.UserProfileSearchOutboxEvent{}, false, fmt.Errorf(
			"claim UserProfile search outbox: %w",
			err,
		)
	}
	return event, true, nil
}

func (store *UserProfileSearchOutboxStore) MarkPublished(
	ctx context.Context,
	eventID string,
	owner string,
	publishedAt time.Time,
) error {
	tag, err := store.pool.Exec(ctx, `
UPDATE user_profile_search_outbox
SET published_at=$3,
    lease_owner=NULL,
    lease_until=NULL,
    last_failure_code='',
    last_failure_digest='',
    last_failed_at=NULL
WHERE event_id=$1
  AND lease_owner=$2
  AND published_at IS NULL`,
		strings.TrimSpace(eventID),
		strings.TrimSpace(owner),
		publishedAt.UTC(),
	)
	if err != nil {
		return fmt.Errorf("mark UserProfile search outbox published: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return errors.New("UserProfile search outbox lease lost before publish ack")
	}
	return nil
}

func (store *UserProfileSearchOutboxStore) MarkFailed(
	ctx context.Context,
	eventID string,
	owner string,
	failedAt time.Time,
	nextAttemptAt time.Time,
	failure userports.UserProfileSearchOutboxFailure,
) error {
	failure, err := normalizeUserProfileSearchOutboxFailure(failure)
	if err != nil {
		return err
	}
	tag, err := store.pool.Exec(ctx, `
UPDATE user_profile_search_outbox
SET next_attempt_at=$3,
    last_failure_code=$4,
    last_failure_digest=$5,
    last_failed_at=$6,
    lease_owner=NULL,
    lease_until=NULL
WHERE event_id=$1
  AND lease_owner=$2
  AND published_at IS NULL`,
		strings.TrimSpace(eventID),
		strings.TrimSpace(owner),
		nextAttemptAt.UTC(),
		failure.Code,
		failure.Digest,
		failedAt.UTC(),
	)
	if err != nil {
		return fmt.Errorf("mark UserProfile search outbox failed: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return errors.New("UserProfile search outbox lease lost before failure ack")
	}
	return nil
}

func (store *UserProfileSearchOutboxStore) PendingCount(
	ctx context.Context,
) (int, error) {
	var count int
	if err := store.pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM user_profile_search_outbox
WHERE published_at IS NULL`).Scan(&count); err != nil {
		return 0, fmt.Errorf("count UserProfile search outbox pending: %w", err)
	}
	return count, nil
}

func normalizeUserProfileSearchOutboxFailure(
	failure userports.UserProfileSearchOutboxFailure,
) (userports.UserProfileSearchOutboxFailure, error) {
	failure.Code = userports.UserProfileSearchOutboxFailureCode(
		strings.TrimSpace(string(failure.Code)),
	)
	failure.Digest = strings.ToLower(strings.TrimSpace(failure.Digest))
	switch failure.Code {
	case userports.UserProfileSearchOutboxFailureClaim,
		userports.UserProfileSearchOutboxFailurePublish,
		userports.UserProfileSearchOutboxFailurePublishAck,
		userports.UserProfileSearchOutboxFailureRetryRecord,
		userports.UserProfileSearchOutboxFailureHealthStore,
		userports.UserProfileSearchOutboxFailureUnexpected:
	default:
		return userports.UserProfileSearchOutboxFailure{}, errors.New(
			"UserProfile search outbox failure code is invalid",
		)
	}
	if len(failure.Digest) != 64 {
		return userports.UserProfileSearchOutboxFailure{}, errors.New(
			"UserProfile search outbox failure digest is invalid",
		)
	}
	if _, err := hex.DecodeString(failure.Digest); err != nil {
		return userports.UserProfileSearchOutboxFailure{}, errors.New(
			"UserProfile search outbox failure digest is invalid",
		)
	}
	return failure, nil
}
