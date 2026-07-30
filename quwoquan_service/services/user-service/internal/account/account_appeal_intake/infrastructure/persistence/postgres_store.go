package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/model"
	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/ports"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("AccountAppealIntake PostgreSQL pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

func (store *PostgresStore) IssueCredential(
	ctx context.Context,
	commit ports.IssueCredentialCommit,
) (ports.CredentialReceipt, error) {
	if !validText(commit.CredentialID, 64) ||
		!validDigest(commit.CredentialDigest) ||
		!validText(commit.ChallengeID, 128) ||
		!model.CanonicalOwnerAccountID(commit.AccountID) || commit.IssuedAt.IsZero() ||
		!commit.ExpiresAt.Equal(commit.IssuedAt.Add(model.CredentialTTL)) ||
		!commit.DeleteAfter.Equal(commit.ExpiresAt.Add(model.CredentialAuditRetention)) {
		return ports.CredentialReceipt{}, ports.ErrCredentialInvalid
	}
	commit.IssuedAt = commit.IssuedAt.UTC()
	commit.ExpiresAt = commit.ExpiresAt.UTC()
	commit.DeleteAfter = commit.DeleteAfter.UTC()

	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return ports.CredentialReceipt{}, fmt.Errorf("begin appeal credential issue: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	_, authEpoch, err := lockSuspendedAccount(ctx, tx, commit.AccountID)
	if err != nil {
		return ports.CredentialReceipt{}, err
	}

	var exists bool
	if err := tx.QueryRow(ctx, `
SELECT EXISTS(
  SELECT 1 FROM account_appeal_credentials WHERE challenge_id=$1
)`, commit.ChallengeID).Scan(&exists); err != nil {
		return ports.CredentialReceipt{}, fmt.Errorf("read appeal challenge receipt: %w", err)
	}
	if exists {
		return ports.CredentialReceipt{}, ports.ErrRateLimited
	}
	if err := tx.QueryRow(ctx, `
SELECT EXISTS(
  SELECT 1 FROM account_appeal_credentials
  WHERE account_id=$1 AND suspension_auth_epoch=$2
    AND consumed_at IS NULL AND expires_at>$3
)`, commit.AccountID, authEpoch, commit.IssuedAt).Scan(&exists); err != nil {
		return ports.CredentialReceipt{}, fmt.Errorf("read active appeal credential: %w", err)
	}
	if exists {
		return ports.CredentialReceipt{}, ports.ErrRateLimited
	}
	var issuedInWindow int
	if err := tx.QueryRow(ctx, `
SELECT COUNT(*) FROM account_appeal_credentials
WHERE account_id=$1 AND suspension_auth_epoch=$2 AND issued_at>$3`,
		commit.AccountID,
		authEpoch,
		commit.IssuedAt.Add(-model.CredentialIssueWindow),
	).Scan(&issuedInWindow); err != nil {
		return ports.CredentialReceipt{}, fmt.Errorf("count appeal credential quota: %w", err)
	}
	if issuedInWindow >= model.CredentialIssueLimit {
		return ports.CredentialReceipt{}, ports.ErrRateLimited
	}
	_, err = tx.Exec(ctx, `
INSERT INTO account_appeal_credentials (
  credential_id, credential_digest, challenge_id, account_id,
  suspension_auth_epoch, issued_at, expires_at, delete_after
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
		commit.CredentialID,
		commit.CredentialDigest,
		commit.ChallengeID,
		commit.AccountID,
		authEpoch,
		commit.IssuedAt,
		commit.ExpiresAt,
		commit.DeleteAfter,
	)
	if isUniqueViolation(err) {
		return ports.CredentialReceipt{}, ports.ErrRateLimited
	}
	if err != nil {
		return ports.CredentialReceipt{}, fmt.Errorf("insert appeal credential: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CredentialReceipt{}, fmt.Errorf("commit appeal credential issue: %w", err)
	}
	return ports.CredentialReceipt{ExpiresAt: commit.ExpiresAt}, nil
}

func (store *PostgresStore) Submit(
	ctx context.Context,
	commit ports.SubmitCommit,
) (ports.CommandResult, error) {
	if !validDigest(commit.CredentialDigest) || !model.CanonicalIntakeRef(commit.IntakeRef) ||
		!validText(commit.IdempotencyKey, 160) || !validDigest(commit.CommandDigest) ||
		commit.SubmittedAt.IsZero() ||
		!commit.DeleteAfter.Equal(commit.SubmittedAt.Add(model.IntakeRetention)) {
		return ports.CommandResult{}, ports.ErrCredentialInvalid
	}
	commit.SubmittedAt = commit.SubmittedAt.UTC()
	commit.DeleteAfter = commit.DeleteAfter.UTC()

	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return ports.CommandResult{}, fmt.Errorf("begin appeal intake submit: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if replay, found, err := loadBySubmissionKey(
		ctx, tx, commit.IdempotencyKey,
	); err != nil {
		return ports.CommandResult{}, err
	} else if found {
		if replay.digest != commit.CommandDigest {
			return ports.CommandResult{}, ports.ErrIdempotencyConflict
		}
		if err := tx.Commit(ctx); err != nil {
			return ports.CommandResult{}, fmt.Errorf("commit appeal submission replay: %w", err)
		}
		return ports.CommandResult{Intake: replay.intake, IdempotentReplay: true}, nil
	}

	credential, found, err := loadCredentialForUpdate(ctx, tx, commit.CredentialDigest)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if !found {
		return ports.CommandResult{}, ports.ErrCredentialInvalid
	}
	if credential.consumedAt.Valid {
		// Exact retries have already been resolved through the immutable
		// submission idempotency receipt above. A different request identity
		// must never turn a consumed one-time credential into a second replay
		// channel, even when it points at the same naturally unique intake.
		return ports.CommandResult{}, ports.ErrCredentialConsumed
	}
	if !commit.SubmittedAt.Before(credential.expiresAt) {
		return ports.CommandResult{}, ports.ErrCredentialExpired
	}
	_, currentEpoch, err := lockSuspendedAccount(ctx, tx, credential.accountID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if currentEpoch != credential.authEpoch {
		return ports.CommandResult{}, ports.ErrAccountNotSuspended
	}
	if existing, found, err := loadIntakeByAccountEpoch(
		ctx, tx, credential.accountID, credential.authEpoch,
	); err != nil {
		return ports.CommandResult{}, err
	} else if found {
		if err := consumeCredential(
			ctx, tx, commit.CredentialDigest, existing.State().IntakeRef, commit.SubmittedAt,
		); err != nil {
			return ports.CommandResult{}, err
		}
		if err := tx.Commit(ctx); err != nil {
			return ports.CommandResult{}, fmt.Errorf("commit natural appeal intake replay: %w", err)
		}
		return ports.CommandResult{Intake: existing, IdempotentReplay: true}, nil
	}
	intake, err := model.NewSubmitted(model.CreateParams{
		IntakeRef: commit.IntakeRef, AccountID: credential.accountID,
		SuspensionAuthEpoch: credential.authEpoch,
		SubmittedAt:         commit.SubmittedAt, DeleteAfter: commit.DeleteAfter,
	})
	if err != nil {
		return ports.CommandResult{}, ports.ErrCredentialInvalid
	}
	state := intake.State()
	_, err = tx.Exec(ctx, `
INSERT INTO account_appeal_intakes (
  intake_ref, account_id, suspension_auth_epoch, status, submitted_at,
  delete_after, version, submission_idempotency_key, submission_digest
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
		state.IntakeRef,
		state.AccountID,
		state.SuspensionAuthEpoch,
		state.Status,
		state.SubmittedAt,
		state.DeleteAfter,
		state.Version,
		commit.IdempotencyKey,
		commit.CommandDigest,
	)
	if isUniqueViolation(err) {
		return ports.CommandResult{}, ports.ErrIdempotencyConflict
	}
	if err != nil {
		return ports.CommandResult{}, fmt.Errorf("insert account appeal intake: %w", err)
	}
	if err := consumeCredential(
		ctx, tx, commit.CredentialDigest, state.IntakeRef, commit.SubmittedAt,
	); err != nil {
		return ports.CommandResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CommandResult{}, fmt.Errorf("commit appeal intake submit: %w", err)
	}
	return ports.CommandResult{Intake: intake}, nil
}

func (store *PostgresStore) Claim(
	ctx context.Context,
	commit ports.ClaimCommit,
) (ports.CommandResult, error) {
	if !model.CanonicalIntakeRef(commit.IntakeRef) ||
		!model.CanonicalOwnerAccountID(commit.AccountID) ||
		!model.CanonicalAppealCaseID(commit.CaseID) ||
		!validText(commit.IdempotencyKey, 160) ||
		!validDigest(commit.CommandDigest) || commit.ClaimedAt.IsZero() {
		return ports.CommandResult{}, ports.ErrIntakeNotFound
	}
	commit.ClaimedAt = commit.ClaimedAt.UTC()
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return ports.CommandResult{}, fmt.Errorf("begin appeal intake claim: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var (
		receiptIntakeRef string
		receiptDigest    string
	)
	err = tx.QueryRow(ctx, `
SELECT intake_ref, claim_digest
FROM account_appeal_intakes
WHERE claim_idempotency_key=$1`, commit.IdempotencyKey).Scan(
		&receiptIntakeRef,
		&receiptDigest,
	)
	if err == nil && (receiptIntakeRef != commit.IntakeRef || receiptDigest != commit.CommandDigest) {
		return ports.CommandResult{}, ports.ErrIdempotencyConflict
	}
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return ports.CommandResult{}, fmt.Errorf("read appeal claim idempotency receipt: %w", err)
	}
	intake, found, err := loadIntake(ctx, tx, commit.IntakeRef, true)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if !found || !commit.ClaimedAt.Before(intake.State().DeleteAfter) {
		return ports.CommandResult{}, ports.ErrIntakeNotFound
	}
	next, replayed, err := intake.Claim(commit.AccountID, commit.CaseID, commit.ClaimedAt)
	switch {
	case errors.Is(err, model.ErrAccountMismatch):
		return ports.CommandResult{}, ports.ErrAccountMismatch
	case errors.Is(err, model.ErrAlreadyClaimed):
		return ports.CommandResult{}, ports.ErrIntakeClaimed
	case err != nil:
		return ports.CommandResult{}, ports.ErrIntakeNotFound
	}
	if replayed {
		if err := tx.Commit(ctx); err != nil {
			return ports.CommandResult{}, fmt.Errorf("commit appeal claim replay: %w", err)
		}
		return ports.CommandResult{Intake: next, IdempotentReplay: true}, nil
	}
	_, currentEpoch, err := lockSuspendedAccount(ctx, tx, commit.AccountID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if currentEpoch != intake.State().SuspensionAuthEpoch {
		return ports.CommandResult{}, ports.ErrAccountNotSuspended
	}
	nextState := next.State()
	tag, err := tx.Exec(ctx, `
UPDATE account_appeal_intakes
SET status=$2, claimed_case_id=$3, claimed_at=$4, version=$5,
    claim_idempotency_key=$6, claim_digest=$7
WHERE intake_ref=$1 AND status='submitted' AND version=$8`,
		nextState.IntakeRef,
		nextState.Status,
		nextState.ClaimedCaseID,
		nextState.ClaimedAt,
		nextState.Version,
		commit.IdempotencyKey,
		commit.CommandDigest,
		intake.State().Version,
	)
	if isUniqueViolation(err) {
		return ports.CommandResult{}, ports.ErrIdempotencyConflict
	}
	if err != nil {
		return ports.CommandResult{}, fmt.Errorf("update account appeal intake claim: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return ports.CommandResult{}, ports.ErrIntakeClaimed
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CommandResult{}, fmt.Errorf("commit appeal intake claim: %w", err)
	}
	return ports.CommandResult{Intake: next}, nil
}

func (store *PostgresStore) PurgeExpired(
	ctx context.Context,
	now time.Time,
) (credentials int64, intakes int64, err error) {
	if now.IsZero() {
		return 0, 0, errors.New("AccountAppealIntake purge clock is required")
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return 0, 0, fmt.Errorf("begin appeal retention purge: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	credentialTag, err := tx.Exec(ctx, `
DELETE FROM account_appeal_credentials WHERE delete_after<=$1`, now.UTC())
	if err != nil {
		return 0, 0, fmt.Errorf("purge appeal credentials: %w", err)
	}
	intakeTag, err := tx.Exec(ctx, `
DELETE FROM account_appeal_intakes WHERE delete_after<=$1`, now.UTC())
	if err != nil {
		return 0, 0, fmt.Errorf("purge appeal intakes: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return 0, 0, fmt.Errorf("commit appeal retention purge: %w", err)
	}
	return credentialTag.RowsAffected(), intakeTag.RowsAffected(), nil
}

type appealCredentialRow struct {
	accountID  string
	authEpoch  int64
	expiresAt  time.Time
	consumedAt pgtype.Timestamptz
	intakeRef  pgtype.Text
}

func loadCredentialForUpdate(
	ctx context.Context,
	tx pgx.Tx,
	digest string,
) (appealCredentialRow, bool, error) {
	var result appealCredentialRow
	err := tx.QueryRow(ctx, `
SELECT account_id, suspension_auth_epoch, expires_at, consumed_at, intake_ref
FROM account_appeal_credentials
WHERE credential_digest=$1
FOR UPDATE`, digest).Scan(
		&result.accountID,
		&result.authEpoch,
		&result.expiresAt,
		&result.consumedAt,
		&result.intakeRef,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return appealCredentialRow{}, false, nil
	}
	if err != nil {
		return appealCredentialRow{}, false, fmt.Errorf("load appeal credential: %w", err)
	}
	result.expiresAt = result.expiresAt.UTC()
	return result, true, nil
}

func consumeCredential(
	ctx context.Context,
	tx pgx.Tx,
	digest string,
	intakeRef string,
	consumedAt time.Time,
) error {
	tag, err := tx.Exec(ctx, `
UPDATE account_appeal_credentials
SET consumed_at=$2, intake_ref=$3
WHERE credential_digest=$1 AND consumed_at IS NULL`,
		digest,
		consumedAt.UTC(),
		intakeRef,
	)
	if err != nil {
		return fmt.Errorf("consume appeal credential: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return ports.ErrCredentialConsumed
	}
	return nil
}

type submissionReplay struct {
	intake model.AccountAppealIntake
	digest string
}

func loadBySubmissionKey(
	ctx context.Context,
	tx pgx.Tx,
	idempotencyKey string,
) (submissionReplay, bool, error) {
	intake, digest, found, err := scanIntake(tx.QueryRow(ctx, `
SELECT intake_ref, account_id, suspension_auth_epoch, status, submitted_at,
       claimed_case_id, claimed_at, delete_after, version, submission_digest
FROM account_appeal_intakes
WHERE submission_idempotency_key=$1
FOR UPDATE`, idempotencyKey))
	if err != nil || !found {
		return submissionReplay{}, found, err
	}
	return submissionReplay{intake: intake, digest: digest}, true, nil
}

func loadIntake(
	ctx context.Context,
	tx pgx.Tx,
	intakeRef string,
	forUpdate bool,
) (model.AccountAppealIntake, bool, error) {
	query := `
SELECT intake_ref, account_id, suspension_auth_epoch, status, submitted_at,
       claimed_case_id, claimed_at, delete_after, version, submission_digest
FROM account_appeal_intakes
WHERE intake_ref=$1`
	if forUpdate {
		query += " FOR UPDATE"
	}
	intake, _, found, err := scanIntake(tx.QueryRow(ctx, query, intakeRef))
	return intake, found, err
}

func loadIntakeByAccountEpoch(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	authEpoch int64,
) (model.AccountAppealIntake, bool, error) {
	intake, _, found, err := scanIntake(tx.QueryRow(ctx, `
SELECT intake_ref, account_id, suspension_auth_epoch, status, submitted_at,
       claimed_case_id, claimed_at, delete_after, version, submission_digest
FROM account_appeal_intakes
WHERE account_id=$1 AND suspension_auth_epoch=$2
FOR UPDATE`, accountID, authEpoch))
	return intake, found, err
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanIntake(
	row rowScanner,
) (model.AccountAppealIntake, string, bool, error) {
	var (
		state            model.State
		claimedCaseID    pgtype.Text
		claimedAt        pgtype.Timestamptz
		submissionDigest string
	)
	err := row.Scan(
		&state.IntakeRef,
		&state.AccountID,
		&state.SuspensionAuthEpoch,
		&state.Status,
		&state.SubmittedAt,
		&claimedCaseID,
		&claimedAt,
		&state.DeleteAfter,
		&state.Version,
		&submissionDigest,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.AccountAppealIntake{}, "", false, nil
	}
	if err != nil {
		return model.AccountAppealIntake{}, "", false, fmt.Errorf("scan account appeal intake: %w", err)
	}
	if claimedCaseID.Valid {
		state.ClaimedCaseID = claimedCaseID.String
	}
	if claimedAt.Valid {
		value := claimedAt.Time.UTC()
		state.ClaimedAt = &value
	}
	intake, err := model.Restore(state)
	if err != nil {
		return model.AccountAppealIntake{}, "", false, fmt.Errorf("restore account appeal intake: %w", err)
	}
	return intake, submissionDigest, true, nil
}

func lockSuspendedAccount(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
) (state string, authEpoch int64, err error) {
	err = tx.QueryRow(ctx, `
SELECT account_state, auth_epoch
FROM user_profiles
WHERE user_id=$1
FOR UPDATE`, accountID).Scan(&state, &authEpoch)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", 0, ports.ErrAccountNotSuspended
	}
	if err != nil {
		return "", 0, fmt.Errorf("lock appeal UserAccount security state: %w", err)
	}
	if state != "suspended" || authEpoch <= 0 {
		return "", 0, ports.ErrAccountNotSuspended
	}
	return state, authEpoch, nil
}

func validText(value string, maxLength int) bool {
	return value != "" && value == strings.TrimSpace(value) && len(value) <= maxLength
}

func validDigest(value string) bool {
	if len(value) != 64 {
		return false
	}
	for _, current := range value {
		if current < '0' || current > '9' {
			if current < 'a' || current > 'f' {
				return false
			}
		}
	}
	return true
}

func isUniqueViolation(err error) bool {
	var postgresError *pgconn.PgError
	return errors.As(err, &postgresError) && postgresError.Code == "23505"
}

var _ ports.Store = (*PostgresStore)(nil)
