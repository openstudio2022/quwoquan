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
