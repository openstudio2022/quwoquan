package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

// AccountCreationRecoveryPostgresStore 实现 UserAccount-owned 注册恢复状态。
// 所有变更按 flow_id 行锁串行；状态只单向推进，不允许重写已选择身份。
type AccountCreationRecoveryPostgresStore struct {
	pool *pgxpool.Pool
}

func NewAccountCreationRecoveryPostgresStore(pool *pgxpool.Pool) (*AccountCreationRecoveryPostgresStore, error) {
	if pool == nil {
		return nil, errors.New("account creation recovery PostgreSQL pool is required")
	}
	return &AccountCreationRecoveryPostgresStore{pool: pool}, nil
}

var _ application.AccountCreationRecoveryStore = (*AccountCreationRecoveryPostgresStore)(nil)

func (store *AccountCreationRecoveryPostgresStore) Begin(
	ctx context.Context,
	candidate application.AccountCreationFlow,
) (application.AccountCreationFlow, error) {
	if err := candidate.Validate(); err != nil {
		return application.AccountCreationFlow{}, err
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return application.AccountCreationFlow{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx,
		`SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`,
		"account-creation-flow:"+candidate.FlowID,
	); err != nil {
		return application.AccountCreationFlow{}, err
	}
	stored, found, err := loadAccountCreationFlow(ctx, tx, candidate.FlowID)
	if err != nil {
		return application.AccountCreationFlow{}, err
	}
	if found {
		if stored.IntentDigest != candidate.IntentDigest {
			return application.AccountCreationFlow{}, application.ErrAccountCreationFlowConflict
		}
		if err := tx.Commit(ctx); err != nil {
			return application.AccountCreationFlow{}, err
		}
		return stored, nil
	}
	_, err = tx.Exec(ctx, `
INSERT INTO user_account_creation_flows(
  flow_id, intent_digest, owner_id, persona_id, default_nickname, identity_origin,
  account_committed, persona_committed, profile_projected, credential_bound,
  completed, created_at, updated_at
) VALUES ($1,$2,$3,$4,$5,$6,FALSE,FALSE,FALSE,FALSE,FALSE,NOW(),NOW())`,
		candidate.FlowID, candidate.IntentDigest, candidate.OwnerID, candidate.PersonaID,
		candidate.DefaultNickname, candidate.IdentityOrigin,
	)
	if err != nil {
		return application.AccountCreationFlow{}, fmt.Errorf("insert account creation flow: %w", err)
	}
	stored, _, err = loadAccountCreationFlow(ctx, tx, candidate.FlowID)
	if err != nil {
		return application.AccountCreationFlow{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return application.AccountCreationFlow{}, err
	}
	return stored, nil
}

func (store *AccountCreationRecoveryPostgresStore) Load(
	ctx context.Context,
	flowID string,
) (application.AccountCreationFlow, bool, error) {
	if strings.TrimSpace(flowID) == "" {
		return application.AccountCreationFlow{}, false, nil
	}
	return loadAccountCreationFlow(ctx, store.pool, flowID)
}

func (store *AccountCreationRecoveryPostgresStore) MarkStep(
	ctx context.Context,
	flowID string,
	step application.AccountCreationStep,
) error {
	flowID = strings.TrimSpace(flowID)
	if flowID == "" || !step.ValidForPersistence() {
		return errors.New("invalid account creation recovery step")
	}
	column := map[application.AccountCreationStep]string{
		application.AccountCreationAccountCommitted: "account_committed",
		application.AccountCreationPersonaCommitted: "persona_committed",
		application.AccountCreationProfileProjected: "profile_projected",
		application.AccountCreationCredentialBound:  "credential_bound",
	}[step]
	completedExpression := map[application.AccountCreationStep]string{
		application.AccountCreationAccountCommitted: "TRUE AND persona_committed AND profile_projected AND credential_bound",
		application.AccountCreationPersonaCommitted: "account_committed AND TRUE AND profile_projected AND credential_bound",
		application.AccountCreationProfileProjected: "account_committed AND persona_committed AND TRUE AND credential_bound",
		application.AccountCreationCredentialBound:  "account_committed AND persona_committed AND profile_projected AND TRUE",
	}[step]
	command, err := store.pool.Exec(ctx, fmt.Sprintf(`
UPDATE user_account_creation_flows
SET %s=TRUE, completed=(%s), updated_at=NOW()
WHERE flow_id=$1`, column, completedExpression), flowID)
	if err != nil {
		return fmt.Errorf("mark account creation recovery step: %w", err)
	}
	if command.RowsAffected() != 1 {
		return application.ErrAccountCreationFlowNotFound
	}
	return nil
}

func (store *AccountCreationRecoveryPostgresStore) ReplacePersonaCandidate(
	ctx context.Context,
	flowID string,
	expectedPersonaID string,
	nextPersonaID string,
) error {
	flowID = strings.TrimSpace(flowID)
	expectedPersonaID = strings.TrimSpace(expectedPersonaID)
	nextPersonaID = strings.TrimSpace(nextPersonaID)
	if flowID == "" || expectedPersonaID == "" || nextPersonaID == "" || expectedPersonaID == nextPersonaID {
		return errors.New("invalid account creation Persona candidate replacement")
	}
	command, err := store.pool.Exec(ctx, `
UPDATE user_account_creation_flows
SET persona_id=$3, updated_at=NOW()
WHERE flow_id=$1 AND persona_id=$2 AND persona_committed=FALSE`,
		flowID, expectedPersonaID, nextPersonaID)
	if err != nil {
		return fmt.Errorf("replace account creation Persona candidate: %w", err)
	}
	if command.RowsAffected() != 1 {
		return application.ErrAccountCreationCandidateStale
	}
	return nil
}

func loadAccountCreationFlow(
	ctx context.Context,
	querier interface {
		QueryRow(context.Context, string, ...any) pgx.Row
	},
	flowID string,
) (application.AccountCreationFlow, bool, error) {
	var flow application.AccountCreationFlow
	err := querier.QueryRow(ctx, `
SELECT flow_id, intent_digest, owner_id, persona_id, default_nickname, identity_origin,
       account_committed, persona_committed, profile_projected, credential_bound,
       completed, created_at, updated_at
FROM user_account_creation_flows
WHERE flow_id=$1`, strings.TrimSpace(flowID)).Scan(
		&flow.FlowID, &flow.IntentDigest, &flow.OwnerID, &flow.PersonaID,
		&flow.DefaultNickname, &flow.IdentityOrigin,
		&flow.AccountCommitted, &flow.PersonaCommitted, &flow.ProfileProjected,
		&flow.CredentialBound, &flow.Completed, &flow.CreatedAt, &flow.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return application.AccountCreationFlow{}, false, nil
	}
	if err != nil {
		return application.AccountCreationFlow{}, false, fmt.Errorf("load account creation flow: %w", err)
	}
	return flow, true, nil
}
