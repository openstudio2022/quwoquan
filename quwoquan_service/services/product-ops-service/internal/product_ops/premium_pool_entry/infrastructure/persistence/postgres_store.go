package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/ports"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("PremiumPoolEntry postgres pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

func (store *PostgresStore) EnsureSchema(ctx context.Context) error {
	_, err := store.pool.Exec(ctx, `
CREATE TABLE IF NOT EXISTS premium_pool_entries (
  content_id VARCHAR(128) PRIMARY KEY,
  scope VARCHAR(16) NOT NULL,
  status VARCHAR(32) NOT NULL,
  quality_score DOUBLE PRECISION NOT NULL,
  quality_admission VARCHAR(32) NOT NULL,
  supply_source VARCHAR(128) NULL,
  source_task_id VARCHAR(160) NULL,
  audit_id VARCHAR(160) NOT NULL,
  rollback_token VARCHAR(160) NOT NULL,
  featured_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  revision BIGINT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT premium_pool_entries_scope_check CHECK (scope = 'global'),
  CONSTRAINT premium_pool_entries_status_check CHECK (status IN ('active','rolled_back','takedown_ejected')),
  CONSTRAINT premium_pool_entries_admission_check CHECK (quality_admission = 'approved'),
  CONSTRAINT premium_pool_entries_score_check CHECK (quality_score >= 0.75),
  CONSTRAINT premium_pool_entries_revision_check CHECK (revision > 0)
);
CREATE INDEX IF NOT EXISTS idx_premium_pool_entries_status_expiry
  ON premium_pool_entries(status, expires_at, updated_at DESC);

CREATE TABLE IF NOT EXISTS premium_pool_entry_workflows (
  content_id VARCHAR(128) PRIMARY KEY,
  state VARCHAR(32) NOT NULL,
  revision BIGINT NOT NULL,
  body JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS premium_pool_entry_approvals (
  content_id VARCHAR(128) NOT NULL,
  payload_digest VARCHAR(64) NOT NULL,
  decision VARCHAR(32) NOT NULL,
  actor_id VARCHAR(160) NOT NULL,
  revision BIGINT NOT NULL,
  approved_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(content_id, payload_digest, decision, actor_id)
);

CREATE TABLE IF NOT EXISTS premium_pool_entry_audits (
  audit_event_id VARCHAR(160) PRIMARY KEY,
  content_id VARCHAR(128) NOT NULL,
  action VARCHAR(64) NOT NULL,
  actor_id VARCHAR(160) NOT NULL,
  environment VARCHAR(32) NOT NULL,
  request_id VARCHAR(160) NOT NULL,
  trace_id VARCHAR(160) NOT NULL,
  before_state JSONB NULL,
  after_state JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS premium_pool_entry_command_receipts (
  content_id VARCHAR(128) NOT NULL,
  idempotency_key VARCHAR(160) NOT NULL,
  command_digest VARCHAR(64) NOT NULL,
	approval_digest VARCHAR(64) NULL,
  intent VARCHAR(32) NOT NULL,
  result_revision BIGINT NOT NULL,
  result_snapshot JSONB NOT NULL,
  committed_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY(content_id, idempotency_key)
);
ALTER TABLE premium_pool_entry_command_receipts
  ADD COLUMN IF NOT EXISTS approval_digest VARCHAR(64) NULL;

CREATE TABLE IF NOT EXISTS premium_pool_entry_outbox (
  event_id VARCHAR(128) PRIMARY KEY,
  event_type VARCHAR(128) NOT NULL,
  aggregate_type VARCHAR(128) NOT NULL,
  aggregate_id VARCHAR(128) NOT NULL,
  payload JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  dispatched_at TIMESTAMPTZ NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_error TEXT NOT NULL DEFAULT '',
  lease_owner VARCHAR(160) NULL,
  leased_until TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_premium_pool_entry_outbox_ready
  ON premium_pool_entry_outbox(dispatched_at, next_attempt_at, occurred_at);
`)
	return err
}

func (store *PostgresStore) List(ctx context.Context) ([]model.Entry, error) {
	rows, err := store.pool.Query(ctx, entrySelect+` ORDER BY updated_at DESC, content_id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	entries := make([]model.Entry, 0)
	for rows.Next() {
		entry, err := scanEntry(rows)
		if err != nil {
			return nil, err
		}
		entries = append(entries, entry)
	}
	return entries, rows.Err()
}

func (store *PostgresStore) Load(ctx context.Context, contentID string) (model.Entry, bool, error) {
	entry, err := scanEntry(store.pool.QueryRow(ctx, entrySelect+` WHERE content_id=$1`, strings.TrimSpace(contentID)))
	if errors.Is(err, pgx.ErrNoRows) {
		return model.Entry{}, false, nil
	}
	return entry, err == nil, err
}

func (store *PostgresStore) Replay(
	ctx context.Context,
	contentID string,
	idempotencyKey string,
) (ports.CommitReceipt, bool, error) {
	return scanReceipt(store.pool.QueryRow(ctx, `
SELECT command_digest,COALESCE(approval_digest,''),intent,result_snapshot,committed_at
FROM premium_pool_entry_command_receipts
WHERE content_id=$1 AND idempotency_key=$2`,
		strings.TrimSpace(contentID), strings.TrimSpace(idempotencyKey),
	), strings.TrimSpace(idempotencyKey))
}

func (store *PostgresStore) RecordApproval(ctx context.Context, approval ports.Approval) error {
	if strings.TrimSpace(approval.ContentID) == "" ||
		len(strings.TrimSpace(approval.PayloadDigest)) != 64 ||
		strings.TrimSpace(approval.Decision) == "" ||
		strings.TrimSpace(approval.ActorID) == "" ||
		approval.ActorID == "unverified" || approval.Revision <= 0 {
		return model.ErrInvalidArgument
	}
	_, err := store.pool.Exec(ctx, `
INSERT INTO premium_pool_entry_approvals(
  content_id, payload_digest, decision, actor_id, revision, approved_at
) VALUES ($1,$2,$3,$4,$5,$6)
ON CONFLICT (content_id, payload_digest, decision, actor_id) DO NOTHING`,
		approval.ContentID, approval.PayloadDigest, approval.Decision,
		approval.ActorID, approval.Revision, approval.ApprovedAt.UTC(),
	)
	return err
}

func (store *PostgresStore) ListApprovals(
	ctx context.Context,
	contentID string,
	payloadDigest string,
	decision string,
	revision int64,
) ([]ports.Approval, error) {
	rows, err := store.pool.Query(ctx, `
SELECT content_id, payload_digest, decision, actor_id, revision, approved_at
FROM premium_pool_entry_approvals
WHERE content_id=$1 AND payload_digest=$2 AND decision=$3 AND revision=$4
ORDER BY approved_at, actor_id`, contentID, payloadDigest, decision, revision)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]ports.Approval, 0, 2)
	for rows.Next() {
		var item ports.Approval
		if err := rows.Scan(
			&item.ContentID, &item.PayloadDigest, &item.Decision,
			&item.ActorID, &item.Revision, &item.ApprovedAt,
		); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (store *PostgresStore) Commit(
	ctx context.Context,
	change ports.ChangeSet,
) (ports.CommitReceipt, error) {
	if err := validateChange(change); err != nil {
		return ports.CommitReceipt{}, err
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	defer tx.Rollback(ctx)

	// 对同一聚合使用事务 advisory lock，连“尚不存在的行”也能串行化，
	// 避免两个并发 Upsert 都把 expectedRevision=0 当成可写。
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`, change.Entry.ContentID); err != nil {
		return ports.CommitReceipt{}, err
	}
	if receipt, found, err := replayReceipt(ctx, tx, change); err != nil || found {
		return receipt, err
	}

	current, found, err := loadEntryTx(ctx, tx, change.Entry.ContentID)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if change.ExpectedRevision == 0 {
		if found {
			return ports.CommitReceipt{}, model.ErrRevisionConflict
		}
	} else {
		if !found {
			return ports.CommitReceipt{}, model.ErrNotFound
		}
		if current.Revision != change.ExpectedRevision {
			return ports.CommitReceipt{}, model.ErrRevisionConflict
		}
	}
	if change.Entry.Revision != change.ExpectedRevision+1 {
		return ports.CommitReceipt{}, model.ErrRevisionConflict
	}
	if change.RequireDualApproval {
		var actorCount int
		if err := tx.QueryRow(ctx, `
SELECT COUNT(DISTINCT actor_id)
FROM premium_pool_entry_approvals
WHERE content_id=$1 AND payload_digest=$2 AND decision=$3 AND revision=$4
  AND actor_id <> '' AND actor_id <> 'unverified'`,
			change.Entry.ContentID, change.ApprovalDigest,
			change.Intent, change.ExpectedRevision,
		).Scan(&actorCount); err != nil {
			return ports.CommitReceipt{}, err
		}
		if actorCount < 2 {
			return ports.CommitReceipt{}, model.ErrDualApprovalRequired
		}
	}

	entry := change.Entry
	if _, err := tx.Exec(ctx, `
INSERT INTO premium_pool_entries(
  content_id, scope, status, quality_score, quality_admission,
  supply_source, source_task_id, audit_id, rollback_token,
  featured_at, expires_at, revision, updated_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
ON CONFLICT (content_id) DO UPDATE SET
  scope=EXCLUDED.scope, status=EXCLUDED.status,
  quality_score=EXCLUDED.quality_score, quality_admission=EXCLUDED.quality_admission,
  supply_source=EXCLUDED.supply_source, source_task_id=EXCLUDED.source_task_id,
  audit_id=EXCLUDED.audit_id, rollback_token=EXCLUDED.rollback_token,
  featured_at=EXCLUDED.featured_at, expires_at=EXCLUDED.expires_at,
  revision=EXCLUDED.revision, updated_at=EXCLUDED.updated_at`,
		entry.ContentID, entry.Scope, string(entry.Status), entry.QualityScore,
		entry.QualityAdmission, nullable(entry.SupplySource), nullable(entry.SourceTaskID),
		entry.AuditID, entry.RollbackToken, entry.FeaturedAt.UTC(), entry.ExpiresAt.UTC(),
		entry.Revision, entry.UpdatedAt.UTC(),
	); err != nil {
		return ports.CommitReceipt{}, err
	}

	workflow, _ := json.Marshal(map[string]any{
		"objectType": "premium_pool_entry", "objectId": entry.ContentID,
		"workflowId": "global_premium_pool:" + entry.ContentID,
		"state":      string(entry.Status), "revision": entry.Revision,
		"updatedAt": entry.UpdatedAt.UTC().Format(time.RFC3339Nano),
	})
	if _, err := tx.Exec(ctx, `
INSERT INTO premium_pool_entry_workflows(content_id,state,revision,body,updated_at)
VALUES ($1,$2,$3,$4,$5)
ON CONFLICT (content_id) DO UPDATE SET
  state=EXCLUDED.state, revision=EXCLUDED.revision,
  body=EXCLUDED.body, updated_at=EXCLUDED.updated_at`,
		entry.ContentID, string(entry.Status), entry.Revision, workflow, entry.UpdatedAt.UTC(),
	); err != nil {
		return ports.CommitReceipt{}, err
	}

	var beforeJSON []byte
	if change.Before != nil {
		beforeJSON, _ = json.Marshal(snapshotFromEntry(*change.Before))
	}
	afterSnapshot := snapshotFromEntry(entry)
	afterJSON, _ := json.Marshal(afterSnapshot)
	auditEventID := "premium_pool_" + change.Intent + "_" + change.CommandDigest[:32]
	if _, err := tx.Exec(ctx, `
INSERT INTO premium_pool_entry_audits(
  audit_event_id,content_id,action,actor_id,environment,request_id,trace_id,
  before_state,after_state,occurred_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)`,
		auditEventID, entry.ContentID, change.Intent, change.Context.ActorID,
		normalizeMetadata(change.Context.Environment, "unknown"),
		normalizeMetadata(change.Context.RequestID, "unknown"),
		normalizeMetadata(change.Context.TraceID, "unknown"),
		beforeJSON, afterJSON, entry.UpdatedAt.UTC(),
	); err != nil {
		return ports.CommitReceipt{}, err
	}

	eventPayload, err := json.Marshal(change.Event.Payload)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO premium_pool_entry_outbox(
  event_id,event_type,aggregate_type,aggregate_id,payload,occurred_at
) VALUES ($1,$2,'PremiumPoolEntry',$3,$4,$5)`,
		change.Event.ID, change.Event.Type, entry.ContentID,
		eventPayload, change.Event.OccurredAt.UTC(),
	); err != nil {
		return ports.CommitReceipt{}, err
	}

	committedAt := time.Now().UTC()
	resultSnapshot, _ := json.Marshal(afterSnapshot)
	if _, err := tx.Exec(ctx, `
INSERT INTO premium_pool_entry_command_receipts(
  content_id,idempotency_key,command_digest,approval_digest,intent,
  result_revision,result_snapshot,committed_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
		entry.ContentID, change.Context.IdempotencyKey, change.CommandDigest,
		nullable(change.ApprovalDigest), change.Intent, entry.Revision, resultSnapshot, committedAt,
	); err != nil {
		if isUniqueViolation(err) {
			return ports.CommitReceipt{}, model.ErrIdempotencyConflict
		}
		return ports.CommitReceipt{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CommitReceipt{}, err
	}
	return ports.CommitReceipt{
		Entry: entry, Intent: change.Intent, CommandDigest: change.CommandDigest,
		ApprovalDigest: change.ApprovalDigest,
		IdempotencyKey: change.Context.IdempotencyKey, CommittedAt: committedAt,
	}, nil
}

const entrySelect = `
SELECT content_id, scope, status, quality_score, quality_admission,
       COALESCE(supply_source,''), COALESCE(source_task_id,''), audit_id,
       rollback_token, featured_at, expires_at, revision, updated_at
FROM premium_pool_entries`

type rowScanner interface {
	Scan(...any) error
}

func scanEntry(row rowScanner) (model.Entry, error) {
	var entry model.Entry
	var status string
	err := row.Scan(
		&entry.ContentID, &entry.Scope, &status, &entry.QualityScore,
		&entry.QualityAdmission, &entry.SupplySource, &entry.SourceTaskID,
		&entry.AuditID, &entry.RollbackToken, &entry.FeaturedAt,
		&entry.ExpiresAt, &entry.Revision, &entry.UpdatedAt,
	)
	entry.Status = model.Status(status)
	return entry, err
}

func loadEntryTx(ctx context.Context, tx pgx.Tx, contentID string) (model.Entry, bool, error) {
	entry, err := scanEntry(tx.QueryRow(ctx, entrySelect+` WHERE content_id=$1 FOR UPDATE`, contentID))
	if errors.Is(err, pgx.ErrNoRows) {
		return model.Entry{}, false, nil
	}
	return entry, err == nil, err
}

func validateChange(change ports.ChangeSet) error {
	if strings.TrimSpace(change.Entry.ContentID) == "" ||
		strings.TrimSpace(change.Intent) == "" ||
		len(strings.TrimSpace(change.CommandDigest)) != 64 ||
		strings.TrimSpace(change.Context.IdempotencyKey) == "" ||
		strings.TrimSpace(change.Context.ActorID) == "" ||
		change.Context.ActorID == "unverified" ||
		strings.TrimSpace(change.Event.ID) == "" ||
		strings.TrimSpace(change.Event.Type) == "" ||
		change.Event.Payload == nil {
		return model.ErrInvalidArgument
	}
	if change.RequireDualApproval && len(strings.TrimSpace(change.ApprovalDigest)) != 64 {
		return model.ErrInvalidArgument
	}
	return nil
}

func replayReceipt(
	ctx context.Context,
	tx pgx.Tx,
	change ports.ChangeSet,
) (ports.CommitReceipt, bool, error) {
	receipt, found, err := scanReceipt(tx.QueryRow(ctx, `
SELECT command_digest,COALESCE(approval_digest,''),intent,result_snapshot,committed_at
FROM premium_pool_entry_command_receipts
WHERE content_id=$1 AND idempotency_key=$2`,
		change.Entry.ContentID, change.Context.IdempotencyKey,
	), change.Context.IdempotencyKey)
	if err != nil || !found {
		return receipt, found, err
	}
	if receipt.CommandDigest != change.CommandDigest || receipt.Intent != change.Intent {
		return ports.CommitReceipt{}, true, model.ErrIdempotencyConflict
	}
	return receipt, true, nil
}

func scanReceipt(row rowScanner, idempotencyKey string) (ports.CommitReceipt, bool, error) {
	var commandDigest, approvalDigest, intent string
	var raw []byte
	var committedAt time.Time
	if err := row.Scan(&commandDigest, &approvalDigest, &intent, &raw, &committedAt); errors.Is(err, pgx.ErrNoRows) {
		return ports.CommitReceipt{}, false, nil
	} else if err != nil {
		return ports.CommitReceipt{}, false, err
	}
	entry, err := entryFromSnapshot(raw)
	if err != nil {
		return ports.CommitReceipt{}, true, err
	}
	return ports.CommitReceipt{
		Entry: entry, Intent: intent, CommandDigest: commandDigest,
		ApprovalDigest: approvalDigest, IdempotencyKey: idempotencyKey,
		CommittedAt: committedAt, Replayed: true,
	}, true, nil
}

type entrySnapshot struct {
	ContentID        string  `json:"contentId"`
	Scope            string  `json:"scope"`
	Status           string  `json:"status"`
	QualityScore     float64 `json:"qualityScore"`
	QualityAdmission string  `json:"qualityAdmission"`
	SupplySource     string  `json:"supplySource,omitempty"`
	SourceTaskID     string  `json:"sourceTaskId,omitempty"`
	AuditID          string  `json:"auditId"`
	RollbackToken    string  `json:"rollbackToken"`
	FeaturedAt       string  `json:"featuredAt"`
	ExpiresAt        string  `json:"expiresAt"`
	TakedownEjected  bool    `json:"takedownEjected"`
	Revision         int64   `json:"revision"`
	UpdatedAt        string  `json:"updatedAt"`
}

func snapshotFromEntry(entry model.Entry) entrySnapshot {
	return entrySnapshot{
		ContentID: entry.ContentID, Scope: entry.Scope,
		Status: string(entry.Status), QualityScore: entry.QualityScore,
		QualityAdmission: entry.QualityAdmission, SupplySource: entry.SupplySource,
		SourceTaskID: entry.SourceTaskID, AuditID: entry.AuditID,
		RollbackToken:   entry.RollbackToken,
		FeaturedAt:      entry.FeaturedAt.UTC().Format(time.RFC3339Nano),
		ExpiresAt:       entry.ExpiresAt.UTC().Format(time.RFC3339Nano),
		TakedownEjected: entry.TakedownEjected(), Revision: entry.Revision,
		UpdatedAt: entry.UpdatedAt.UTC().Format(time.RFC3339Nano),
	}
}

func entryFromSnapshot(raw []byte) (model.Entry, error) {
	var snapshot entrySnapshot
	if err := json.Unmarshal(raw, &snapshot); err != nil {
		return model.Entry{}, err
	}
	featuredAt, err := time.Parse(time.RFC3339Nano, snapshot.FeaturedAt)
	if err != nil {
		return model.Entry{}, err
	}
	expiresAt, err := time.Parse(time.RFC3339Nano, snapshot.ExpiresAt)
	if err != nil {
		return model.Entry{}, err
	}
	updatedAt, err := time.Parse(time.RFC3339Nano, snapshot.UpdatedAt)
	if err != nil {
		return model.Entry{}, err
	}
	return model.Entry{
		ContentID: snapshot.ContentID, Scope: snapshot.Scope,
		Status: model.Status(snapshot.Status), QualityScore: snapshot.QualityScore,
		QualityAdmission: snapshot.QualityAdmission, SupplySource: snapshot.SupplySource,
		SourceTaskID: snapshot.SourceTaskID, AuditID: snapshot.AuditID,
		RollbackToken: snapshot.RollbackToken, FeaturedAt: featuredAt,
		ExpiresAt: expiresAt, Revision: snapshot.Revision, UpdatedAt: updatedAt,
	}, nil
}

func nullable(value string) any {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	return value
}

func normalizeMetadata(value, fallback string) string {
	if value = strings.TrimSpace(value); value != "" {
		return value
	}
	return fallback
}

func isUniqueViolation(err error) bool {
	return strings.Contains(strings.ToLower(fmt.Sprint(err)), "duplicate key") ||
		strings.Contains(strings.ToLower(fmt.Sprint(err)), "unique constraint")
}
