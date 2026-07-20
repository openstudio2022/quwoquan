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

	"quwoquan_service/runtime/controlplane"
)

const stateStoreTimeout = 5 * time.Second

// PostgresStore 是控制面生产状态存储。scope 隔离 platform/product 两个控制面，
// 所有写入由 PostgreSQL 原子提交，不允许本地文件成为第二真相源。
type PostgresStore struct {
	pool  *pgxpool.Pool
	scope string
}

func NewPostgresStore(pool *pgxpool.Pool, scope string) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("control plane postgres pool is required")
	}
	scope = strings.TrimSpace(scope)
	if scope == "" {
		return nil, errors.New("control plane store scope is required")
	}
	return &PostgresStore{pool: pool, scope: scope}, nil
}

func (s *PostgresStore) EnsureSchema(ctx context.Context) error {
	if ctx == nil {
		ctx = context.Background()
	}
	_, err := s.pool.Exec(ctx, `
CREATE TABLE IF NOT EXISTS control_plane_documents (
  scope TEXT NOT NULL,
  namespace TEXT NOT NULL,
  document_id TEXT NOT NULL,
  body JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (scope, namespace, document_id)
);
CREATE INDEX IF NOT EXISTS idx_control_plane_documents_namespace
  ON control_plane_documents(scope, namespace, document_id);

CREATE TABLE IF NOT EXISTS control_plane_workflows (
  scope TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  body JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (scope, object_type, object_id)
);

CREATE TABLE IF NOT EXISTS control_plane_approvals (
  sequence_id BIGSERIAL PRIMARY KEY,
  scope TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  body JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_control_plane_approvals_object
  ON control_plane_approvals(scope, object_type, object_id, occurred_at, sequence_id);

CREATE TABLE IF NOT EXISTS control_plane_audits (
  sequence_id BIGSERIAL PRIMARY KEY,
  scope TEXT NOT NULL,
  audit_id TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  body JSONB NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_control_plane_audits_time
  ON control_plane_audits(scope, occurred_at DESC, sequence_id DESC);

CREATE TABLE IF NOT EXISTS control_plane_mutation_receipts (
  scope TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  intent TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  body JSONB NOT NULL,
  committed_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (scope, object_type, object_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS product_control_plane_outbox (
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
CREATE INDEX IF NOT EXISTS idx_product_control_plane_outbox_ready
  ON product_control_plane_outbox(dispatched_at, next_attempt_at, occurred_at);

CREATE TABLE IF NOT EXISTS platform_control_plane_outbox (
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
CREATE INDEX IF NOT EXISTS idx_platform_control_plane_outbox_ready
  ON platform_control_plane_outbox(dispatched_at, next_attempt_at, occurred_at);

CREATE TABLE IF NOT EXISTS generic_control_plane_outbox (
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
CREATE INDEX IF NOT EXISTS idx_generic_control_plane_outbox_ready
  ON generic_control_plane_outbox(dispatched_at, next_attempt_at, occurred_at);
`)
	return err
}

func (s *PostgresStore) GetDocument(namespace, id string) (controlplane.Document, bool, error) {
	ctx, cancel := s.operationContext()
	defer cancel()
	var raw []byte
	err := s.pool.QueryRow(ctx, `
SELECT body FROM control_plane_documents
WHERE scope=$1 AND namespace=$2 AND document_id=$3`, s.scope, namespace, id).Scan(&raw)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	doc, err := decodeDocumentJSON(raw)
	return doc, err == nil, err
}

func (s *PostgresStore) PutDocument(namespace, id string, doc controlplane.Document) error {
	if strings.TrimSpace(namespace) == "" || strings.TrimSpace(id) == "" {
		return errors.New("namespace and id are required")
	}
	raw, err := json.Marshal(doc)
	if err != nil {
		return err
	}
	ctx, cancel := s.operationContext()
	defer cancel()
	_, err = s.pool.Exec(ctx, `
INSERT INTO control_plane_documents(scope, namespace, document_id, body, updated_at)
VALUES ($1,$2,$3,$4,NOW())
ON CONFLICT (scope, namespace, document_id)
DO UPDATE SET body=EXCLUDED.body, updated_at=NOW()`, s.scope, namespace, id, raw)
	return err
}

func (s *PostgresStore) PutDocumentIfAbsent(namespace, id string, doc controlplane.Document) (controlplane.Document, bool, error) {
	if strings.TrimSpace(namespace) == "" || strings.TrimSpace(id) == "" {
		return nil, false, errors.New("namespace and id are required")
	}
	raw, err := json.Marshal(doc)
	if err != nil {
		return nil, false, err
	}
	ctx, cancel := s.operationContext()
	defer cancel()
	var stored []byte
	err = s.pool.QueryRow(ctx, `
INSERT INTO control_plane_documents(scope, namespace, document_id, body, updated_at)
VALUES ($1,$2,$3,$4,NOW())
ON CONFLICT (scope, namespace, document_id) DO NOTHING
RETURNING body`, s.scope, namespace, id, raw).Scan(&stored)
	inserted := true
	if errors.Is(err, pgx.ErrNoRows) {
		inserted = false
		err = s.pool.QueryRow(ctx, `
SELECT body FROM control_plane_documents
WHERE scope=$1 AND namespace=$2 AND document_id=$3`, s.scope, namespace, id).Scan(&stored)
	}
	if err != nil {
		return nil, false, err
	}
	canonical, err := decodeDocumentJSON(stored)
	return canonical, inserted, err
}

func (s *PostgresStore) DeleteDocument(namespace, id string) error {
	ctx, cancel := s.operationContext()
	defer cancel()
	_, err := s.pool.Exec(ctx, `DELETE FROM control_plane_documents
WHERE scope=$1 AND namespace=$2 AND document_id=$3`, s.scope, namespace, id)
	return err
}

func (s *PostgresStore) ListDocuments(namespace string) ([]controlplane.Document, error) {
	ctx, cancel := s.operationContext()
	defer cancel()
	rows, err := s.pool.Query(ctx, `
SELECT body FROM control_plane_documents
WHERE scope=$1 AND namespace=$2 ORDER BY document_id`, s.scope, namespace)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]controlplane.Document, 0)
	for rows.Next() {
		var raw []byte
		if err := rows.Scan(&raw); err != nil {
			return nil, err
		}
		doc, err := decodeDocumentJSON(raw)
		if err != nil {
			return nil, err
		}
		out = append(out, doc)
	}
	return out, rows.Err()
}

func (s *PostgresStore) UpsertWorkflow(workflow controlplane.WorkflowState) error {
	if workflow.ObjectType == "" || workflow.ObjectID == "" {
		return errors.New("workflow object type and id are required")
	}
	if workflow.UpdatedAt == "" {
		workflow.UpdatedAt = nowRFC3339()
	}
	raw, err := json.Marshal(workflow)
	if err != nil {
		return err
	}
	ctx, cancel := s.operationContext()
	defer cancel()
	_, err = s.pool.Exec(ctx, `
INSERT INTO control_plane_workflows(scope, object_type, object_id, body, updated_at)
VALUES ($1,$2,$3,$4,$5)
ON CONFLICT (scope, object_type, object_id)
DO UPDATE SET body=EXCLUDED.body, updated_at=EXCLUDED.updated_at`,
		s.scope, workflow.ObjectType, workflow.ObjectID, raw, workflow.UpdatedAt)
	return err
}

func (s *PostgresStore) GetWorkflow(objectType, objectID string) (controlplane.WorkflowState, bool, error) {
	ctx, cancel := s.operationContext()
	defer cancel()
	var raw []byte
	err := s.pool.QueryRow(ctx, `
SELECT body FROM control_plane_workflows
WHERE scope=$1 AND object_type=$2 AND object_id=$3`, s.scope, objectType, objectID).Scan(&raw)
	if errors.Is(err, pgx.ErrNoRows) {
		return controlplane.WorkflowState{}, false, nil
	}
	if err != nil {
		return controlplane.WorkflowState{}, false, err
	}
	var out controlplane.WorkflowState
	err = json.Unmarshal(raw, &out)
	return out, err == nil, err
}

func (s *PostgresStore) ListWorkflows() ([]controlplane.WorkflowState, error) {
	ctx, cancel := s.operationContext()
	defer cancel()
	rows, err := s.pool.Query(ctx, `
SELECT body FROM control_plane_workflows
WHERE scope=$1 ORDER BY object_type, object_id`, s.scope)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]controlplane.WorkflowState, 0)
	for rows.Next() {
		var raw []byte
		var item controlplane.WorkflowState
		if err := rows.Scan(&raw); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(raw, &item); err != nil {
			return nil, err
		}
		out = append(out, item)
	}
	return out, rows.Err()
}

func (s *PostgresStore) AppendApproval(item controlplane.ApprovalDecision) error {
	if item.ObjectType == "" || item.ObjectID == "" {
		return errors.New("approval object type and id are required")
	}
	if item.At == "" {
		item.At = nowRFC3339()
	}
	occurredAt, err := parseOccurredAt(item.At)
	if err != nil {
		return err
	}
	raw, err := json.Marshal(item)
	if err != nil {
		return err
	}
	ctx, cancel := s.operationContext()
	defer cancel()
	_, err = s.pool.Exec(ctx, `
INSERT INTO control_plane_approvals(scope, object_type, object_id, body, occurred_at)
VALUES ($1,$2,$3,$4,$5)`, s.scope, item.ObjectType, item.ObjectID, raw, occurredAt)
	return err
}

func (s *PostgresStore) ListApprovals(objectType, objectID string) ([]controlplane.ApprovalDecision, error) {
	return s.listApprovals(`
SELECT body FROM control_plane_approvals
WHERE scope=$1 AND object_type=$2 AND object_id=$3
ORDER BY occurred_at, sequence_id`, s.scope, objectType, objectID)
}

func (s *PostgresStore) ListAllApprovals() ([]controlplane.ApprovalDecision, error) {
	return s.listApprovals(`
SELECT body FROM control_plane_approvals
WHERE scope=$1 ORDER BY occurred_at DESC, sequence_id DESC`, s.scope)
}

func (s *PostgresStore) AppendAudit(event controlplane.AuditEvent) error {
	if event.AuditID == "" || event.ObjectType == "" || event.ObjectID == "" {
		return errors.New("audit id, object type and object id are required")
	}
	if event.At == "" {
		event.At = nowRFC3339()
	}
	occurredAt, err := parseOccurredAt(event.At)
	if err != nil {
		return err
	}
	raw, err := json.Marshal(event)
	if err != nil {
		return err
	}
	ctx, cancel := s.operationContext()
	defer cancel()
	_, err = s.pool.Exec(ctx, `
INSERT INTO control_plane_audits(scope, audit_id, object_type, object_id, body, occurred_at)
VALUES ($1,$2,$3,$4,$5,$6)`, s.scope, event.AuditID, event.ObjectType, event.ObjectID, raw, occurredAt)
	return err
}

func (s *PostgresStore) ListAudits() ([]controlplane.AuditEvent, error) {
	ctx, cancel := s.operationContext()
	defer cancel()
	rows, err := s.pool.Query(ctx, `
SELECT body FROM control_plane_audits
WHERE scope=$1 ORDER BY occurred_at DESC, sequence_id DESC`, s.scope)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]controlplane.AuditEvent, 0)
	for rows.Next() {
		var raw []byte
		var item controlplane.AuditEvent
		if err := rows.Scan(&raw); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(raw, &item); err != nil {
			return nil, err
		}
		out = append(out, item)
	}
	return out, rows.Err()
}

func (s *PostgresStore) CommitApprovedMutation(
	mutation controlplane.ApprovedMutation,
) (controlplane.MutationReceipt, error) {
	if err := controlplane.ValidateApprovedMutation(mutation); err != nil {
		return controlplane.MutationReceipt{}, err
	}
	ctx, cancel := s.operationContext()
	defer cancel()
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return controlplane.MutationReceipt{}, err
	}
	defer tx.Rollback(ctx)

	committedAt := time.Now().UTC()
	receipt := controlplane.MutationReceipt{
		ObjectType:     mutation.ObjectType,
		ObjectID:       mutation.ObjectID,
		Intent:         mutation.Intent,
		PayloadDigest:  mutation.PayloadDigest,
		IdempotencyKey: mutation.IdempotencyKey,
		CommittedAt:    committedAt.Format(time.RFC3339Nano),
	}
	receiptRaw, err := json.Marshal(receipt)
	if err != nil {
		return controlplane.MutationReceipt{}, err
	}
	var inserted []byte
	err = tx.QueryRow(ctx, `
INSERT INTO control_plane_mutation_receipts(
  scope, object_type, object_id, idempotency_key, intent,
  payload_digest, body, committed_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
ON CONFLICT (scope, object_type, object_id, idempotency_key) DO NOTHING
RETURNING body`,
		s.scope, mutation.ObjectType, mutation.ObjectID,
		mutation.IdempotencyKey, mutation.Intent, mutation.PayloadDigest,
		receiptRaw, committedAt,
	).Scan(&inserted)
	if errors.Is(err, pgx.ErrNoRows) {
		var existingRaw []byte
		var existingIntent, existingDigest string
		if err := tx.QueryRow(ctx, `
SELECT intent, payload_digest, body
FROM control_plane_mutation_receipts
WHERE scope=$1 AND object_type=$2 AND object_id=$3 AND idempotency_key=$4
FOR UPDATE`,
			s.scope, mutation.ObjectType, mutation.ObjectID, mutation.IdempotencyKey,
		).Scan(&existingIntent, &existingDigest, &existingRaw); err != nil {
			return controlplane.MutationReceipt{}, err
		}
		if existingIntent != mutation.Intent || existingDigest != mutation.PayloadDigest {
			return controlplane.MutationReceipt{}, controlplane.ErrMutationIdempotencyConflict
		}
		var existing controlplane.MutationReceipt
		if err := json.Unmarshal(existingRaw, &existing); err != nil {
			return controlplane.MutationReceipt{}, err
		}
		existing.Replayed = true
		return existing, nil
	}
	if err != nil {
		return controlplane.MutationReceipt{}, err
	}

	// Approval rows are locked for the duration of the commit. Only two
	// different verified actors approving the exact same digest/intent count.
	rows, err := tx.Query(ctx, `
SELECT body FROM control_plane_approvals
WHERE scope=$1 AND object_type=$2 AND object_id=$3
FOR SHARE`, s.scope, mutation.ObjectType, mutation.ObjectID)
	if err != nil {
		return controlplane.MutationReceipt{}, err
	}
	actors := map[string]struct{}{}
	for rows.Next() {
		var raw []byte
		var approval controlplane.ApprovalDecision
		if err := rows.Scan(&raw); err != nil {
			rows.Close()
			return controlplane.MutationReceipt{}, err
		}
		if err := json.Unmarshal(raw, &approval); err != nil {
			rows.Close()
			return controlplane.MutationReceipt{}, err
		}
		actor := strings.TrimSpace(approval.Actor)
		if approval.PayloadDigest == mutation.PayloadDigest &&
			approval.Decision == mutation.ApprovalDecision &&
			actor != "" && actor != "unverified" {
			actors[actor] = struct{}{}
		}
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return controlplane.MutationReceipt{}, err
	}
	rows.Close()
	if len(actors) < 2 {
		return controlplane.MutationReceipt{}, controlplane.ErrDualApprovalRequired
	}

	documentRaw, err := json.Marshal(mutation.Document)
	if err != nil {
		return controlplane.MutationReceipt{}, err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO control_plane_documents(scope, namespace, document_id, body, updated_at)
VALUES ($1,$2,$3,$4,$5)
ON CONFLICT (scope, namespace, document_id)
DO UPDATE SET body=EXCLUDED.body, updated_at=EXCLUDED.updated_at`,
		s.scope, mutation.Namespace, mutation.ObjectID, documentRaw, committedAt,
	); err != nil {
		return controlplane.MutationReceipt{}, err
	}

	if mutation.Workflow.UpdatedAt == "" {
		mutation.Workflow.UpdatedAt = committedAt.Format(time.RFC3339Nano)
	}
	workflowRaw, err := json.Marshal(mutation.Workflow)
	if err != nil {
		return controlplane.MutationReceipt{}, err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO control_plane_workflows(scope, object_type, object_id, body, updated_at)
VALUES ($1,$2,$3,$4,$5)
ON CONFLICT (scope, object_type, object_id)
DO UPDATE SET body=EXCLUDED.body, updated_at=EXCLUDED.updated_at`,
		s.scope, mutation.ObjectType, mutation.ObjectID,
		workflowRaw, mutation.Workflow.UpdatedAt,
	); err != nil {
		return controlplane.MutationReceipt{}, err
	}

	if mutation.Audit.At == "" {
		mutation.Audit.At = committedAt.Format(time.RFC3339Nano)
	}
	auditOccurredAt, err := parseOccurredAt(mutation.Audit.At)
	if err != nil {
		return controlplane.MutationReceipt{}, err
	}
	auditRaw, err := json.Marshal(mutation.Audit)
	if err != nil {
		return controlplane.MutationReceipt{}, err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO control_plane_audits(
  scope, audit_id, object_type, object_id, body, occurred_at
) VALUES ($1,$2,$3,$4,$5,$6)`,
		s.scope, mutation.Audit.AuditID, mutation.ObjectType,
		mutation.ObjectID, auditRaw, auditOccurredAt,
	); err != nil {
		return controlplane.MutationReceipt{}, err
	}

	outboxTable := s.mutationOutboxTable()
	for _, event := range mutation.OutboxEvents {
		occurredAt := committedAt
		if strings.TrimSpace(event.OccurredAt) != "" {
			occurredAt, err = parseOccurredAt(event.OccurredAt)
			if err != nil {
				return controlplane.MutationReceipt{}, err
			}
		}
		payload, err := json.Marshal(event.Payload)
		if err != nil {
			return controlplane.MutationReceipt{}, err
		}
		query := fmt.Sprintf(`
INSERT INTO %s(
  event_id, event_type, aggregate_type, aggregate_id, payload, occurred_at
) VALUES ($1,$2,$3,$4,$5,$6)
ON CONFLICT (event_id) DO NOTHING`, outboxTable)
		if _, err := tx.Exec(ctx, query,
			event.EventID, event.EventType, event.AggregateType,
			event.AggregateID, payload, occurredAt,
		); err != nil {
			return controlplane.MutationReceipt{}, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return controlplane.MutationReceipt{}, err
	}
	return receipt, nil
}

func (s *PostgresStore) GetMutationReceipt(
	objectType string,
	objectID string,
	idempotencyKey string,
) (controlplane.MutationReceipt, bool, error) {
	ctx, cancel := s.operationContext()
	defer cancel()
	var raw []byte
	err := s.pool.QueryRow(ctx, `
SELECT body FROM control_plane_mutation_receipts
WHERE scope=$1 AND object_type=$2 AND object_id=$3 AND idempotency_key=$4`,
		s.scope, objectType, objectID, idempotencyKey,
	).Scan(&raw)
	if errors.Is(err, pgx.ErrNoRows) {
		return controlplane.MutationReceipt{}, false, nil
	}
	if err != nil {
		return controlplane.MutationReceipt{}, false, err
	}
	var receipt controlplane.MutationReceipt
	if err := json.Unmarshal(raw, &receipt); err != nil {
		return controlplane.MutationReceipt{}, false, err
	}
	return receipt, true, nil
}

func (s *PostgresStore) mutationOutboxTable() string {
	switch s.scope {
	case "product-ops":
		return "product_control_plane_outbox"
	case "platform-ops":
		return "platform_control_plane_outbox"
	default:
		return "generic_control_plane_outbox"
	}
}

var _ controlplane.AtomicMutationStore = (*PostgresStore)(nil)

func (s *PostgresStore) listApprovals(query string, args ...any) ([]controlplane.ApprovalDecision, error) {
	ctx, cancel := s.operationContext()
	defer cancel()
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]controlplane.ApprovalDecision, 0)
	for rows.Next() {
		var raw []byte
		var item controlplane.ApprovalDecision
		if err := rows.Scan(&raw); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(raw, &item); err != nil {
			return nil, err
		}
		out = append(out, item)
	}
	return out, rows.Err()
}

func (s *PostgresStore) operationContext() (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.Background(), stateStoreTimeout)
}

func decodeDocumentJSON(raw []byte) (controlplane.Document, error) {
	var out controlplane.Document
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil, err
	}
	return out, nil
}

func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339)
}

func parseOccurredAt(raw string) (time.Time, error) {
	parsed, err := time.Parse(time.RFC3339, raw)
	if err != nil {
		return time.Time{}, fmt.Errorf("control plane timestamp must be RFC3339: %w", err)
	}
	return parsed, nil
}

var _ controlplane.StateStore = (*PostgresStore)(nil)
