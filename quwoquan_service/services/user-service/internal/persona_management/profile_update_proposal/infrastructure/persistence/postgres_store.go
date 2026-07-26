package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	"quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/model"
	"quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/ports"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

var _ ports.AggregateStore = (*PostgresStore)(nil)
var _ ports.Reader = (*PostgresStore)(nil)
var _ ports.TransactionalOutbox = (*PostgresStore)(nil)

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("profile proposal PostgreSQL pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

func (s *PostgresStore) Load(ctx context.Context, proposalID string) (model.ProfileUpdateProposal, error) {
	return scanProposal(s.pool.QueryRow(ctx, proposalSelect+` WHERE id=$1`, strings.TrimSpace(proposalID)))
}

func (s *PostgresStore) Get(ctx context.Context, proposalID string) (model.ProfileUpdateProposal, error) {
	return s.Load(ctx, proposalID)
}

func (s *PostgresStore) LoadAudit(
	ctx context.Context,
	proposalID string,
	action model.AuditAction,
) (model.AuditRecord, error) {
	var (
		record           model.AuditRecord
		beforeJSON       []byte
		afterJSON        []byte
		beforeVersion    int64
		afterVersion     int64
		rollbackDeadline *time.Time
	)
	err := s.pool.QueryRow(ctx, `
SELECT audit_id, proposal_id, action, actor_persona_id, request_id, trace_id,
       before_snapshot, after_snapshot, before_persona_version,
       after_persona_version, occurred_at, rollback_deadline
FROM profile_update_proposal_audits
WHERE proposal_id=$1 AND action=$2`,
		strings.TrimSpace(proposalID),
		action,
	).Scan(
		&record.ID,
		&record.ProposalID,
		&record.Action,
		&record.Context.ActorPersonaID,
		&record.Context.RequestID,
		&record.Context.TraceID,
		&beforeJSON,
		&afterJSON,
		&beforeVersion,
		&afterVersion,
		&record.OccurredAt,
		&rollbackDeadline,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.AuditRecord{}, model.ErrNotFound
	}
	if err != nil {
		return model.AuditRecord{}, err
	}
	record.RollbackDeadline = rollbackDeadline
	if err := json.Unmarshal(beforeJSON, &record.Before); err != nil {
		return model.AuditRecord{}, err
	}
	if err := json.Unmarshal(afterJSON, &record.After); err != nil {
		return model.AuditRecord{}, err
	}
	if record.Before.Version != beforeVersion || record.After.Version != afterVersion {
		return model.AuditRecord{}, errors.New("profile proposal audit version columns diverge from snapshots")
	}
	return record, record.Validate()
}

func (s *PostgresStore) ListByPersona(
	ctx context.Context,
	personaID string,
	cursor *ports.Cursor,
	limit int,
) (ports.Slice, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return ports.Slice{}, errors.New("personaId is required")
	}
	if limit <= 0 || limit > 100 {
		return ports.Slice{}, errors.New("limit must be between 1 and 100")
	}
	query := proposalSelect + ` WHERE persona_id=$1`
	args := []any{personaID}
	if cursor != nil {
		if cursor.CreatedAt.IsZero() || strings.TrimSpace(cursor.ID) == "" {
			return ports.Slice{}, errors.New("profile proposal cursor is invalid")
		}
		query += ` AND (created_at, id) < ($2, $3)`
		args = append(args, cursor.CreatedAt.UTC(), cursor.ID)
	}
	args = append(args, limit+1)
	query += fmt.Sprintf(` ORDER BY created_at DESC, id DESC LIMIT $%d`, len(args))
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return ports.Slice{}, err
	}
	defer rows.Close()
	items := make([]model.ProfileUpdateProposal, 0, limit+1)
	for rows.Next() {
		proposal, err := scanProposal(rows)
		if err != nil {
			return ports.Slice{}, err
		}
		items = append(items, proposal)
	}
	if err := rows.Err(); err != nil {
		return ports.Slice{}, err
	}
	result := ports.Slice{Items: items}
	if len(items) > limit {
		last := items[limit-1]
		result.Items = items[:limit]
		result.NextCursor = &ports.Cursor{CreatedAt: last.CreatedAt, ID: last.ID}
	}
	return result, nil
}

func (s *PostgresStore) Replay(
	ctx context.Context,
	actorPersonaID string,
	idempotencyKey string,
	commandDigest string,
) (ports.CommitReceipt, bool, error) {
	return replayReceipt(ctx, s.pool, actorPersonaID, idempotencyKey, commandDigest)
}

func (s *PostgresStore) RecordNoopReceipt(
	ctx context.Context,
	proposal model.ProfileUpdateProposal,
	idempotencyKey string,
	commandDigest string,
) (ports.CommitReceipt, error) {
	if err := proposal.Validate(); err != nil {
		return ports.CommitReceipt{}, err
	}
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	commandDigest = strings.TrimSpace(commandDigest)
	if idempotencyKey == "" || len(idempotencyKey) > 160 || commandDigest == "" {
		return ports.CommitReceipt{}, errors.New(
			"profile proposal no-op receipt requires idempotency key and command digest",
		)
	}
	if replayed, found, err := s.Replay(
		ctx,
		proposal.PersonaID,
		idempotencyKey,
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	receipt := ports.CommitReceipt{
		ProposalID: proposal.ID,
		Version:    proposal.Version,
		Status:     string(proposal.Status),
	}
	resultJSON, err := json.Marshal(receipt)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	result, err := s.pool.Exec(ctx, `
INSERT INTO profile_update_proposals_command_receipts(
  receipt_id, proposal_id, actor_persona_id, idempotency_key,
  command_digest, aggregate_version, result_json
) VALUES ($1,$2,$3,$4,$5,$6,$7)
ON CONFLICT (actor_persona_id, idempotency_key) DO NOTHING`,
		receiptID(proposal.PersonaID, idempotencyKey), proposal.ID,
		proposal.PersonaID, idempotencyKey, commandDigest, proposal.Version, resultJSON,
	)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if result.RowsAffected() == 1 {
		return receipt, nil
	}
	replayed, found, err := s.Replay(
		ctx,
		proposal.PersonaID,
		idempotencyKey,
		commandDigest,
	)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if !found {
		return ports.CommitReceipt{}, errors.New(
			"profile proposal no-op receipt lost a concurrent insert",
		)
	}
	return replayed, nil
}

func (s *PostgresStore) Commit(
	ctx context.Context,
	expectedVersion int64,
	changes ports.ChangeSet,
) (ports.CommitReceipt, error) {
	if err := validateCommit(expectedVersion, changes); err != nil {
		return ports.CommitReceipt{}, err
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if receipt, found, err := replayReceipt(
		ctx,
		tx,
		changes.Proposal.PersonaID,
		changes.IdempotencyKey,
		changes.CommandDigest,
	); err != nil {
		return ports.CommitReceipt{}, err
	} else if found {
		if err := tx.Commit(ctx); err != nil {
			return ports.CommitReceipt{}, err
		}
		return receipt, nil
	}

	proposedChanges, err := json.Marshal(changes.Proposal.ProposedChanges)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	evidenceRefs, err := json.Marshal(changes.Proposal.EvidenceRefs)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	impactScope, err := json.Marshal(changes.Proposal.ImpactScope)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if expectedVersion == 0 {
		result, err := tx.Exec(ctx, `
INSERT INTO profile_update_proposals(
  id, persona_id, source, proposed_changes, reason, evidence_refs, impact_scope,
  created_by, created_request_id, created_trace_id, status, reviewed_by,
  target_persona_expected_version,
  apply_actor_persona_id, apply_request_id, apply_trace_id, apply_audit_id,
  rollback_deadline, rollback_actor_persona_id, rollback_request_id,
  rollback_trace_id, rollback_audit_id,
  version, created_at, updated_at, resolved_at
) VALUES (
  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
  $14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26
)
ON CONFLICT (id) DO NOTHING`,
			changes.Proposal.ID, changes.Proposal.PersonaID, changes.Proposal.Source,
			proposedChanges, changes.Proposal.Reason, evidenceRefs, impactScope,
			changes.Proposal.CreatedBy, changes.Proposal.CreatedRequestID,
			changes.Proposal.CreatedTraceID, changes.Proposal.Status,
			nullableString(changes.Proposal.ReviewedBy),
			changes.Proposal.TargetPersonaExpectedVersion,
			auditActorID(changes.Proposal.ApplyContext),
			auditRequestID(changes.Proposal.ApplyContext),
			auditTraceID(changes.Proposal.ApplyContext),
			nullableString(changes.Proposal.ApplyAuditID),
			changes.Proposal.RollbackDeadline,
			auditActorID(changes.Proposal.RollbackContext),
			auditRequestID(changes.Proposal.RollbackContext),
			auditTraceID(changes.Proposal.RollbackContext),
			nullableString(changes.Proposal.RollbackAuditID),
			changes.Proposal.Version, changes.Proposal.CreatedAt,
			changes.Proposal.UpdatedAt, changes.Proposal.ResolvedAt,
		)
		if err != nil {
			return ports.CommitReceipt{}, err
		}
		if result.RowsAffected() != 1 {
			return ports.CommitReceipt{}, model.ErrVersionConflict
		}
	} else {
		result, err := tx.Exec(ctx, `
UPDATE profile_update_proposals SET
  status=$3, reviewed_by=$4, target_persona_expected_version=$5,
  apply_actor_persona_id=$6, apply_request_id=$7, apply_trace_id=$8,
  apply_audit_id=$9, rollback_deadline=$10,
  rollback_actor_persona_id=$11, rollback_request_id=$12,
  rollback_trace_id=$13, rollback_audit_id=$14,
  version=$15, updated_at=$16, resolved_at=$17
WHERE id=$1 AND version=$2`,
			changes.Proposal.ID, expectedVersion, changes.Proposal.Status,
			nullableString(changes.Proposal.ReviewedBy), changes.Proposal.TargetPersonaExpectedVersion,
			auditActorID(changes.Proposal.ApplyContext),
			auditRequestID(changes.Proposal.ApplyContext),
			auditTraceID(changes.Proposal.ApplyContext),
			nullableString(changes.Proposal.ApplyAuditID),
			changes.Proposal.RollbackDeadline,
			auditActorID(changes.Proposal.RollbackContext),
			auditRequestID(changes.Proposal.RollbackContext),
			auditTraceID(changes.Proposal.RollbackContext),
			nullableString(changes.Proposal.RollbackAuditID),
			changes.Proposal.Version, changes.Proposal.UpdatedAt,
			changes.Proposal.ResolvedAt,
		)
		if err != nil {
			return ports.CommitReceipt{}, err
		}
		if result.RowsAffected() != 1 {
			return ports.CommitReceipt{}, model.ErrVersionConflict
		}
	}

	if changes.Audit != nil {
		beforeJSON, err := json.Marshal(changes.Audit.Before)
		if err != nil {
			return ports.CommitReceipt{}, err
		}
		afterJSON, err := json.Marshal(changes.Audit.After)
		if err != nil {
			return ports.CommitReceipt{}, err
		}
		if _, err := tx.Exec(ctx, `
INSERT INTO profile_update_proposal_audits(
  audit_id, proposal_id, action, actor_persona_id, request_id, trace_id,
  before_snapshot, after_snapshot, before_persona_version,
  after_persona_version, occurred_at, rollback_deadline
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
			changes.Audit.ID,
			changes.Audit.ProposalID,
			changes.Audit.Action,
			changes.Audit.Context.ActorPersonaID,
			changes.Audit.Context.RequestID,
			changes.Audit.Context.TraceID,
			beforeJSON,
			afterJSON,
			changes.Audit.Before.Version,
			changes.Audit.After.Version,
			changes.Audit.OccurredAt,
			changes.Audit.RollbackDeadline,
		); err != nil {
			return ports.CommitReceipt{}, err
		}
	}

	for _, event := range changes.Events {
		payload, err := marshalProposalEvent(event, changes.Proposal)
		if err != nil {
			return ports.CommitReceipt{}, err
		}
		if _, err := tx.Exec(ctx, `
INSERT INTO profile_update_proposals_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,$4,$5,$6)`,
			event.ID, event.AggregateID, event.AggregateVersion, event.Type, payload, event.OccurredAt,
		); err != nil {
			return ports.CommitReceipt{}, err
		}
	}
	receipt := ports.CommitReceipt{
		ProposalID: changes.Proposal.ID,
		Version:    changes.Proposal.Version,
		Status:     string(changes.Proposal.Status),
	}
	resultJSON, err := json.Marshal(receipt)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO profile_update_proposals_command_receipts(
  receipt_id, proposal_id, actor_persona_id, idempotency_key,
  command_digest, aggregate_version, result_json
) VALUES ($1,$2,$3,$4,$5,$6,$7)`,
		receiptID(changes.Proposal.PersonaID, changes.IdempotencyKey),
		changes.Proposal.ID, changes.Proposal.PersonaID, changes.IdempotencyKey,
		changes.CommandDigest, changes.Proposal.Version, resultJSON,
	); err != nil {
		return ports.CommitReceipt{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CommitReceipt{}, err
	}
	return receipt, nil
}

func (s *PostgresStore) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	lease time.Duration,
	limit int,
) ([]ports.OutboxEvent, error) {
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" {
		return nil, errors.New("profile proposal outbox claim owner is required")
	}
	if lease <= 0 {
		lease = time.Minute
	}
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	leaseBefore := time.Now().UTC().Add(-lease)
	rows, err := s.pool.Query(ctx, `
WITH candidates AS (
  SELECT candidate.event_id
  FROM profile_update_proposals_outbox AS candidate
  WHERE candidate.published_at IS NULL
    AND candidate.next_attempt_at <= NOW()
    AND (candidate.claim_owner IS NULL OR candidate.claimed_at < $2)
    AND NOT EXISTS (
      SELECT 1
      FROM profile_update_proposals_outbox AS earlier
      WHERE earlier.aggregate_id = candidate.aggregate_id
        AND earlier.published_at IS NULL
        AND earlier.aggregate_version < candidate.aggregate_version
    )
  ORDER BY candidate.occurred_at, candidate.event_id
  LIMIT $3
  FOR UPDATE SKIP LOCKED
),
claimed AS (
  UPDATE profile_update_proposals_outbox AS outbox
  SET claim_owner = $1, claimed_at = NOW()
  FROM candidates
  WHERE outbox.event_id = candidates.event_id
  RETURNING outbox.event_id
)
SELECT outbox.event_id, outbox.aggregate_id, outbox.aggregate_version,
       outbox.event_type, outbox.payload_json, outbox.occurred_at
FROM profile_update_proposals_outbox AS outbox
JOIN claimed USING (event_id)
ORDER BY outbox.occurred_at, outbox.event_id`,
		ownerID,
		leaseBefore,
		limit,
	)
	if err != nil {
		return nil, fmt.Errorf("claim pending profile proposal outbox: %w", err)
	}
	defer rows.Close()
	events := make([]ports.OutboxEvent, 0, limit)
	for rows.Next() {
		var event ports.OutboxEvent
		if err := rows.Scan(
			&event.EventID,
			&event.AggregateID,
			&event.AggregateVersion,
			&event.EventType,
			&event.PayloadJSON,
			&event.OccurredAt,
		); err != nil {
			return nil, fmt.Errorf("scan claimed profile proposal outbox: %w", err)
		}
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate claimed profile proposal outbox: %w", err)
	}
	return events, nil
}

func (s *PostgresStore) MarkOutboxPublished(
	ctx context.Context,
	eventID string,
	ownerID string,
) error {
	command, err := s.pool.Exec(ctx, `
UPDATE profile_update_proposals_outbox
SET published_at = NOW(), claim_owner = NULL, claimed_at = NULL, last_error = ''
WHERE event_id = $1 AND published_at IS NULL AND claim_owner = $2`,
		strings.TrimSpace(eventID),
		strings.TrimSpace(ownerID),
	)
	if err != nil {
		return fmt.Errorf("mark profile proposal outbox published: %w", err)
	}
	if command.RowsAffected() != 1 {
		return fmt.Errorf("%w: event %q", ports.ErrOutboxClaimLost, eventID)
	}
	return nil
}

func (s *PostgresStore) ReleaseOutboxClaim(
	ctx context.Context,
	eventID string,
	ownerID string,
) error {
	_, err := s.pool.Exec(ctx, `
UPDATE profile_update_proposals_outbox
SET claim_owner = NULL, claimed_at = NULL
WHERE event_id = $1 AND published_at IS NULL AND claim_owner = $2`,
		strings.TrimSpace(eventID),
		strings.TrimSpace(ownerID),
	)
	if err != nil {
		return fmt.Errorf("release profile proposal outbox claim: %w", err)
	}
	return nil
}

func validateCommit(expectedVersion int64, changes ports.ChangeSet) error {
	if expectedVersion < 0 || changes.Proposal.Version != expectedVersion+1 {
		return model.ErrVersionConflict
	}
	if err := changes.Proposal.Validate(); err != nil {
		return err
	}
	if strings.TrimSpace(changes.IdempotencyKey) == "" || len(changes.IdempotencyKey) > 160 {
		return errors.New("profile proposal idempotency key is required and must not exceed 160 bytes")
	}
	if strings.TrimSpace(changes.CommandDigest) == "" {
		return errors.New("profile proposal command digest is required")
	}
	if len(changes.Events) != 1 || changes.Events[0].AggregateID != changes.Proposal.ID ||
		changes.Events[0].AggregateVersion != changes.Proposal.Version {
		return errors.New("profile proposal commit requires exactly one version-aligned event")
	}
	if changes.Audit == nil {
		if (changes.Proposal.Status == model.StatusApplied &&
			changes.Events[0].Type != "ProfileUpdateProposalRollbackAborted") ||
			changes.Proposal.Status == model.StatusRolledBack {
			return errors.New("profile proposal terminal mutation requires immutable audit")
		}
		return nil
	}
	if err := changes.Audit.Validate(); err != nil {
		return err
	}
	if changes.Audit.ProposalID != changes.Proposal.ID {
		return errors.New("profile proposal audit aggregate mismatch")
	}
	switch changes.Audit.Action {
	case model.AuditActionApply:
		if changes.Proposal.Status != model.StatusApplied ||
			changes.Proposal.ApplyAuditID != changes.Audit.ID {
			return errors.New("profile proposal apply audit does not match applied state")
		}
	case model.AuditActionRollback:
		if changes.Proposal.Status != model.StatusRolledBack ||
			changes.Proposal.RollbackAuditID != changes.Audit.ID {
			return errors.New("profile proposal rollback audit does not match rolled_back state")
		}
	default:
		return errors.New("profile proposal audit action is invalid")
	}
	return nil
}

type proposalOutboxPayload struct {
	ID                           string                         `json:"id"`
	PersonaID                    string                         `json:"personaId"`
	Source                       model.Source                   `json:"source,omitempty"`
	ProposedChanges              *personamodel.ProfileChangeSet `json:"proposedChanges,omitempty"`
	Reason                       string                         `json:"reason,omitempty"`
	EvidenceRefs                 []string                       `json:"evidenceRefs,omitempty"`
	ImpactScope                  []string                       `json:"impactScope,omitempty"`
	CreatedBy                    string                         `json:"createdBy,omitempty"`
	CreatedRequestID             string                         `json:"createdRequestId,omitempty"`
	CreatedTraceID               string                         `json:"createdTraceId,omitempty"`
	Status                       model.Status                   `json:"status"`
	Version                      int64                          `json:"version"`
	CreatedAt                    *time.Time                     `json:"createdAt,omitempty"`
	ReviewedBy                   string                         `json:"reviewedBy,omitempty"`
	TargetPersonaExpectedVersion *int64                         `json:"targetPersonaExpectedVersion,omitempty"`
	ApplyActorPersonaID          string                         `json:"applyActorPersonaId,omitempty"`
	ApplyRequestID               string                         `json:"applyRequestId,omitempty"`
	ApplyTraceID                 string                         `json:"applyTraceId,omitempty"`
	ApplyAuditID                 string                         `json:"applyAuditId,omitempty"`
	RollbackDeadline             *time.Time                     `json:"rollbackDeadline,omitempty"`
	RollbackActorPersonaID       string                         `json:"rollbackActorPersonaId,omitempty"`
	RollbackRequestID            string                         `json:"rollbackRequestId,omitempty"`
	RollbackTraceID              string                         `json:"rollbackTraceId,omitempty"`
	RollbackAuditID              string                         `json:"rollbackAuditId,omitempty"`
	ResolvedAt                   *time.Time                     `json:"resolvedAt,omitempty"`
}

func marshalProposalEvent(
	event model.Event,
	proposal model.ProfileUpdateProposal,
) ([]byte, error) {
	payload := proposalOutboxPayload{
		ID: proposal.ID, PersonaID: proposal.PersonaID,
		Status: proposal.Status, Version: proposal.Version,
	}
	switch event.Type {
	case "ProfileUpdateProposalCreated":
		changes := proposal.ProposedChanges
		createdAt := proposal.CreatedAt
		payload.Source = proposal.Source
		payload.ProposedChanges = &changes
		payload.Reason = proposal.Reason
		payload.EvidenceRefs = proposal.EvidenceRefs
		payload.ImpactScope = proposal.ImpactScope
		payload.CreatedBy = proposal.CreatedBy
		payload.CreatedRequestID = proposal.CreatedRequestID
		payload.CreatedTraceID = proposal.CreatedTraceID
		payload.CreatedAt = &createdAt
	case "ProfileUpdateProposalConfirmed":
		payload.ReviewedBy = proposal.ReviewedBy
		payload.TargetPersonaExpectedVersion = proposal.TargetPersonaExpectedVersion
	case "ProfileUpdateProposalApplyStarted":
		if proposal.ApplyContext == nil {
			return nil, errors.New("apply started event requires apply context")
		}
		payload.ApplyActorPersonaID = proposal.ApplyContext.ActorPersonaID
		payload.ApplyRequestID = proposal.ApplyContext.RequestID
		payload.ApplyTraceID = proposal.ApplyContext.TraceID
	case "ProfileUpdateProposalApplied":
		payload.ResolvedAt = proposal.ResolvedAt
		payload.ApplyAuditID = proposal.ApplyAuditID
		payload.RollbackDeadline = proposal.RollbackDeadline
	case "ProfileUpdateProposalRollbackStarted":
		if proposal.RollbackContext == nil {
			return nil, errors.New("rollback started event requires rollback context")
		}
		payload.ApplyAuditID = proposal.ApplyAuditID
		payload.RollbackActorPersonaID = proposal.RollbackContext.ActorPersonaID
		payload.RollbackRequestID = proposal.RollbackContext.RequestID
		payload.RollbackTraceID = proposal.RollbackContext.TraceID
	case "ProfileUpdateProposalRollbackAborted":
		payload.ApplyAuditID = proposal.ApplyAuditID
	case "ProfileUpdateProposalRolledBack":
		payload.ResolvedAt = proposal.ResolvedAt
		payload.ApplyAuditID = proposal.ApplyAuditID
		payload.RollbackAuditID = proposal.RollbackAuditID
	case "ProfileUpdateProposalRejected":
		payload.ReviewedBy = proposal.ReviewedBy
		payload.ResolvedAt = proposal.ResolvedAt
	case "ProfileUpdateProposalExpired":
		payload.ResolvedAt = proposal.ResolvedAt
	default:
		return nil, fmt.Errorf("unknown profile proposal event type %q", event.Type)
	}
	return json.Marshal(payload)
}

type rowScanner interface {
	Scan(...any) error
}

const proposalSelect = `SELECT
  id, persona_id, source, proposed_changes, reason, evidence_refs, impact_scope,
  created_by, created_request_id, created_trace_id, status, reviewed_by,
  target_persona_expected_version,
  apply_actor_persona_id, apply_request_id, apply_trace_id, apply_audit_id,
  rollback_deadline, rollback_actor_persona_id, rollback_request_id,
  rollback_trace_id, rollback_audit_id,
  version, created_at, updated_at, resolved_at
FROM profile_update_proposals`

func scanProposal(row rowScanner) (model.ProfileUpdateProposal, error) {
	var proposal model.ProfileUpdateProposal
	var proposedChanges []byte
	var evidenceRefs []byte
	var impactScope []byte
	var reviewedBy *string
	var applyActorPersonaID, applyRequestID, applyTraceID *string
	var applyAuditID *string
	var rollbackActorPersonaID, rollbackRequestID, rollbackTraceID *string
	var rollbackAuditID *string
	err := row.Scan(
		&proposal.ID, &proposal.PersonaID, &proposal.Source, &proposedChanges,
		&proposal.Reason, &evidenceRefs, &impactScope,
		&proposal.CreatedBy, &proposal.CreatedRequestID, &proposal.CreatedTraceID,
		&proposal.Status, &reviewedBy, &proposal.TargetPersonaExpectedVersion,
		&applyActorPersonaID, &applyRequestID, &applyTraceID, &applyAuditID,
		&proposal.RollbackDeadline,
		&rollbackActorPersonaID, &rollbackRequestID, &rollbackTraceID, &rollbackAuditID,
		&proposal.Version, &proposal.CreatedAt, &proposal.UpdatedAt, &proposal.ResolvedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return model.ProfileUpdateProposal{}, model.ErrNotFound
	}
	if err != nil {
		return model.ProfileUpdateProposal{}, err
	}
	if reviewedBy != nil {
		proposal.ReviewedBy = *reviewedBy
	}
	if applyActorPersonaID != nil && applyRequestID != nil && applyTraceID != nil {
		proposal.ApplyContext = &model.CommandAuditContext{
			ActorPersonaID: *applyActorPersonaID,
			RequestID:      *applyRequestID,
			TraceID:        *applyTraceID,
		}
	}
	if applyAuditID != nil {
		proposal.ApplyAuditID = *applyAuditID
	}
	if rollbackActorPersonaID != nil && rollbackRequestID != nil && rollbackTraceID != nil {
		proposal.RollbackContext = &model.CommandAuditContext{
			ActorPersonaID: *rollbackActorPersonaID,
			RequestID:      *rollbackRequestID,
			TraceID:        *rollbackTraceID,
		}
	}
	if rollbackAuditID != nil {
		proposal.RollbackAuditID = *rollbackAuditID
	}
	if err := json.Unmarshal(proposedChanges, &proposal.ProposedChanges); err != nil {
		return model.ProfileUpdateProposal{}, err
	}
	if err := json.Unmarshal(evidenceRefs, &proposal.EvidenceRefs); err != nil {
		return model.ProfileUpdateProposal{}, err
	}
	if err := json.Unmarshal(impactScope, &proposal.ImpactScope); err != nil {
		return model.ProfileUpdateProposal{}, err
	}
	return proposal, proposal.Validate()
}

type queryRower interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

func replayReceipt(
	ctx context.Context,
	querier queryRower,
	actorPersonaID string,
	idempotencyKey string,
	commandDigest string,
) (ports.CommitReceipt, bool, error) {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	commandDigest = strings.TrimSpace(commandDigest)
	if actorPersonaID == "" || idempotencyKey == "" || commandDigest == "" {
		return ports.CommitReceipt{}, false, errors.New("receipt lookup requires actor, idempotency key and command digest")
	}
	var resultJSON []byte
	var storedDigest string
	err := querier.QueryRow(ctx, `
SELECT command_digest, result_json
FROM profile_update_proposals_command_receipts
WHERE actor_persona_id=$1 AND idempotency_key=$2`, actorPersonaID, idempotencyKey).
		Scan(&storedDigest, &resultJSON)
	if errors.Is(err, pgx.ErrNoRows) {
		return ports.CommitReceipt{}, false, nil
	}
	if err != nil {
		return ports.CommitReceipt{}, false, err
	}
	if storedDigest != commandDigest {
		return ports.CommitReceipt{}, false, model.ErrIdempotencyConflict
	}
	var receipt ports.CommitReceipt
	if err := json.Unmarshal(resultJSON, &receipt); err != nil {
		return ports.CommitReceipt{}, false, err
	}
	receipt.Replayed = true
	return receipt, true, nil
}

func receiptID(actorPersonaID, idempotencyKey string) string {
	digest := sha256.Sum256([]byte(actorPersonaID + "\x00" + idempotencyKey))
	return fmt.Sprintf("profile-proposal-receipt-%x", digest[:16])
}

func nullableString(value string) *string {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	return &value
}

func auditActorID(context *model.CommandAuditContext) *string {
	if context == nil {
		return nil
	}
	return nullableString(context.ActorPersonaID)
}

func auditRequestID(context *model.CommandAuditContext) *string {
	if context == nil {
		return nil
	}
	return nullableString(context.RequestID)
}

func auditTraceID(context *model.CommandAuditContext) *string {
	if context == nil {
		return nil
	}
	return nullableString(context.TraceID)
}
