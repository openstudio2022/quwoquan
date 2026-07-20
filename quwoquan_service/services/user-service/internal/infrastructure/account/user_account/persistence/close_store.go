// Package persistence 实现 UserAccount 账号注销终态的对象专属 PostgreSQL Store。
package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	accountports "quwoquan_service/services/user-service/internal/domain/account/user_account/ports"
)

type CloseStore struct {
	pool *pgxpool.Pool
}

func NewCloseStore(pool *pgxpool.Pool) (*CloseStore, error) {
	if pool == nil {
		return nil, errors.New("UserAccount close store requires a PostgreSQL pool")
	}
	return &CloseStore{pool: pool}, nil
}

var _ accountports.UserAccountCloseStore = (*CloseStore)(nil)

type accountCloseState struct {
	accountState string
	updatedAt    time.Time
	version      int64
	phone        string
}

// CommitClose 在同一事务内完成账号安全终态、会话/凭证吊销、PII 擦除、
// 私有数据清理、Persona 退役与 UserAccountClosed outbox。
// 已 closed 账号仍执行幂等收敛，但 closedAt、version 与 outbox 保持稳定。
func (store *CloseStore) CommitClose(
	ctx context.Context,
	accountID string,
	closedAt time.Time,
) (accountports.CloseResult, error) {
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return accountports.CloseResult{}, fmt.Errorf("begin UserAccount close: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	state, err := loadAccountForClose(ctx, tx, accountID)
	if err != nil {
		return accountports.CloseResult{}, err
	}

	alreadyClosed := state.accountState == "closed"
	effectiveClosedAt := closedAt.UTC()
	if alreadyClosed {
		effectiveClosedAt = state.updatedAt.UTC()
	}
	if effectiveClosedAt.IsZero() {
		return accountports.CloseResult{}, errors.New(
			"UserAccount close requires a non-zero close time",
		)
	}

	personaIDs, err := listAccountPersonaIDs(ctx, tx, accountID)
	if err != nil {
		return accountports.CloseResult{}, err
	}
	credentials, err := loadCredentialCloseTargets(ctx, tx, accountID)
	if err != nil {
		return accountports.CloseResult{}, err
	}
	phoneCredentialKeys, destinationHashes := authenticationDestinations(
		state.phone,
		credentials,
	)

	if err := closeAccountSessions(
		ctx,
		tx,
		accountID,
		effectiveClosedAt,
	); err != nil {
		return accountports.CloseResult{}, err
	}
	if err := closeCredentialBindings(
		ctx,
		tx,
		accountID,
		credentials,
		effectiveClosedAt,
	); err != nil {
		return accountports.CloseResult{}, err
	}
	if err := eraseAccountPrivateState(
		ctx,
		tx,
		accountID,
		phoneCredentialKeys,
		destinationHashes,
		effectiveClosedAt,
	); err != nil {
		return accountports.CloseResult{}, err
	}
	if err := erasePersonaPrivateState(
		ctx,
		tx,
		accountID,
		personaIDs,
		effectiveClosedAt,
	); err != nil {
		return accountports.CloseResult{}, err
	}
	if err := retireAndScrubPersonas(
		ctx,
		tx,
		accountID,
		effectiveClosedAt,
	); err != nil {
		return accountports.CloseResult{}, err
	}

	accountVersion := state.version
	if !alreadyClosed {
		accountVersion++
	}
	if err := closeAndScrubAccountProfile(
		ctx,
		tx,
		accountID,
		accountVersion,
		effectiveClosedAt,
	); err != nil {
		return accountports.CloseResult{}, err
	}
	if err := appendUserAccountClosed(
		ctx,
		tx,
		accountID,
		accountVersion,
		personaIDs,
		effectiveClosedAt,
	); err != nil {
		return accountports.CloseResult{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return accountports.CloseResult{}, fmt.Errorf("commit UserAccount close: %w", err)
	}
	return accountports.CloseResult{
		AlreadyClosed:       alreadyClosed,
		ClosedAt:            effectiveClosedAt,
		PhoneCredentialKeys: phoneCredentialKeys,
	}, nil
}

func loadAccountForClose(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
) (accountCloseState, error) {
	var (
		state accountCloseState
		phone *string
	)
	err := tx.QueryRow(ctx, `
SELECT account_state, updated_at, profile_version, phone
FROM user_profiles
WHERE user_id = $1
FOR UPDATE`, accountID).Scan(
		&state.accountState,
		&state.updatedAt,
		&state.version,
		&phone,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return accountCloseState{}, accountports.ErrAccountNotFound
	}
	if err != nil {
		return accountCloseState{}, fmt.Errorf("load account for close: %w", err)
	}
	if phone != nil {
		state.phone = *phone
	}
	return state, nil
}

func listAccountPersonaIDs(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
) ([]string, error) {
	rows, err := tx.Query(ctx, `
SELECT sub_account_id
FROM personas
WHERE user_id=$1
ORDER BY sub_account_id
FOR UPDATE`, accountID)
	if err != nil {
		return nil, fmt.Errorf("list personas for account close: %w", err)
	}
	defer rows.Close()
	personaIDs := make([]string, 0)
	for rows.Next() {
		var personaID string
		if err := rows.Scan(&personaID); err != nil {
			return nil, fmt.Errorf("scan persona for account close: %w", err)
		}
		personaIDs = append(personaIDs, personaID)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate personas for account close: %w", err)
	}
	return personaIDs, nil
}

func closeAndScrubAccountProfile(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	accountVersion int64,
	closedAt time.Time,
) error {
	tag, err := tx.Exec(ctx, `
UPDATE user_profiles
SET account_state='closed',
    phone=NULL,
    nickname='已注销用户',
    nickname_customized=false,
    avatar_url=NULL,
    avatar_asset_id=NULL,
    avatar_version=0,
    background_url=NULL,
    background_asset_id=NULL,
    bio=NULL,
    identity_tags=NULL,
    gender=NULL,
    birth_date=NULL,
    region=NULL,
    region_code=NULL,
    status='closed',
    profile_version=$3,
    follower_count=0,
    following_count=0,
    post_count=0,
    circle_count=0,
    like_count=0,
    owner_display_name=NULL,
    sub_account_count=0,
    updated_at=$2
WHERE user_id=$1`, accountID, closedAt, accountVersion)
	if err != nil {
		return fmt.Errorf("close and scrub account profile: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return accountports.ErrAccountNotFound
	}
	return nil
}

func appendUserAccountClosed(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	accountVersion int64,
	personaIDs []string,
	closedAt time.Time,
) error {
	payload, err := json.Marshal(map[string]any{
		"userId":       accountID,
		"personaIds":   personaIDs,
		"accountState": "closed",
		"updatedAt":    closedAt.Format(time.RFC3339Nano),
	})
	if err != nil {
		return fmt.Errorf("encode UserAccountClosed outbox: %w", err)
	}
	eventDigest := sha256.Sum256([]byte("UserAccountClosed:" + accountID))
	if _, err := tx.Exec(ctx, `
INSERT INTO user_account_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,'UserAccountClosed',$4,$5)
ON CONFLICT (aggregate_id, aggregate_version, event_type) DO NOTHING`,
		hex.EncodeToString(eventDigest[:]),
		accountID,
		accountVersion,
		payload,
		closedAt,
	); err != nil {
		return fmt.Errorf("append UserAccountClosed outbox: %w", err)
	}
	return nil
}
