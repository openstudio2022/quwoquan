package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	userevent "quwoquan_service/services/user-service/internal/account/user_account/domain/user/event"
)

// EnforcementStore 实现 UserAccount 的可逆处置事务；它不会复用注销清理 Store。
type EnforcementStore struct {
	pool *pgxpool.Pool
}

func NewEnforcementStore(pool *pgxpool.Pool) (*EnforcementStore, error) {
	if pool == nil {
		return nil, errors.New("UserAccount enforcement store requires a PostgreSQL pool")
	}
	return &EnforcementStore{pool: pool}, nil
}

var _ accountports.UserAccountEnforcementStore = (*EnforcementStore)(nil)
var _ accountports.AccountSecurityReader = (*EnforcementStore)(nil)

type accountEnforcementState struct {
	accountState   string
	authEpoch      int64
	profileVersion int64
}

type enforcementReceipt struct {
	accountID      string
	action         accountports.EnforcementAction
	caseRef        string
	decisionDigest string
	accountState   string
	authEpoch      int64
	occurredAt     time.Time
}

// userAccountEnforcementEventPayload 与 metadata 中的
// UserAccountEnforcementPayload 一一对应。它只携带下游 restriction projection
// 必需的最小事实，绝不序列化 case、审批证据或 digest。
type userAccountEnforcementEventPayload struct {
	UserID       string    `json:"userId"`
	PersonaIDs   []string  `json:"personaIds"`
	AccountState string    `json:"accountState"`
	AuthEpoch    int64     `json:"authEpoch"`
	DecisionRef  string    `json:"decisionRef"`
	OccurredAt   time.Time `json:"occurredAt"`
}

// ReadAccountSecurity 只读取鉴权必需的权威状态；调用方必须对错误 fail-closed。
func (store *EnforcementStore) ReadAccountSecurity(
	ctx context.Context,
	accountID string,
) (accountports.AccountSecuritySnapshot, error) {
	var snapshot accountports.AccountSecuritySnapshot
	err := store.pool.QueryRow(ctx, `
SELECT account_state, auth_epoch
FROM user_profiles
WHERE user_id=$1`, strings.TrimSpace(accountID)).Scan(
		&snapshot.AccountState,
		&snapshot.AuthEpoch,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return accountports.AccountSecuritySnapshot{}, accountports.ErrAccountNotFound
	}
	if err != nil {
		return accountports.AccountSecuritySnapshot{}, fmt.Errorf(
			"read UserAccount security state: %w",
			err,
		)
	}
	if snapshot.AuthEpoch <= 0 {
		return accountports.AccountSecuritySnapshot{}, fmt.Errorf(
			"read UserAccount security state: invalid auth epoch",
		)
	}
	return snapshot, nil
}

// CommitEnforcement 锁定账号后以 decisionId 去重。Suspend 与 Restore 都只修改可逆
// 账号限制状态：不会清理 Profile/Persona/内容，也不会调用 UserAccountClosed 的下游链路。
func (store *EnforcementStore) CommitEnforcement(
	ctx context.Context,
	accountID string,
	action accountports.EnforcementAction,
	decision accountports.EnforcementDecision,
	occurredAt time.Time,
) (accountports.EnforcementCommitResult, error) {
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return accountports.EnforcementCommitResult{}, fmt.Errorf(
			"begin UserAccount enforcement: %w",
			err,
		)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	state, err := loadAccountForEnforcement(ctx, tx, accountID)
	if err != nil {
		return accountports.EnforcementCommitResult{}, err
	}
	if replay, found, err := loadEnforcementReceipt(
		ctx,
		tx,
		decision.DecisionID,
	); err != nil {
		return accountports.EnforcementCommitResult{}, err
	} else if found {
		if replay.accountID != accountID || replay.action != action ||
			replay.caseRef != decision.CaseRef ||
			replay.decisionDigest != decision.DecisionDigest {
			return accountports.EnforcementCommitResult{},
				accountports.ErrEnforcementDecisionInvalid
		}
		if err := tx.Commit(ctx); err != nil {
			return accountports.EnforcementCommitResult{}, fmt.Errorf(
				"commit UserAccount enforcement replay: %w",
				err,
			)
		}
		return accountports.EnforcementCommitResult{
			AccountState:     replay.accountState,
			AuthEpoch:        replay.authEpoch,
			DecisionID:       decision.DecisionID,
			IdempotentReplay: true,
			OccurredAt:       replay.occurredAt.UTC(),
		}, nil
	}

	nextState, eventType, err := resolveEnforcementTransition(
		state.accountState,
		action,
	)
	if err != nil {
		return accountports.EnforcementCommitResult{}, err
	}
	if occurredAt.IsZero() {
		return accountports.EnforcementCommitResult{},
			accountports.ErrEnforcementDecisionInvalid
	}
	occurredAt = occurredAt.UTC()

	personaIDs, err := listAccountPersonaIDs(ctx, tx, accountID)
	if err != nil {
		return accountports.EnforcementCommitResult{}, err
	}
	nextEpoch := state.authEpoch + 1
	nextVersion := state.profileVersion + 1
	if err := applyAccountEnforcementState(
		ctx,
		tx,
		accountID,
		action,
		nextEpoch,
		nextVersion,
		decision.CaseRef,
		occurredAt,
	); err != nil {
		return accountports.EnforcementCommitResult{}, err
	}
	if err := revokeAccountRefreshSessions(
		ctx,
		tx,
		accountID,
		action,
		occurredAt,
	); err != nil {
		return accountports.EnforcementCommitResult{}, err
	}
	if err := appendEnforcementReceipt(
		ctx,
		tx,
		accountID,
		action,
		decision,
		nextState,
		nextEpoch,
		nextVersion,
		occurredAt,
	); err != nil {
		return accountports.EnforcementCommitResult{}, err
	}
	if err := appendUserAccountEnforcementEvent(
		ctx,
		tx,
		accountID,
		personaIDs,
		nextState,
		nextEpoch,
		decision.DecisionID,
		eventType,
		nextVersion,
		occurredAt,
	); err != nil {
		return accountports.EnforcementCommitResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return accountports.EnforcementCommitResult{}, fmt.Errorf(
			"commit UserAccount enforcement: %w",
			err,
		)
	}
	return accountports.EnforcementCommitResult{
		AccountState: nextState,
		AuthEpoch:    nextEpoch,
		DecisionID:   decision.DecisionID,
		OccurredAt:   occurredAt,
	}, nil
}

func loadAccountForEnforcement(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
) (accountEnforcementState, error) {
	var state accountEnforcementState
	err := tx.QueryRow(ctx, `
SELECT account_state, auth_epoch, profile_version
FROM user_profiles
WHERE user_id=$1
FOR UPDATE`, accountID).Scan(
		&state.accountState,
		&state.authEpoch,
		&state.profileVersion,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return accountEnforcementState{}, accountports.ErrAccountNotFound
	}
	if err != nil {
		return accountEnforcementState{}, fmt.Errorf(
			"load UserAccount for enforcement: %w",
			err,
		)
	}
	if state.authEpoch <= 0 {
		return accountEnforcementState{}, accountports.ErrEnforcementDecisionInvalid
	}
	return state, nil
}

func loadEnforcementReceipt(
	ctx context.Context,
	tx pgx.Tx,
	decisionID string,
) (enforcementReceipt, bool, error) {
	var receipt enforcementReceipt
	err := tx.QueryRow(ctx, `
SELECT account_id, action, case_ref, decision_digest, account_state, auth_epoch, occurred_at
FROM user_account_enforcement_receipts
WHERE decision_id=$1`, decisionID).Scan(
		&receipt.accountID,
		&receipt.action,
		&receipt.caseRef,
		&receipt.decisionDigest,
		&receipt.accountState,
		&receipt.authEpoch,
		&receipt.occurredAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return enforcementReceipt{}, false, nil
	}
	if err != nil {
		return enforcementReceipt{}, false, fmt.Errorf(
			"load UserAccount enforcement receipt: %w",
			err,
		)
	}
	return receipt, true, nil
}

func resolveEnforcementTransition(
	currentState string,
	action accountports.EnforcementAction,
) (nextState string, eventType string, err error) {
	switch action {
	case accountports.EnforcementActionSuspend:
		if currentState != "active" {
			return "", "", accountports.ErrAccountStateConflict
		}
		return "suspended", userevent.UserSuspended, nil
	case accountports.EnforcementActionRestore:
		if currentState != "suspended" {
			return "", "", accountports.ErrAccountStateConflict
		}
		return "active", userevent.UserRestored, nil
	default:
		return "", "", accountports.ErrEnforcementDecisionInvalid
	}
}

func applyAccountEnforcementState(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	action accountports.EnforcementAction,
	nextEpoch int64,
	nextVersion int64,
	caseRef string,
	occurredAt time.Time,
) error {
	var tag pgconn.CommandTag
	var err error
	switch action {
	case accountports.EnforcementActionSuspend:
		tag, err = tx.Exec(ctx, `
UPDATE user_profiles
SET account_state='suspended',
    auth_epoch=$2,
    suspension_case_ref=$3,
    suspended_at=$4,
    profile_version=$5,
    updated_at=$4
WHERE user_id=$1 AND account_state='active'`,
			accountID,
			nextEpoch,
			caseRef,
			occurredAt,
			nextVersion,
		)
	case accountports.EnforcementActionRestore:
		tag, err = tx.Exec(ctx, `
UPDATE user_profiles
SET account_state='active',
    auth_epoch=$2,
    suspension_case_ref=NULL,
    profile_version=$3,
    updated_at=$4
WHERE user_id=$1 AND account_state='suspended'`,
			accountID,
			nextEpoch,
			nextVersion,
			occurredAt,
		)
	default:
		return accountports.ErrEnforcementDecisionInvalid
	}
	if err != nil {
		return fmt.Errorf("update UserAccount enforcement state: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return accountports.ErrAccountStateConflict
	}
	return nil
}

func revokeAccountRefreshSessions(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	action accountports.EnforcementAction,
	occurredAt time.Time,
) error {
	reason := "account_suspended"
	if action == accountports.EnforcementActionRestore {
		reason = "account_restored"
	}
	if _, err := tx.Exec(ctx, `
UPDATE account_sessions
SET status='revoked',
    revoked_at=$2,
    revoke_reason=$3,
    version=version+1,
    updated_at=$2
WHERE account_id=$1 AND status IN ('active','rotated')`,
		accountID,
		occurredAt,
		reason,
	); err != nil {
		return fmt.Errorf("revoke UserAccount refresh sessions: %w", err)
	}
	return nil
}

func appendEnforcementReceipt(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	action accountports.EnforcementAction,
	decision accountports.EnforcementDecision,
	accountState string,
	authEpoch int64,
	accountVersion int64,
	occurredAt time.Time,
) error {
	_, err := tx.Exec(ctx, `
INSERT INTO user_account_enforcement_receipts(
  decision_id, account_id, action, case_ref, decision_digest, approved_at,
  account_state, auth_epoch, account_version, occurred_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
		decision.DecisionID,
		accountID,
		string(action),
		decision.CaseRef,
		decision.DecisionDigest,
		decision.ApprovedAt.UTC(),
		accountState,
		authEpoch,
		accountVersion,
		occurredAt,
	)
	if err == nil {
		return nil
	}
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "23505" {
		return accountports.ErrEnforcementDecisionInvalid
	}
	return fmt.Errorf("append UserAccount enforcement receipt: %w", err)
}

func appendUserAccountEnforcementEvent(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	personaIDs []string,
	accountState string,
	authEpoch int64,
	decisionID string,
	eventType string,
	accountVersion int64,
	occurredAt time.Time,
) error {
	payload, err := json.Marshal(userAccountEnforcementEventPayload{
		UserID:       accountID,
		PersonaIDs:   personaIDs,
		AccountState: accountState,
		AuthEpoch:    authEpoch,
		DecisionRef:  decisionID,
		OccurredAt:   occurredAt,
	})
	if err != nil {
		return fmt.Errorf("encode UserAccount enforcement outbox: %w", err)
	}
	eventDigest := sha256.Sum256([]byte(
		eventType + "\x00" + strings.TrimSpace(decisionID),
	))
	tag, err := tx.Exec(ctx, `
INSERT INTO user_account_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,$4,$5,$6)
ON CONFLICT (aggregate_id, aggregate_version, event_type) DO NOTHING`,
		hex.EncodeToString(eventDigest[:]),
		accountID,
		accountVersion,
		eventType,
		payload,
		occurredAt,
	)
	if err != nil {
		return fmt.Errorf("append UserAccount enforcement outbox: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return fmt.Errorf(
			"append UserAccount enforcement outbox: aggregate version conflict",
		)
	}
	return nil
}
