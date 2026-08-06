package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/ports"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

var _ ports.CaseStore = (*PostgresStore)(nil)
var _ ports.DeliveryStore = (*PostgresStore)(nil)

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("account enforcement postgres pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

func (store *PostgresStore) EnsureSchema(ctx context.Context) error {
	statements := []string{
		`CREATE TABLE IF NOT EXISTS account_enforcement_cases (
  id VARCHAR(128) PRIMARY KEY,
  case_kind VARCHAR(32) NOT NULL CHECK (case_kind IN ('moderation','appeal')),
  account_id VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL CHECK (status IN ('pending_approval','approved','rejected')),
  policy_ref VARCHAR(256),
  source_decision_id VARCHAR(128),
  intake_ref VARCHAR(256),
  evidence_refs JSONB NOT NULL,
  opened_by VARCHAR(160) NOT NULL,
  version BIGINT NOT NULL CHECK (version > 0),
  opened_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CHECK (
    (case_kind='moderation' AND policy_ref IS NOT NULL AND source_decision_id IS NULL AND intake_ref IS NULL) OR
    (case_kind='appeal' AND policy_ref IS NULL AND source_decision_id IS NOT NULL AND intake_ref IS NOT NULL)
  )
)`,
		`CREATE UNIQUE INDEX IF NOT EXISTS uq_account_enforcement_pending_account
ON account_enforcement_cases(account_id) WHERE status='pending_approval'`,
		`CREATE INDEX IF NOT EXISTS idx_account_enforcement_case_status_updated
ON account_enforcement_cases(status, updated_at)`,
		`CREATE TABLE IF NOT EXISTS account_enforcement_case_reviews (
  case_id VARCHAR(128) NOT NULL REFERENCES account_enforcement_cases(id) ON DELETE RESTRICT,
  reviewer_id VARCHAR(160) NOT NULL,
  verdict VARCHAR(16) NOT NULL CHECK (verdict IN ('approve','reject')),
  reviewed_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(case_id, reviewer_id)
)`,
		`CREATE TABLE IF NOT EXISTS account_enforcement_decisions (
  decision_id VARCHAR(128) PRIMARY KEY,
  decision_sequence BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
  case_id VARCHAR(128) NOT NULL UNIQUE REFERENCES account_enforcement_cases(id) ON DELETE RESTRICT,
  account_id VARCHAR(128) NOT NULL,
  action VARCHAR(16) NOT NULL CHECK (action IN ('suspend','restore')),
  case_ref VARCHAR(256) NOT NULL,
  decision_digest VARCHAR(64) NOT NULL,
  approved_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
)`,
		`CREATE TABLE IF NOT EXISTS account_enforcement_command_receipts (
  idempotency_key VARCHAR(160) PRIMARY KEY,
  command_digest VARCHAR(64) NOT NULL,
  case_id VARCHAR(128) NOT NULL REFERENCES account_enforcement_cases(id) ON DELETE RESTRICT,
  result_version BIGINT NOT NULL,
  result_snapshot JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
)`,
		`CREATE TABLE IF NOT EXISTS account_enforcement_delivery_outbox (
  decision_id VARCHAR(128) PRIMARY KEY REFERENCES account_enforcement_decisions(decision_id) ON DELETE RESTRICT,
  status VARCHAR(32) NOT NULL CHECK (status IN ('pending','retrying','delivered','dead_letter')),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  retry_generation INTEGER NOT NULL DEFAULT 0 CHECK (retry_generation >= 0),
  next_attempt_at TIMESTAMPTZ NOT NULL,
  lease_owner VARCHAR(160),
  leased_until TIMESTAMPTZ,
  last_error_class VARCHAR(64) NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
)`,
		`CREATE INDEX IF NOT EXISTS idx_account_enforcement_delivery_due
ON account_enforcement_delivery_outbox(status, next_attempt_at, created_at)`,
		`CREATE TABLE IF NOT EXISTS account_enforcement_delivery_receipts (
  decision_id VARCHAR(128) PRIMARY KEY REFERENCES account_enforcement_decisions(decision_id) ON DELETE RESTRICT,
  account_state VARCHAR(32) NOT NULL,
  auth_epoch BIGINT NOT NULL,
  remote_idempotent_replay BOOLEAN NOT NULL,
  remote_occurred_at TIMESTAMPTZ NOT NULL,
  delivered_at TIMESTAMPTZ NOT NULL
)`,
		`CREATE TABLE IF NOT EXISTS account_enforcement_delivery_dead_letters (
  decision_id VARCHAR(128) NOT NULL REFERENCES account_enforcement_decisions(decision_id) ON DELETE RESTRICT,
  retry_generation INTEGER NOT NULL,
  error_class VARCHAR(64) NOT NULL,
  attempt_count INTEGER NOT NULL,
  failed_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(decision_id, retry_generation)
)`,
	}
	for _, statement := range statements {
		if _, err := store.pool.Exec(ctx, statement); err != nil {
			return fmt.Errorf("ensure account enforcement schema: %w", err)
		}
	}
	return nil
}

func (store *PostgresStore) Replay(
	ctx context.Context,
	idempotencyKey string,
	commandDigest string,
) (ports.CaseSnapshot, bool, error) {
	return replayWith(ctx, store.pool, idempotencyKey, commandDigest)
}

func (store *PostgresStore) CommitOpen(
	ctx context.Context,
	current model.Case,
	receipt ports.CommandReceipt,
) (ports.CaseSnapshot, error) {
	if err := current.Validate(); err != nil || current.Version != 1 ||
		receipt.CaseID != current.ID || receipt.ResultVersion != current.Version {
		return ports.CaseSnapshot{}, model.ErrInvalidArgument
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.Serializable})
	if err != nil {
		return ports.CaseSnapshot{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if err := lockTransactionKey(ctx, tx, "idempotency:"+receipt.IdempotencyKey); err != nil {
		return ports.CaseSnapshot{}, err
	}
	if err := lockTransactionKey(ctx, tx, "account:"+current.AccountID); err != nil {
		return ports.CaseSnapshot{}, err
	}
	if replay, found, replayErr := replayWith(ctx, tx, receipt.IdempotencyKey, receipt.CommandDigest); replayErr != nil {
		return ports.CaseSnapshot{}, replayErr
	} else if found {
		if err := tx.Commit(ctx); err != nil {
			return ports.CaseSnapshot{}, err
		}
		return replay, nil
	}
	if err := ensureCaseCanOpen(ctx, tx, current); err != nil {
		return ports.CaseSnapshot{}, err
	}
	evidence, err := json.Marshal(current.EvidenceRefs)
	if err != nil {
		return ports.CaseSnapshot{}, model.ErrInvalidArgument
	}
	_, err = tx.Exec(ctx, `
INSERT INTO account_enforcement_cases(
  id, case_kind, account_id, status, policy_ref, source_decision_id,
  intake_ref, evidence_refs, opened_by, version, opened_at, updated_at
) VALUES ($1,$2,$3,$4,NULLIF($5,''),NULLIF($6,''),NULLIF($7,''),$8,$9,$10,$11,$12)`,
		current.ID, current.Kind, current.AccountID, current.Status, current.PolicyRef,
		current.SourceDecisionID, current.IntakeRef, evidence, current.OpenedBy,
		current.Version, current.OpenedAt, current.UpdatedAt,
	)
	if err != nil {
		return ports.CaseSnapshot{}, mapConstraintError(err)
	}
	if err := insertCommandReceipt(ctx, tx, receipt, current); err != nil {
		if isReceiptConflict(err) {
			_ = tx.Rollback(ctx)
			return store.replayAfterConflict(ctx, receipt)
		}
		return ports.CaseSnapshot{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CaseSnapshot{}, err
	}
	return ports.CaseSnapshot{Case: current}, nil
}

func (store *PostgresStore) Load(ctx context.Context, caseID string) (model.Case, error) {
	return loadCase(ctx, store.pool, strings.TrimSpace(caseID))
}

func (store *PostgresStore) CommitReview(
	ctx context.Context,
	expectedVersion int64,
	next model.Case,
	review model.Review,
	decision *model.Decision,
	receipt ports.CommandReceipt,
) (ports.CaseSnapshot, error) {
	if err := next.Validate(); err != nil || expectedVersion <= 0 ||
		next.Version != expectedVersion+1 || receipt.CaseID != next.ID ||
		receipt.ResultVersion != next.Version || review.ReviewerID == "" {
		return ports.CaseSnapshot{}, model.ErrInvalidArgument
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.Serializable})
	if err != nil {
		return ports.CaseSnapshot{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if err := lockTransactionKey(ctx, tx, "idempotency:"+receipt.IdempotencyKey); err != nil {
		return ports.CaseSnapshot{}, err
	}
	if err := lockTransactionKey(ctx, tx, "case:"+next.ID); err != nil {
		return ports.CaseSnapshot{}, err
	}
	if replay, found, replayErr := replayWith(ctx, tx, receipt.IdempotencyKey, receipt.CommandDigest); replayErr != nil {
		return ports.CaseSnapshot{}, replayErr
	} else if found {
		if err := tx.Commit(ctx); err != nil {
			return ports.CaseSnapshot{}, err
		}
		return replay, nil
	}
	var storedVersion int64
	var storedStatus string
	err = tx.QueryRow(ctx, `
SELECT version, status FROM account_enforcement_cases WHERE id=$1 FOR UPDATE`, next.ID).
		Scan(&storedVersion, &storedStatus)
	if errors.Is(err, pgx.ErrNoRows) {
		return ports.CaseSnapshot{}, model.ErrCaseNotFound
	}
	if err != nil {
		return ports.CaseSnapshot{}, err
	}
	if storedVersion != expectedVersion {
		return ports.CaseSnapshot{}, model.ErrVersionConflict
	}
	if model.CaseStatus(storedStatus) != model.CaseStatusPendingApproval {
		return ports.CaseSnapshot{}, model.ErrCaseClosed
	}
	if decision != nil {
		if next.Status != model.CaseStatusApproved || decision.CaseID != next.ID ||
			decision.AccountID != next.AccountID {
			return ports.CaseSnapshot{}, model.ErrInvalidArgument
		}
		if err := ensureDecisionCanIssue(ctx, tx, next); err != nil {
			return ports.CaseSnapshot{}, err
		}
	}
	_, err = tx.Exec(ctx, `
INSERT INTO account_enforcement_case_reviews(case_id, reviewer_id, verdict, reviewed_at)
VALUES ($1,$2,$3,$4)`, next.ID, review.ReviewerID, review.Verdict, review.ReviewedAt)
	if err != nil {
		if isUniqueViolation(err) {
			return ports.CaseSnapshot{}, model.ErrReviewConflict
		}
		return ports.CaseSnapshot{}, err
	}
	commandTag, err := tx.Exec(ctx, `
UPDATE account_enforcement_cases
SET status=$3, version=$4, updated_at=$5
WHERE id=$1 AND version=$2`, next.ID, expectedVersion, next.Status, next.Version, next.UpdatedAt)
	if err != nil {
		return ports.CaseSnapshot{}, err
	}
	if commandTag.RowsAffected() != 1 {
		return ports.CaseSnapshot{}, model.ErrVersionConflict
	}
	if decision != nil {
		if _, err := tx.Exec(ctx, `
INSERT INTO account_enforcement_decisions(
  decision_id, case_id, account_id, action, case_ref, decision_digest, approved_at, created_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$7)`, decision.ID, decision.CaseID,
			decision.AccountID, decision.Action, decision.CaseRef,
			decision.DecisionDigest, decision.ApprovedAt); err != nil {
			return ports.CaseSnapshot{}, mapConstraintError(err)
		}
		if _, err := tx.Exec(ctx, `
INSERT INTO account_enforcement_delivery_outbox(
  decision_id, status, attempts, retry_generation, next_attempt_at,
  lease_owner, leased_until, last_error_class, created_at, updated_at
) VALUES ($1,'pending',0,0,$2,NULL,NULL,'',$2,$2)`, decision.ID, decision.ApprovedAt); err != nil {
			return ports.CaseSnapshot{}, mapConstraintError(err)
		}
	}
	if err := insertCommandReceipt(ctx, tx, receipt, next); err != nil {
		if isReceiptConflict(err) {
			_ = tx.Rollback(ctx)
			return store.replayAfterConflict(ctx, receipt)
		}
		return ports.CaseSnapshot{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CaseSnapshot{}, err
	}
	return ports.CaseSnapshot{Case: next}, nil
}

func (store *PostgresStore) RecoverDelivery(
	ctx context.Context,
	caseID string,
	receipt ports.CommandReceipt,
	recoveredAt time.Time,
) (ports.CaseSnapshot, error) {
	caseID = strings.TrimSpace(caseID)
	if caseID == "" || receipt.CaseID != caseID || recoveredAt.IsZero() {
		return ports.CaseSnapshot{}, model.ErrInvalidArgument
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.Serializable})
	if err != nil {
		return ports.CaseSnapshot{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if err := lockTransactionKey(ctx, tx, "idempotency:"+receipt.IdempotencyKey); err != nil {
		return ports.CaseSnapshot{}, err
	}
	if err := lockTransactionKey(ctx, tx, "case:"+caseID); err != nil {
		return ports.CaseSnapshot{}, err
	}
	if replay, found, replayErr := replayWith(ctx, tx, receipt.IdempotencyKey, receipt.CommandDigest); replayErr != nil {
		return ports.CaseSnapshot{}, replayErr
	} else if found {
		if err := tx.Commit(ctx); err != nil {
			return ports.CaseSnapshot{}, err
		}
		return replay, nil
	}
	var storedVersion int64
	var status string
	var decisionID, accountID string
	err = tx.QueryRow(ctx, `
SELECT c.version, c.status, d.decision_id, d.account_id
FROM account_enforcement_cases c
JOIN account_enforcement_decisions d ON d.case_id=c.id
WHERE c.id=$1 FOR UPDATE OF c`, caseID).
		Scan(&storedVersion, &status, &decisionID, &accountID)
	if errors.Is(err, pgx.ErrNoRows) {
		return ports.CaseSnapshot{}, model.ErrCaseNotFound
	}
	if err != nil {
		return ports.CaseSnapshot{}, err
	}
	if model.CaseStatus(status) != model.CaseStatusApproved {
		return ports.CaseSnapshot{}, model.ErrDeliveryNotRecoverable
	}
	if err := ensureLatestDecision(ctx, tx, accountID, decisionID); err != nil {
		return ports.CaseSnapshot{}, err
	}
	commandTag, err := tx.Exec(ctx, `
UPDATE account_enforcement_delivery_outbox
SET status='pending', attempts=0, retry_generation=retry_generation+1,
    next_attempt_at=$2, lease_owner=NULL, leased_until=NULL,
    last_error_class='', updated_at=$2
WHERE decision_id=$1 AND status='dead_letter'`, decisionID, recoveredAt.UTC())
	if err != nil {
		return ports.CaseSnapshot{}, err
	}
	if commandTag.RowsAffected() != 1 {
		return ports.CaseSnapshot{}, model.ErrDeliveryNotRecoverable
	}
	commandTag, err = tx.Exec(ctx, `
UPDATE account_enforcement_cases SET version=version+1, updated_at=$3
WHERE id=$1 AND version=$2`, caseID, storedVersion, recoveredAt.UTC())
	if err != nil {
		return ports.CaseSnapshot{}, err
	}
	if commandTag.RowsAffected() != 1 {
		return ports.CaseSnapshot{}, model.ErrVersionConflict
	}
	receipt.ResultVersion = storedVersion + 1
	recovered, err := loadCase(ctx, tx, caseID)
	if err != nil {
		return ports.CaseSnapshot{}, err
	}
	if err := insertCommandReceipt(ctx, tx, receipt, recovered); err != nil {
		if isReceiptConflict(err) {
			_ = tx.Rollback(ctx)
			return store.replayAfterConflict(ctx, receipt)
		}
		return ports.CaseSnapshot{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CaseSnapshot{}, err
	}
	return ports.CaseSnapshot{Case: recovered}, nil
}

func (store *PostgresStore) ClaimPendingOutbox(
	ctx context.Context,
	owner string,
	now time.Time,
	leaseDuration time.Duration,
	limit int,
) ([]ports.DeliveryJob, error) {
	owner = strings.TrimSpace(owner)
	if owner == "" || now.IsZero() || leaseDuration <= 0 || limit < 1 {
		return nil, model.ErrInvalidArgument
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	rows, err := tx.Query(ctx, `
SELECT d.decision_id, d.case_id, d.account_id, d.action, d.case_ref,
       d.decision_digest, d.approved_at, o.attempts, o.retry_generation
FROM account_enforcement_delivery_outbox o
JOIN account_enforcement_decisions d ON d.decision_id=o.decision_id
WHERE o.status IN ('pending','retrying')
  AND o.next_attempt_at <= $1
  AND (o.leased_until IS NULL OR o.leased_until <= $1)
ORDER BY o.created_at, o.decision_id
FOR UPDATE OF o SKIP LOCKED
LIMIT $2`, now.UTC(), limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	jobs := make([]ports.DeliveryJob, 0, limit)
	for rows.Next() {
		var job ports.DeliveryJob
		var action string
		if err := rows.Scan(
			&job.Decision.ID,
			&job.Decision.CaseID,
			&job.Decision.AccountID,
			&action,
			&job.Decision.CaseRef,
			&job.Decision.DecisionDigest,
			&job.Decision.ApprovedAt,
			&job.Attempts,
			&job.RetryGeneration,
		); err != nil {
			return nil, err
		}
		job.Decision.Action = model.EnforcementAction(action)
		jobs = append(jobs, job)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	rows.Close()
	for _, job := range jobs {
		if _, err := tx.Exec(ctx, `
UPDATE account_enforcement_delivery_outbox
SET status='retrying', lease_owner=$2, leased_until=$3, updated_at=$4
WHERE decision_id=$1`, job.Decision.ID, owner, now.UTC().Add(leaseDuration), now.UTC()); err != nil {
			return nil, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	return jobs, nil
}

func (store *PostgresStore) MarkDispatched(
	ctx context.Context,
	owner string,
	receipt ports.DeliveryReceipt,
) error {
	owner = strings.TrimSpace(owner)
	if owner == "" || receipt.DecisionID == "" || receipt.AuthEpoch <= 0 ||
		receipt.OccurredAt.IsZero() || receipt.DeliveredAt.IsZero() {
		return model.ErrInvalidArgument
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var status, leaseOwner, action string
	err = tx.QueryRow(ctx, `
SELECT o.status, COALESCE(o.lease_owner,''), d.action
FROM account_enforcement_delivery_outbox o
JOIN account_enforcement_decisions d ON d.decision_id=o.decision_id
WHERE o.decision_id=$1 FOR UPDATE OF o`, receipt.DecisionID).
		Scan(&status, &leaseOwner, &action)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.ErrSourceDecisionConflict
	}
	if err != nil {
		return err
	}
	if status == string(model.DeliveryStatusDelivered) {
		return tx.Commit(ctx)
	}
	if status != string(model.DeliveryStatusRetrying) || leaseOwner != owner {
		return model.ErrSourceDecisionConflict
	}
	if (action == string(model.EnforcementActionSuspend) && receipt.AccountState != "suspended") ||
		(action == string(model.EnforcementActionRestore) && receipt.AccountState != "active") {
		return model.ErrSourceDecisionConflict
	}
	_, err = tx.Exec(ctx, `
INSERT INTO account_enforcement_delivery_receipts(
  decision_id, account_state, auth_epoch, remote_idempotent_replay,
  remote_occurred_at, delivered_at
) VALUES ($1,$2,$3,$4,$5,$6)
ON CONFLICT (decision_id) DO NOTHING`, receipt.DecisionID, receipt.AccountState,
		receipt.AuthEpoch, receipt.IdempotentReplay, receipt.OccurredAt.UTC(), receipt.DeliveredAt.UTC())
	if err != nil {
		return err
	}
	commandTag, err := tx.Exec(ctx, `
UPDATE account_enforcement_delivery_outbox
SET status='delivered', lease_owner=NULL, leased_until=NULL,
    last_error_class='', updated_at=$3
WHERE decision_id=$1 AND lease_owner=$2`, receipt.DecisionID, owner, receipt.DeliveredAt.UTC())
	if err != nil {
		return err
	}
	if commandTag.RowsAffected() != 1 {
		return model.ErrSourceDecisionConflict
	}
	return tx.Commit(ctx)
}

func (store *PostgresStore) MarkFailed(
	ctx context.Context,
	owner string,
	job ports.DeliveryJob,
	errorClass string,
	permanent bool,
	maxAttempts int,
	nextAttemptAt time.Time,
	failedAt time.Time,
) (model.DeliveryStatus, error) {
	owner = strings.TrimSpace(owner)
	errorClass = normalizedErrorClass(errorClass)
	if owner == "" || job.Decision.ID == "" || maxAttempts < 1 ||
		nextAttemptAt.IsZero() || failedAt.IsZero() {
		return "", model.ErrInvalidArgument
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return "", err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	var status, leaseOwner string
	var attempts, retryGeneration int
	err = tx.QueryRow(ctx, `
SELECT status, COALESCE(lease_owner,''), attempts, retry_generation
FROM account_enforcement_delivery_outbox WHERE decision_id=$1 FOR UPDATE`, job.Decision.ID).
		Scan(&status, &leaseOwner, &attempts, &retryGeneration)
	if err != nil {
		return "", err
	}
	if status != string(model.DeliveryStatusRetrying) || leaseOwner != owner ||
		attempts != job.Attempts || retryGeneration != job.RetryGeneration {
		return "", model.ErrSourceDecisionConflict
	}
	attempts++
	nextStatus := model.DeliveryStatusRetrying
	if permanent || attempts >= maxAttempts {
		nextStatus = model.DeliveryStatusDeadLetter
	}
	_, err = tx.Exec(ctx, `
UPDATE account_enforcement_delivery_outbox
SET status=$3, attempts=$4, next_attempt_at=$5, lease_owner=NULL,
    leased_until=NULL, last_error_class=$6, updated_at=$7
WHERE decision_id=$1 AND lease_owner=$2`, job.Decision.ID, owner, nextStatus,
		attempts, nextAttemptAt.UTC(), errorClass, failedAt.UTC())
	if err != nil {
		return "", err
	}
	if nextStatus == model.DeliveryStatusDeadLetter {
		_, err = tx.Exec(ctx, `
INSERT INTO account_enforcement_delivery_dead_letters(
  decision_id, retry_generation, error_class, attempt_count, failed_at
) VALUES ($1,$2,$3,$4,$5)
ON CONFLICT (decision_id, retry_generation) DO NOTHING`, job.Decision.ID,
			retryGeneration, errorClass, attempts, failedAt.UTC())
		if err != nil {
			return "", err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return "", err
	}
	return nextStatus, nil
}

func (store *PostgresStore) Backlog(
	ctx context.Context,
	now time.Time,
) (ports.DeliveryBacklog, error) {
	_ = now
	var backlog ports.DeliveryBacklog
	var oldest *time.Time
	err := store.pool.QueryRow(ctx, `
SELECT
  COUNT(*) FILTER (WHERE status='pending'),
  COUNT(*) FILTER (WHERE status='retrying'),
  COUNT(*) FILTER (WHERE status='dead_letter'),
  MIN(created_at) FILTER (WHERE status IN ('pending','retrying'))
FROM account_enforcement_delivery_outbox`).
		Scan(&backlog.Pending, &backlog.Retrying, &backlog.DeadLetter, &oldest)
	if err != nil {
		return ports.DeliveryBacklog{}, err
	}
	backlog.OldestDue = oldest
	return backlog, nil
}

func ensureCaseCanOpen(ctx context.Context, tx pgx.Tx, current model.Case) error {
	var unresolved int
	if err := tx.QueryRow(ctx, `
SELECT COUNT(*)
FROM account_enforcement_decisions d
JOIN account_enforcement_delivery_outbox o ON o.decision_id=d.decision_id
WHERE d.account_id=$1 AND o.status IN ('pending','retrying','dead_letter')`, current.AccountID).
		Scan(&unresolved); err != nil {
		return err
	}
	if unresolved > 0 {
		return model.ErrSourceDecisionConflict
	}
	latestID, latestAction, found, err := latestDeliveredDecision(ctx, tx, current.AccountID)
	if err != nil {
		return err
	}
	switch current.Kind {
	case model.CaseKindModeration:
		if found && latestAction == model.EnforcementActionSuspend {
			return model.ErrSourceDecisionConflict
		}
	case model.CaseKindAppeal:
		if !found || latestID != current.SourceDecisionID ||
			latestAction != model.EnforcementActionSuspend {
			return model.ErrSourceDecisionConflict
		}
	default:
		return model.ErrInvalidArgument
	}
	return nil
}

func ensureDecisionCanIssue(ctx context.Context, tx pgx.Tx, current model.Case) error {
	return ensureCaseCanOpen(ctx, tx, current)
}

func ensureLatestDecision(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	decisionID string,
) error {
	var latest string
	err := tx.QueryRow(ctx, `
SELECT decision_id FROM account_enforcement_decisions
WHERE account_id=$1 ORDER BY decision_sequence DESC LIMIT 1`, accountID).Scan(&latest)
	if errors.Is(err, pgx.ErrNoRows) || latest != decisionID {
		return model.ErrSourceDecisionConflict
	}
	return err
}

func latestDeliveredDecision(
	ctx context.Context,
	query rowQuerier,
	accountID string,
) (string, model.EnforcementAction, bool, error) {
	var decisionID, action string
	err := query.QueryRow(ctx, `
SELECT d.decision_id, d.action
FROM account_enforcement_decisions d
JOIN account_enforcement_delivery_receipts r ON r.decision_id=d.decision_id
WHERE d.account_id=$1
ORDER BY d.decision_sequence DESC
LIMIT 1`, accountID).Scan(&decisionID, &action)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", "", false, nil
	}
	if err != nil {
		return "", "", false, err
	}
	return decisionID, model.EnforcementAction(action), true, nil
}

func replayWith(
	ctx context.Context,
	query fullQuerier,
	idempotencyKey string,
	commandDigest string,
) (ports.CaseSnapshot, bool, error) {
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	commandDigest = strings.TrimSpace(commandDigest)
	if idempotencyKey == "" || commandDigest == "" {
		return ports.CaseSnapshot{}, false, model.ErrInvalidArgument
	}
	var storedDigest, caseID string
	var resultPayload []byte
	err := query.QueryRow(ctx, `
SELECT command_digest, case_id, result_snapshot FROM account_enforcement_command_receipts
WHERE idempotency_key=$1`, idempotencyKey).Scan(&storedDigest, &caseID, &resultPayload)
	if errors.Is(err, pgx.ErrNoRows) {
		return ports.CaseSnapshot{}, false, nil
	}
	if err != nil {
		return ports.CaseSnapshot{}, false, err
	}
	if storedDigest != commandDigest {
		return ports.CaseSnapshot{}, false, model.ErrIdempotencyConflict
	}
	var result ports.CommandResult
	if err := json.Unmarshal(resultPayload, &result); err != nil {
		return ports.CaseSnapshot{}, false, fmt.Errorf("decode account enforcement command result: %w", err)
	}
	if !validCommandResult(result, caseID) {
		return ports.CaseSnapshot{}, false, errors.New("account enforcement command result is invalid")
	}
	return ports.CaseSnapshot{CommandResult: &result, IdempotentReplay: true}, true, nil
}

func loadCase(ctx context.Context, query fullQuerier, caseID string) (model.Case, error) {
	if caseID == "" {
		return model.Case{}, model.ErrInvalidArgument
	}
	var current model.Case
	var kind, status string
	var evidence []byte
	err := query.QueryRow(ctx, `
SELECT id, case_kind, account_id, status, COALESCE(policy_ref,''),
       COALESCE(source_decision_id,''), COALESCE(intake_ref,''), evidence_refs,
       opened_by, version, opened_at, updated_at
FROM account_enforcement_cases WHERE id=$1`, caseID).Scan(
		&current.ID, &kind, &current.AccountID, &status, &current.PolicyRef,
		&current.SourceDecisionID, &current.IntakeRef, &evidence, &current.OpenedBy,
		&current.Version, &current.OpenedAt, &current.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.Case{}, model.ErrCaseNotFound
	}
	if err != nil {
		return model.Case{}, err
	}
	current.Kind = model.CaseKind(kind)
	current.Status = model.CaseStatus(status)
	if err := json.Unmarshal(evidence, &current.EvidenceRefs); err != nil {
		return model.Case{}, err
	}
	rows, err := query.Query(ctx, `
SELECT reviewer_id, verdict, reviewed_at
FROM account_enforcement_case_reviews WHERE case_id=$1 ORDER BY reviewed_at, reviewer_id`, caseID)
	if err != nil {
		return model.Case{}, err
	}
	for rows.Next() {
		var review model.Review
		var verdict string
		if err := rows.Scan(&review.ReviewerID, &verdict, &review.ReviewedAt); err != nil {
			rows.Close()
			return model.Case{}, err
		}
		review.Verdict = model.ReviewVerdict(verdict)
		current.Reviews = append(current.Reviews, review)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return model.Case{}, err
	}
	rows.Close()
	var decision model.Decision
	var action, deliveryStatus string
	var retryGeneration int
	err = query.QueryRow(ctx, `
SELECT d.decision_id, d.case_id, d.account_id, d.action, d.case_ref,
	   d.decision_digest, d.approved_at, o.status, o.retry_generation
FROM account_enforcement_decisions d
JOIN account_enforcement_delivery_outbox o ON o.decision_id=d.decision_id
WHERE d.case_id=$1`, caseID).Scan(
		&decision.ID, &decision.CaseID, &decision.AccountID, &action,
		&decision.CaseRef, &decision.DecisionDigest, &decision.ApprovedAt, &deliveryStatus,
		&retryGeneration,
	)
	if err == nil {
		decision.Action = model.EnforcementAction(action)
		current.Decision = &decision
		current.DeliveryStatus = model.DeliveryStatus(deliveryStatus)
	} else if !errors.Is(err, pgx.ErrNoRows) {
		return model.Case{}, err
	}
	if err := validateLoadedCase(current, retryGeneration); err != nil {
		return model.Case{}, err
	}
	return current, nil
}

func validateLoadedCase(current model.Case, retryGeneration int) error {
	if err := current.Validate(); err != nil || retryGeneration < 0 ||
		current.Version != 1+int64(len(current.Reviews))+int64(retryGeneration) {
		return errors.New("stored account enforcement case invariant is invalid")
	}
	approvals := 0
	rejected := false
	reviewers := make(map[string]struct{}, len(current.Reviews))
	for _, review := range current.Reviews {
		if strings.TrimSpace(review.ReviewerID) == "" || review.ReviewedAt.IsZero() {
			return errors.New("stored account enforcement review is invalid")
		}
		if _, exists := reviewers[review.ReviewerID]; exists {
			return errors.New("stored account enforcement reviewer is duplicated")
		}
		reviewers[review.ReviewerID] = struct{}{}
		switch review.Verdict {
		case model.ReviewVerdictApprove:
			approvals++
		case model.ReviewVerdictReject:
			rejected = true
		default:
			return errors.New("stored account enforcement verdict is invalid")
		}
	}
	switch current.Status {
	case model.CaseStatusPendingApproval:
		if rejected || approvals > 1 || current.Decision != nil || current.DeliveryStatus != "" {
			return errors.New("stored pending account enforcement case is invalid")
		}
	case model.CaseStatusRejected:
		if !rejected || approvals > 1 || len(current.Reviews) > 2 ||
			current.Decision != nil || current.DeliveryStatus != "" {
			return errors.New("stored rejected account enforcement case is invalid")
		}
	case model.CaseStatusApproved:
		if rejected || approvals != 2 || len(current.Reviews) != 2 || current.Decision == nil {
			return errors.New("stored approved account enforcement case is invalid")
		}
		decision := current.Decision
		expectedAction := model.EnforcementActionSuspend
		if current.Kind == model.CaseKindAppeal {
			expectedAction = model.EnforcementActionRestore
		}
		if decision.CaseID != current.ID || decision.AccountID != current.AccountID ||
			decision.Action != expectedAction || decision.CaseRef != "ops.account_enforcement_case/"+current.ID ||
			len(decision.DecisionDigest) != 64 || decision.ApprovedAt.IsZero() {
			return errors.New("stored account enforcement decision is invalid")
		}
		switch current.DeliveryStatus {
		case model.DeliveryStatusPending, model.DeliveryStatusRetrying,
			model.DeliveryStatusDelivered, model.DeliveryStatusDeadLetter:
		default:
			return errors.New("stored account enforcement delivery status is invalid")
		}
	default:
		return errors.New("stored account enforcement status is invalid")
	}
	return nil
}

func insertCommandReceipt(
	ctx context.Context,
	tx pgx.Tx,
	receipt ports.CommandReceipt,
	current model.Case,
) error {
	if strings.TrimSpace(receipt.IdempotencyKey) == "" ||
		strings.TrimSpace(receipt.CommandDigest) == "" || receipt.CaseID == "" ||
		receipt.ResultVersion <= 0 || receipt.CreatedAt.IsZero() ||
		receipt.CaseID != current.ID || receipt.ResultVersion != current.Version {
		return model.ErrInvalidArgument
	}
	resultPayload, err := json.Marshal(commandResultFromCase(current))
	if err != nil {
		return model.ErrInvalidArgument
	}
	_, err = tx.Exec(ctx, `
INSERT INTO account_enforcement_command_receipts(
  idempotency_key, command_digest, case_id, result_version, result_snapshot, created_at
) VALUES ($1,$2,$3,$4,$5,$6)`, receipt.IdempotencyKey, receipt.CommandDigest,
		receipt.CaseID, receipt.ResultVersion, resultPayload, receipt.CreatedAt.UTC())
	return err
}

func commandResultFromCase(current model.Case) ports.CommandResult {
	result := ports.CommandResult{
		CaseID:         current.ID,
		CaseKind:       current.Kind,
		Status:         current.Status,
		Version:        current.Version,
		DeliveryStatus: current.DeliveryStatus,
		UpdatedAt:      current.UpdatedAt.UTC(),
	}
	for _, review := range current.Reviews {
		if review.Verdict == model.ReviewVerdictApprove {
			result.ApprovalCount++
		}
	}
	if current.Decision != nil {
		result.DecisionID = current.Decision.ID
	}
	return result
}

func validCommandResult(result ports.CommandResult, caseID string) bool {
	if result.CaseID != caseID || result.Version <= 0 || result.UpdatedAt.IsZero() ||
		result.ApprovalCount < 0 || result.ApprovalCount > 2 {
		return false
	}
	if result.CaseKind != model.CaseKindModeration && result.CaseKind != model.CaseKindAppeal {
		return false
	}
	switch result.Status {
	case model.CaseStatusPendingApproval, model.CaseStatusRejected:
		return result.DecisionID == "" && result.DeliveryStatus == ""
	case model.CaseStatusApproved:
		return result.ApprovalCount == 2 && result.DecisionID != "" &&
			(result.DeliveryStatus == model.DeliveryStatusPending ||
				result.DeliveryStatus == model.DeliveryStatusRetrying ||
				result.DeliveryStatus == model.DeliveryStatusDelivered ||
				result.DeliveryStatus == model.DeliveryStatusDeadLetter)
	default:
		return false
	}
}

func (store *PostgresStore) replayAfterConflict(
	ctx context.Context,
	receipt ports.CommandReceipt,
) (ports.CaseSnapshot, error) {
	snapshot, found, err := store.Replay(ctx, receipt.IdempotencyKey, receipt.CommandDigest)
	if err != nil {
		return ports.CaseSnapshot{}, err
	}
	if !found {
		return ports.CaseSnapshot{}, model.ErrIdempotencyConflict
	}
	return snapshot, nil
}

func mapConstraintError(err error) error {
	var pgError *pgconn.PgError
	if errors.As(err, &pgError) && pgError.Code == "23505" {
		switch pgError.ConstraintName {
		case "account_enforcement_command_receipts_pkey":
			return model.ErrIdempotencyConflict
		default:
			return model.ErrSourceDecisionConflict
		}
	}
	return err
}

func isUniqueViolation(err error) bool {
	var pgError *pgconn.PgError
	return errors.As(err, &pgError) && pgError.Code == "23505"
}

func isReceiptConflict(err error) bool {
	var pgError *pgconn.PgError
	return errors.As(err, &pgError) && pgError.Code == "23505" &&
		pgError.ConstraintName == "account_enforcement_command_receipts_pkey"
}

func normalizedErrorClass(value string) string {
	switch strings.TrimSpace(value) {
	case "invalid_request", "not_found", "state_conflict", "unauthorized",
		"forbidden", "timeout", "remote_unavailable", "invalid_response",
		"transport_unavailable", "canceled":
		return strings.TrimSpace(value)
	default:
		return "transport_unavailable"
	}
}

func lockTransactionKey(ctx context.Context, tx pgx.Tx, value string) error {
	_, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1,0))`, value)
	return err
}

type rowQuerier interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

type fullQuerier interface {
	rowQuerier
	Query(context.Context, string, ...any) (pgx.Rows, error)
}
