// Package persistence 实现 AuthenticationChallenge 对象专属 PostgreSQL Store。
package persistence

import (
	"context"
	"crypto/subtle"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
	challengeports "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/ports"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("AuthenticationChallenge PostgreSQL pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

var _ challengeports.AggregateStore = (*PostgresStore)(nil)

// Create 以 advisory transaction lock 串行化同一 idempotency key，并把
// challenge 与创建指纹写入同一 authoritative row。
func (store *PostgresStore) Create(
	ctx context.Context,
	commit challengeports.CreateCommit,
) (challengeports.CreateResult, error) {
	idempotencyKey := strings.TrimSpace(commit.IdempotencyKey)
	commandFingerprint := strings.TrimSpace(commit.CommandFingerprint)
	if idempotencyKey == "" ||
		len(idempotencyKey) > 256 ||
		len(commandFingerprint) != 64 {
		return challengeports.CreateResult{}, challengemodel.ErrInvalidChallenge
	}
	if err := commit.Aggregate.Validate(); err != nil {
		return challengeports.CreateResult{}, err
	}
	state := commit.Aggregate.State()
	if state.Status != challengemodel.StatusPending ||
		state.Version != 1 ||
		state.AttemptCount != 0 {
		return challengeports.CreateResult{}, challengemodel.ErrInvalidChallenge
	}

	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return challengeports.CreateResult{}, fmt.Errorf(
			"begin authentication challenge create: %w",
			err,
		)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if err := lockIdempotencyKey(ctx, tx, idempotencyKey); err != nil {
		return challengeports.CreateResult{}, err
	}

	var (
		existingID          string
		existingFingerprint string
	)
	err = tx.QueryRow(ctx, `
SELECT challenge_id, creation_fingerprint
FROM authentication_challenges
WHERE idempotency_key=$1
FOR UPDATE`, idempotencyKey).Scan(&existingID, &existingFingerprint)
	switch {
	case err == nil:
		if !equalCreationFingerprint(existingFingerprint, commandFingerprint) {
			return challengeports.CreateResult{}, challengeports.ErrIdempotencyConflict
		}
		existing, found, loadErr := loadByID(ctx, tx, existingID)
		if loadErr != nil {
			return challengeports.CreateResult{}, loadErr
		}
		if !found {
			return challengeports.CreateResult{}, errors.New(
				"authentication challenge receipt references an absent row",
			)
		}
		if err := tx.Commit(ctx); err != nil {
			return challengeports.CreateResult{}, fmt.Errorf(
				"commit authentication challenge replay: %w",
				err,
			)
		}
		return challengeports.CreateResult{Aggregate: existing, Replayed: true}, nil
	case !errors.Is(err, pgx.ErrNoRows):
		return challengeports.CreateResult{}, fmt.Errorf(
			"load authentication challenge creation receipt: %w",
			err,
		)
	}

	if _, err := tx.Exec(ctx, `
INSERT INTO authentication_challenges (
  challenge_id, request_id, account_id, purpose, channel, phone_hash, code_hash,
  binding_ticket_id, delivery_status, delivery_updated_at, last_delivery_event_id,
  status, failed_attempts, expires_at, created_at, consumed_at,
  completion_fingerprint, idempotency_key, creation_fingerprint,
  version, updated_at
) VALUES (
  $1, NULLIF($2, ''), NULLIF($3, ''), $4, $5, NULLIF($6, ''), $7,
  NULLIF($8, ''), NULLIF($9, ''), $10, NULLIF($11, ''),
  $12, $13, $14, $15, NULL,
  NULL, $16, $17, $18, $19
)`,
		state.ID,
		state.DeliveryRequestID,
		state.AccountID,
		state.Purpose,
		state.Channel,
		state.DestinationHash,
		state.SecretRef,
		state.BindingTicketRef,
		state.DeliveryStatus,
		state.DeliveryUpdatedAt,
		state.LastDeliveryEventID,
		state.Status,
		state.AttemptCount,
		state.ExpiresAt,
		state.CreatedAt,
		idempotencyKey,
		commandFingerprint,
		state.Version,
		state.UpdatedAt,
	); err != nil {
		return challengeports.CreateResult{}, fmt.Errorf(
			"insert authentication challenge: %w",
			err,
		)
	}
	if err := tx.Commit(ctx); err != nil {
		return challengeports.CreateResult{}, fmt.Errorf(
			"commit authentication challenge create: %w",
			err,
		)
	}
	return challengeports.CreateResult{Aggregate: commit.Aggregate}, nil
}

func (store *PostgresStore) LoadByID(
	ctx context.Context,
	challengeID string,
) (challengemodel.AuthenticationChallenge, bool, error) {
	challengeID = strings.TrimSpace(challengeID)
	if challengeID == "" {
		return challengemodel.AuthenticationChallenge{}, false,
			challengemodel.ErrInvalidChallenge
	}
	return loadByID(ctx, store.pool, challengeID)
}

func (store *PostgresStore) LoadLatest(
	ctx context.Context,
	lookup challengeports.LatestChallengeLookup,
) (challengemodel.AuthenticationChallenge, bool, error) {
	lookup.Purpose = strings.TrimSpace(lookup.Purpose)
	lookup.Channel = strings.TrimSpace(lookup.Channel)
	lookup.DestinationHash = strings.TrimSpace(lookup.DestinationHash)
	if lookup.Purpose == "" ||
		lookup.Channel == "" ||
		lookup.DestinationHash == "" {
		return challengemodel.AuthenticationChallenge{}, false,
			challengemodel.ErrInvalidChallenge
	}
	return scanChallenge(store.pool.QueryRow(ctx, `
SELECT `+challengeSelectColumns+`
FROM authentication_challenges
WHERE purpose=$1 AND channel=$2 AND phone_hash=$3
ORDER BY created_at DESC, challenge_id DESC
LIMIT 1`,
		lookup.Purpose,
		lookup.Channel,
		lookup.DestinationHash,
	))
}

func (store *PostgresStore) LoadByDeliveryRequestID(
	ctx context.Context,
	requestID string,
) (challengemodel.AuthenticationChallenge, bool, error) {
	requestID = strings.TrimSpace(requestID)
	if requestID == "" {
		return challengemodel.AuthenticationChallenge{}, false,
			challengemodel.ErrInvalidChallenge
	}
	return scanChallenge(store.pool.QueryRow(ctx, `
SELECT `+challengeSelectColumns+`
FROM authentication_challenges
WHERE request_id=$1`, requestID))
}

// Commit 使用内部 version CAS；status、attemptCount、completedAt 与
// completion fingerprint 在同一行、同一 PostgreSQL transaction 原子更新。
func (store *PostgresStore) Commit(
	ctx context.Context,
	expectedVersion int64,
	aggregate challengemodel.AuthenticationChallenge,
) error {
	if err := aggregate.Validate(); err != nil {
		return err
	}
	state := aggregate.State()
	if expectedVersion < 1 || state.Version != expectedVersion+1 {
		return challengemodel.ErrVersionConflict
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return fmt.Errorf("begin authentication challenge commit: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	tag, err := tx.Exec(ctx, `
UPDATE authentication_challenges
SET
  status=$2,
  failed_attempts=$3,
  consumed_at=$4,
  completion_fingerprint=NULLIF($5, ''),
  delivery_status=NULLIF($6, ''),
  delivery_updated_at=$7,
  last_delivery_event_id=NULLIF($8, ''),
  version=$9,
  updated_at=$10
WHERE challenge_id=$1 AND version=$11`,
		state.ID,
		state.Status,
		state.AttemptCount,
		state.CompletedAt,
		state.CompletionFingerprint,
		state.DeliveryStatus,
		state.DeliveryUpdatedAt,
		state.LastDeliveryEventID,
		state.Version,
		state.UpdatedAt,
		expectedVersion,
	)
	if err != nil {
		return fmt.Errorf("update authentication challenge: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return challengemodel.ErrVersionConflict
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit authentication challenge state: %w", err)
	}
	return nil
}

type challengeQueryer interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

func loadByID(
	ctx context.Context,
	queryer challengeQueryer,
	challengeID string,
) (challengemodel.AuthenticationChallenge, bool, error) {
	return scanChallenge(queryer.QueryRow(ctx, `
SELECT `+challengeSelectColumns+`
FROM authentication_challenges
WHERE challenge_id=$1`, challengeID))
}

func lockIdempotencyKey(
	ctx context.Context,
	tx pgx.Tx,
	idempotencyKey string,
) error {
	if _, err := tx.Exec(
		ctx,
		`SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`,
		"authentication_challenge:"+idempotencyKey,
	); err != nil {
		return fmt.Errorf("lock authentication challenge idempotency key: %w", err)
	}
	return nil
}

func equalCreationFingerprint(left, right string) bool {
	leftBytes := []byte(strings.TrimSpace(left))
	rightBytes := []byte(strings.TrimSpace(right))
	return len(leftBytes) == len(rightBytes) &&
		subtle.ConstantTimeCompare(leftBytes, rightBytes) == 1
}
