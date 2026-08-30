package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/model"
	"quwoquan_service/control-plane/platform-ops/internal/platform_ops/human_authority/domain/ports"
)

type PostgresStore struct{ pool *pgxpool.Pool }

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("human authority postgres pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}
func (s *PostgresStore) EnsureSchema(ctx context.Context) error {
	_, err := s.pool.Exec(ctx, `
CREATE TABLE IF NOT EXISTS human_authority_units(
 decision_unit_id VARCHAR(128) PRIMARY KEY,
 unit JSONB NOT NULL,
 last_sequence BIGINT NOT NULL,
 last_hash VARCHAR(72) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS human_authority_events(
 event_id VARCHAR(128) PRIMARY KEY,
 decision_unit_id VARCHAR(128) NOT NULL REFERENCES human_authority_units(decision_unit_id),
 sequence BIGINT NOT NULL,
 event_type VARCHAR(96) NOT NULL,
 actor_id VARCHAR(256) NOT NULL,
 payload BYTEA NOT NULL,
 previous_hash VARCHAR(72) NOT NULL,
 event_hash VARCHAR(72) NOT NULL,
 occurred_at TIMESTAMPTZ NOT NULL,
 UNIQUE(decision_unit_id,sequence)
);
CREATE TABLE IF NOT EXISTS human_authority_receipts(
 decision_id VARCHAR(128) PRIMARY KEY,
 decision_unit_id VARCHAR(128) NOT NULL REFERENCES human_authority_units(decision_unit_id),
 key_id VARCHAR(128) NOT NULL,
 canonical_bytes TEXT NOT NULL,
 payload_digest VARCHAR(72) NOT NULL,
 signature TEXT NOT NULL,
 state VARCHAR(24) NOT NULL,
 previous_generation BIGINT NOT NULL DEFAULT 0,
 generation BIGINT NOT NULL DEFAULT 1,
 winner_idempotency_key VARCHAR(256) NOT NULL DEFAULT '',
 winner_command_digest VARCHAR(72) NOT NULL DEFAULT '',
 state_actor VARCHAR(256) NOT NULL DEFAULT '',
 state_at TIMESTAMPTZ NULL,
 chain_commit VARCHAR(72) NOT NULL DEFAULT '',
 issued_at TIMESTAMPTZ NOT NULL,
 expires_at TIMESTAMPTZ NOT NULL,
 test_key BOOLEAN NOT NULL,
 release_eligible BOOLEAN NOT NULL
);
ALTER TABLE human_authority_receipts ADD COLUMN IF NOT EXISTS previous_generation BIGINT NOT NULL DEFAULT 0;
ALTER TABLE human_authority_receipts ADD COLUMN IF NOT EXISTS generation BIGINT NOT NULL DEFAULT 1;
ALTER TABLE human_authority_receipts ADD COLUMN IF NOT EXISTS winner_idempotency_key VARCHAR(256) NOT NULL DEFAULT '';
ALTER TABLE human_authority_receipts ADD COLUMN IF NOT EXISTS winner_command_digest VARCHAR(72) NOT NULL DEFAULT '';
ALTER TABLE human_authority_receipts ADD COLUMN IF NOT EXISTS state_actor VARCHAR(256) NOT NULL DEFAULT '';
ALTER TABLE human_authority_receipts ADD COLUMN IF NOT EXISTS state_at TIMESTAMPTZ NULL;
ALTER TABLE human_authority_receipts ADD COLUMN IF NOT EXISTS chain_commit VARCHAR(72) NOT NULL DEFAULT '';
CREATE TABLE IF NOT EXISTS human_authority_audits(
 audit_id BIGSERIAL PRIMARY KEY,
 decision_unit_id VARCHAR(128) NOT NULL,
 action VARCHAR(96) NOT NULL,
 actor_id VARCHAR(256) NOT NULL,
 occurred_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS human_authority_outbox(
 event_id VARCHAR(128) PRIMARY KEY,event_type VARCHAR(128) NOT NULL,aggregate_type VARCHAR(128) NOT NULL,aggregate_id VARCHAR(128) NOT NULL,payload JSONB NOT NULL,occurred_at TIMESTAMPTZ NOT NULL,dispatched_at TIMESTAMPTZ NULL,retry_count INTEGER NOT NULL DEFAULT 0,next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),last_error TEXT NOT NULL DEFAULT '',lease_owner VARCHAR(160) NULL,leased_until TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS idx_human_authority_outbox_ready ON human_authority_outbox(dispatched_at,next_attempt_at,occurred_at);
CREATE TABLE IF NOT EXISTS human_authority_github_deliveries(
 delivery_id VARCHAR(128) PRIMARY KEY,payload_digest VARCHAR(72) NOT NULL,approval JSONB NOT NULL,occurred_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS human_authority_idempotency(
 operation VARCHAR(192) NOT NULL,idempotency_key VARCHAR(256) NOT NULL,request_digest VARCHAR(72) NOT NULL,status_code INTEGER NOT NULL,response_bytes BYTEA NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(operation,idempotency_key)
);
CREATE TABLE IF NOT EXISTS human_authority_signing_keys(
 key_id VARCHAR(128) PRIMARY KEY,public_key BYTEA NOT NULL,created_at TIMESTAMPTZ NOT NULL,retired_at TIMESTAMPTZ NULL
);`)
	return err
}
func (s *PostgresStore) Load(ctx context.Context, id string) (model.DecisionUnit, error) {
	var raw []byte
	err := s.pool.QueryRow(ctx, `SELECT unit FROM human_authority_units WHERE decision_unit_id=$1`, id).Scan(&raw)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.DecisionUnit{}, model.ErrNotFound
	}
	if err != nil {
		return model.DecisionUnit{}, err
	}
	var unit model.DecisionUnit
	if err = json.Unmarshal(raw, &unit); err != nil {
		return model.DecisionUnit{}, err
	}
	return unit, nil
}
func (s *PostgresStore) List(ctx context.Context) ([]model.DecisionUnit, error) {
	rows, err := s.pool.Query(ctx, `SELECT unit FROM human_authority_units ORDER BY created_at,decision_unit_id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.DecisionUnit{}
	for rows.Next() {
		var raw []byte
		if err = rows.Scan(&raw); err != nil {
			return nil, err
		}
		var unit model.DecisionUnit
		if err = json.Unmarshal(raw, &unit); err != nil {
			return nil, err
		}
		out = append(out, unit)
	}
	return out, rows.Err()
}
func (s *PostgresStore) Receipt(ctx context.Context, decisionID string) (model.AuthorizationReceipt, error) {
	var r model.AuthorizationReceipt
	err := s.pool.QueryRow(ctx, `SELECT decision_id,decision_unit_id,key_id,canonical_bytes,payload_digest,signature,state,previous_generation,generation,winner_idempotency_key,winner_command_digest,state_actor,COALESCE(state_at::text,''),chain_commit,issued_at,expires_at,test_key,release_eligible FROM human_authority_receipts WHERE decision_id=$1`, decisionID).Scan(&r.DecisionID, &r.DecisionUnitID, &r.KeyID, &r.CanonicalBytes, &r.PayloadDigest, &r.Signature, &r.State, &r.PreviousGeneration, &r.Generation, &r.WinnerIdempotencyKey, &r.WinnerCommandDigest, &r.StateActor, &r.StateAt, &r.ChainCommit, &r.IssuedAt, &r.ExpiresAt, &r.TestKey, &r.ReleaseEligible)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.AuthorizationReceipt{}, model.ErrNotFound
	}
	return r, err
}
func (s *PostgresStore) Idempotency(ctx context.Context, operation, key string) (ports.IdempotencyRecord, bool, error) {
	var record ports.IdempotencyRecord
	err := s.pool.QueryRow(ctx, `SELECT operation,idempotency_key,request_digest,status_code,response_bytes FROM human_authority_idempotency WHERE operation=$1 AND idempotency_key=$2`, operation, key).Scan(&record.Operation, &record.Key, &record.RequestDigest, &record.StatusCode, &record.ResponseBytes)
	if errors.Is(err, pgx.ErrNoRows) {
		return ports.IdempotencyRecord{}, false, nil
	}
	return record, err == nil, err
}
func (s *PostgresStore) SaveIdempotency(ctx context.Context, record ports.IdempotencyRecord) error {
	tag, err := s.pool.Exec(ctx, `INSERT INTO human_authority_idempotency(operation,idempotency_key,request_digest,status_code,response_bytes) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING`, record.Operation, record.Key, record.RequestDigest, record.StatusCode, record.ResponseBytes)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 1 {
		return nil
	}
	stored, ok, err := s.Idempotency(ctx, record.Operation, record.Key)
	if err != nil {
		return err
	}
	if !ok || stored.RequestDigest != record.RequestDigest {
		return model.ErrConflict
	}
	return nil
}
func (s *PostgresStore) Outbox(ctx context.Context, limit int) ([]ports.OutboxRecord, error) {
	if limit <= 0 || limit > 500 {
		limit = 100
	}
	rows, err := s.pool.Query(ctx, `SELECT event_id,event_type,aggregate_id,payload,occurred_at,dispatched_at,retry_count,last_error FROM human_authority_outbox ORDER BY occurred_at,event_id LIMIT $1`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []ports.OutboxRecord{}
	for rows.Next() {
		var r ports.OutboxRecord
		if err = rows.Scan(&r.EventID, &r.EventType, &r.AggregateID, &r.Payload, &r.OccurredAt, &r.DispatchedAt, &r.RetryCount, &r.LastError); err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	return out, rows.Err()
}
func (s *PostgresStore) Events(ctx context.Context, id string) ([]model.Event, error) {
	rows, err := s.pool.Query(ctx, `SELECT event_id,decision_unit_id,sequence,event_type,actor_id,payload,previous_hash,event_hash,occurred_at FROM human_authority_events WHERE decision_unit_id=$1 ORDER BY sequence`, id)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.Event{}
	for rows.Next() {
		var e model.Event
		if err = rows.Scan(&e.EventID, &e.UnitID, &e.Sequence, &e.Type, &e.ActorID, &e.Payload, &e.PreviousHash, &e.Hash, &e.OccurredAt); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, rows.Err()
}
func (s *PostgresStore) Create(ctx context.Context, p ports.CommitPacket) error {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	raw, err := json.Marshal(p.Unit)
	if err != nil {
		return err
	}
	_, err = tx.Exec(ctx, `INSERT INTO human_authority_units(decision_unit_id,unit,last_sequence,last_hash,created_at) VALUES($1,$2,$3,$4,$5)`, p.Unit.ID, raw, p.Unit.LastSequence, p.Unit.LastHash, p.Unit.CreatedAt)
	if err != nil {
		if isUnique(err) {
			return model.ErrConflict
		}
		return err
	}
	if err = appendPacket(ctx, tx, p); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
func (s *PostgresStore) Append(ctx context.Context, expected int64, p ports.CommitPacket) error {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	raw, err := json.Marshal(p.Unit)
	if err != nil {
		return err
	}
	tag, err := tx.Exec(ctx, `UPDATE human_authority_units SET unit=$3,last_sequence=$4,last_hash=$5 WHERE decision_unit_id=$1 AND last_sequence=$2`, p.Unit.ID, expected, raw, p.Unit.LastSequence, p.Unit.LastHash)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return model.ErrConflict
	}
	if err = appendPacket(ctx, tx, p); err != nil {
		return err
	}
	return tx.Commit(ctx)
}
func appendPacket(ctx context.Context, tx pgx.Tx, p ports.CommitPacket) error {
	for _, e := range p.Events {
		_, err := tx.Exec(ctx, `INSERT INTO human_authority_events(event_id,decision_unit_id,sequence,event_type,actor_id,payload,previous_hash,event_hash,occurred_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)`, e.EventID, e.UnitID, e.Sequence, e.Type, e.ActorID, e.Payload, e.PreviousHash, e.Hash, e.OccurredAt)
		if err != nil {
			return err
		}
	}
	at := time.Now().UTC()
	if len(p.Events) > 0 {
		at = p.Events[len(p.Events)-1].OccurredAt
	}
	if _, err := tx.Exec(ctx, `INSERT INTO human_authority_audits(decision_unit_id,action,actor_id,occurred_at) VALUES($1,$2,$3,$4)`, p.Unit.ID, p.AuditAction, p.AuditActor, at); err != nil {
		return err
	}
	outboxRaw, err := json.Marshal(p.OutboxPayload)
	if err != nil {
		return err
	}
	eventID := fmt.Sprintf("%s:%d", p.Unit.ID, p.Unit.LastSequence)
	if _, err = tx.Exec(ctx, `INSERT INTO human_authority_outbox(event_id,event_type,aggregate_type,aggregate_id,payload,occurred_at) VALUES($1,$2,'human_authority',$3,$4,$5)`, eventID, p.OutboxType, p.Unit.ID, outboxRaw, at); err != nil {
		return err
	}
	if p.Receipt != nil {
		r := p.Receipt
		if _, err = tx.Exec(ctx, `INSERT INTO human_authority_receipts(decision_id,decision_unit_id,key_id,canonical_bytes,payload_digest,signature,state,previous_generation,generation,winner_idempotency_key,winner_command_digest,chain_commit,issued_at,expires_at,test_key,release_eligible) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)`, r.DecisionID, p.Unit.ID, r.KeyID, r.CanonicalBytes, r.PayloadDigest, r.Signature, r.State, r.PreviousGeneration, r.Generation, r.WinnerIdempotencyKey, r.WinnerCommandDigest, r.ChainCommit, r.IssuedAt, r.ExpiresAt, r.TestKey, r.ReleaseEligible); err != nil {
			return err
		}
	}
	return nil
}
func (s *PostgresStore) TransitionReceipt(ctx context.Context, decisionID, from, to, expectedETag, idempotencyKey, commandDigest, actor, fingerprint string, scope model.CanonicalScope, action string, now time.Time, reason string) (model.AuthorizationReceipt, error) {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return model.AuthorizationReceipt{}, err
	}
	defer tx.Rollback(ctx)
	var r model.AuthorizationReceipt
	var unitID string
	err = tx.QueryRow(ctx, `SELECT decision_id,key_id,canonical_bytes,payload_digest,signature,state,previous_generation,generation,winner_idempotency_key,winner_command_digest,state_actor,COALESCE(state_at::text,''),chain_commit,issued_at,expires_at,test_key,release_eligible,decision_unit_id FROM human_authority_receipts WHERE decision_id=$1 FOR UPDATE`, decisionID).Scan(&r.DecisionID, &r.KeyID, &r.CanonicalBytes, &r.PayloadDigest, &r.Signature, &r.State, &r.PreviousGeneration, &r.Generation, &r.WinnerIdempotencyKey, &r.WinnerCommandDigest, &r.StateActor, &r.StateAt, &r.ChainCommit, &r.IssuedAt, &r.ExpiresAt, &r.TestKey, &r.ReleaseEligible, &unitID)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.AuthorizationReceipt{}, model.ErrNotFound
	}
	if err != nil {
		return model.AuthorizationReceipt{}, err
	}
	if r.State == to && r.WinnerIdempotencyKey == idempotencyKey && r.WinnerCommandDigest == commandDigest {
		r.DecisionUnitID = unitID
		r.ETag = model.ReceiptETag(r.DecisionID, r.Generation)
		return r, nil
	}
	if r.State != from || model.ReceiptETag(r.DecisionID, r.Generation) != expectedETag {
		return model.AuthorizationReceipt{}, model.ErrConflict
	}
	if to == model.ReceiptConsumed {
		if !now.Before(r.ExpiresAt) {
			return model.AuthorizationReceipt{}, model.ErrReceiptExpired
		}
		exact, decodeErr := model.DecodeExact(r.CanonicalBytes)
		if decodeErr != nil {
			return model.AuthorizationReceipt{}, model.ErrReceiptMismatch
		}
		var payload model.AuthorityReceiptClaims
		if json.Unmarshal(exact, &payload) != nil || payload.EvidenceFingerprint != fingerprint || !equalScope(payload.Scope, scope) || !model.Contains(payload.Actions, action) || !isCanonicalDigest(commandDigest) || idempotencyKey == "" {
			return model.AuthorizationReceipt{}, model.ErrReceiptMismatch
		}
	}
	previousGeneration := r.Generation
	newGeneration := previousGeneration + 1
	newETag := model.ReceiptETag(decisionID, newGeneration)
	tag, err := tx.Exec(ctx, `UPDATE human_authority_receipts SET state=$3,previous_generation=$4,generation=$5,winner_idempotency_key=$6,winner_command_digest=$7,state_actor=$8,state_at=$9 WHERE decision_id=$1 AND state=$2 AND generation=$10`, decisionID, from, to, previousGeneration, newGeneration, idempotencyKey, commandDigest, actor, now.UTC(), previousGeneration)
	if err != nil {
		return model.AuthorizationReceipt{}, err
	}
	if tag.RowsAffected() != 1 {
		return model.AuthorizationReceipt{}, model.ErrConflict
	}
	var lastSequence int64
	var lastHash string
	if err = tx.QueryRow(ctx, `SELECT last_sequence,last_hash FROM human_authority_units WHERE decision_unit_id=$1 FOR UPDATE`, unitID).Scan(&lastSequence, &lastHash); err != nil {
		return model.AuthorizationReceipt{}, err
	}
	event, eventErr := model.NewEvent(unitID, fmt.Sprintf("%s:%s", decisionID, to), "AuthorizationReceipt"+to, actor, lastSequence+1, lastHash, map[string]string{"reason": reason}, now)
	if eventErr != nil {
		return model.AuthorizationReceipt{}, eventErr
	}
	if _, err = tx.Exec(ctx, `INSERT INTO human_authority_events(event_id,decision_unit_id,sequence,event_type,actor_id,payload,previous_hash,event_hash,occurred_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)`, event.EventID, event.UnitID, event.Sequence, event.Type, event.ActorID, event.Payload, event.PreviousHash, event.Hash, event.OccurredAt); err != nil {
		return model.AuthorizationReceipt{}, err
	}
	if _, err = tx.Exec(ctx, `UPDATE human_authority_units SET last_sequence=$2,last_hash=$3,unit=jsonb_set(jsonb_set(unit,'{receipt,state}',to_jsonb($4::text),true),'{receipt,stateActor}',to_jsonb($5::text),true) WHERE decision_unit_id=$1`, unitID, event.Sequence, event.Hash, to, actor); err != nil {
		return model.AuthorizationReceipt{}, err
	}
	if _, err = tx.Exec(ctx, `INSERT INTO human_authority_audits(decision_unit_id,action,actor_id,occurred_at) VALUES($1,$2,$3,$4)`, unitID, "receipt_"+to, actor, now.UTC()); err != nil {
		return model.AuthorizationReceipt{}, err
	}
	payloadRaw, _ := json.Marshal(map[string]string{"decisionId": decisionID, "state": to})
	if _, err = tx.Exec(ctx, `INSERT INTO human_authority_outbox(event_id,event_type,aggregate_type,aggregate_id,payload,occurred_at) VALUES($1,$2,'human_authority',$3,$4,$5)`, event.EventID, "HumanAuthorizationReceipt"+to, unitID, payloadRaw, now.UTC()); err != nil {
		return model.AuthorizationReceipt{}, err
	}
	if _, err = tx.Exec(ctx, `UPDATE human_authority_receipts SET chain_commit=$2 WHERE decision_id=$1`, decisionID, event.Hash); err != nil {
		return model.AuthorizationReceipt{}, err
	}
	if err = tx.Commit(ctx); err != nil {
		return model.AuthorizationReceipt{}, err
	}
	r.State = to
	r.PreviousGeneration = previousGeneration
	r.Generation = newGeneration
	r.ETag = newETag
	r.WinnerIdempotencyKey = idempotencyKey
	r.WinnerCommandDigest = commandDigest
	r.ChainCommit = event.Hash
	r.StateActor = actor
	at := now.UTC()
	r.StateAt = at.Format(time.RFC3339Nano)
	return r, nil
}
func (s *PostgresStore) RecordGitHub(ctx context.Context, a model.GitHubApproval) (model.GitHubApproval, bool, error) {
	if a.Approved {
		var requested bool
		err := s.pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM human_authority_github_deliveries WHERE (approval->>'requested')::boolean=true AND (approval->>'installationId')::bigint=$1 AND approval->>'repository'=$2 AND (approval->>'runId')::bigint=$3 AND (approval->>'runAttempt')::bigint=$4 AND approval->>'headSha'=$5 AND approval->>'candidateDigest'=$6 AND approval->>'environment'=$7)`, a.InstallationID, a.Repository, a.RunID, a.RunAttempt, a.HeadSHA, a.CandidateDigest, a.Environment).Scan(&requested)
		if err != nil {
			return model.GitHubApproval{}, false, err
		}
		if !requested {
			return model.GitHubApproval{}, false, model.ErrConflict
		}
	}
	raw, err := json.Marshal(a)
	if err != nil {
		return model.GitHubApproval{}, false, err
	}
	tag, err := s.pool.Exec(ctx, `INSERT INTO human_authority_github_deliveries(delivery_id,payload_digest,approval,occurred_at) VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING`, a.DeliveryID, a.PayloadDigest, raw, a.OccurredAt)
	if err != nil {
		return model.GitHubApproval{}, false, err
	}
	if tag.RowsAffected() == 1 {
		return a, false, nil
	}
	var digest string
	var stored []byte
	if err = s.pool.QueryRow(ctx, `SELECT payload_digest,approval FROM human_authority_github_deliveries WHERE delivery_id=$1`, a.DeliveryID).Scan(&digest, &stored); err != nil {
		return model.GitHubApproval{}, false, err
	}
	if digest != a.PayloadDigest {
		return model.GitHubApproval{}, false, model.ErrConflict
	}
	var out model.GitHubApproval
	if err = json.Unmarshal(stored, &out); err != nil {
		return model.GitHubApproval{}, false, err
	}
	return out, true, nil
}
func isUnique(err error) bool {
	return err != nil && (errors.Is(err, pgx.ErrNoRows) == false) && contains(err.Error(), "duplicate key")
}
func contains(value, part string) bool {
	for i := 0; i+len(part) <= len(value); i++ {
		if value[i:i+len(part)] == part {
			return true
		}
	}
	return false
}
