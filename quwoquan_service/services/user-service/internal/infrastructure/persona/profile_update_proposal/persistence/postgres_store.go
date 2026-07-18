package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/model"
	"quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/ports"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

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
	proposalID string,
	idempotencyKey string,
	commandDigest string,
) (ports.CommitReceipt, bool, error) {
	return replayReceipt(ctx, s.pool, proposalID, idempotencyKey, commandDigest)
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
		proposal.ID,
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
  receipt_id, proposal_id, idempotency_key, command_digest,
  aggregate_version, result_json
) VALUES ($1,$2,$3,$4,$5,$6)
ON CONFLICT (proposal_id, idempotency_key) DO NOTHING`,
		receiptID(proposal.ID, idempotencyKey), proposal.ID, idempotencyKey,
		commandDigest, proposal.Version, resultJSON,
	)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	if result.RowsAffected() == 1 {
		return receipt, nil
	}
	replayed, found, err := s.Replay(
		ctx,
		proposal.ID,
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

	if receipt, found, err := replayReceipt(ctx, tx, changes.Proposal.ID, changes.IdempotencyKey, changes.CommandDigest); err != nil {
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
	if expectedVersion == 0 {
		result, err := tx.Exec(ctx, `
INSERT INTO profile_update_proposals(
  id, persona_id, source, proposed_changes, status, reviewed_by,
  target_persona_expected_version, version, created_at, updated_at, resolved_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
ON CONFLICT (id) DO NOTHING`,
			changes.Proposal.ID, changes.Proposal.PersonaID, changes.Proposal.Source,
			proposedChanges, changes.Proposal.Status, nullableString(changes.Proposal.ReviewedBy),
			changes.Proposal.TargetPersonaExpectedVersion, changes.Proposal.Version,
			changes.Proposal.CreatedAt, changes.Proposal.UpdatedAt, changes.Proposal.ResolvedAt,
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
  version=$6, updated_at=$7, resolved_at=$8
WHERE id=$1 AND version=$2`,
			changes.Proposal.ID, expectedVersion, changes.Proposal.Status,
			nullableString(changes.Proposal.ReviewedBy), changes.Proposal.TargetPersonaExpectedVersion,
			changes.Proposal.Version, changes.Proposal.UpdatedAt, changes.Proposal.ResolvedAt,
		)
		if err != nil {
			return ports.CommitReceipt{}, err
		}
		if result.RowsAffected() != 1 {
			return ports.CommitReceipt{}, model.ErrVersionConflict
		}
	}

	for _, event := range changes.Events {
		payload, err := json.Marshal(struct {
			Proposal model.ProfileUpdateProposal `json:"proposal"`
		}{Proposal: changes.Proposal})
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
  receipt_id, proposal_id, idempotency_key, command_digest,
  aggregate_version, result_json
) VALUES ($1,$2,$3,$4,$5,$6)`,
		receiptID(changes.Proposal.ID, changes.IdempotencyKey), changes.Proposal.ID,
		changes.IdempotencyKey, changes.CommandDigest, changes.Proposal.Version, resultJSON,
	); err != nil {
		return ports.CommitReceipt{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return ports.CommitReceipt{}, err
	}
	return receipt, nil
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
	return nil
}

type rowScanner interface {
	Scan(...any) error
}

const proposalSelect = `SELECT
  id, persona_id, source, proposed_changes, status, reviewed_by,
  target_persona_expected_version, version, created_at, updated_at, resolved_at
FROM profile_update_proposals`

func scanProposal(row rowScanner) (model.ProfileUpdateProposal, error) {
	var proposal model.ProfileUpdateProposal
	var proposedChanges []byte
	var reviewedBy *string
	err := row.Scan(
		&proposal.ID, &proposal.PersonaID, &proposal.Source, &proposedChanges,
		&proposal.Status, &reviewedBy, &proposal.TargetPersonaExpectedVersion,
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
	if err := json.Unmarshal(proposedChanges, &proposal.ProposedChanges); err != nil {
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
	proposalID string,
	idempotencyKey string,
	commandDigest string,
) (ports.CommitReceipt, bool, error) {
	proposalID = strings.TrimSpace(proposalID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	commandDigest = strings.TrimSpace(commandDigest)
	if proposalID == "" || idempotencyKey == "" || commandDigest == "" {
		return ports.CommitReceipt{}, false, errors.New("receipt lookup requires proposal, idempotency key and command digest")
	}
	var resultJSON []byte
	var storedDigest string
	err := querier.QueryRow(ctx, `
SELECT command_digest, result_json
FROM profile_update_proposals_command_receipts
WHERE proposal_id=$1 AND idempotency_key=$2`, proposalID, idempotencyKey).
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

func receiptID(proposalID, idempotencyKey string) string {
	digest := sha256.Sum256([]byte(proposalID + "\x00" + idempotencyKey))
	return fmt.Sprintf("profile-proposal-receipt-%x", digest[:16])
}

func nullableString(value string) *string {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	return &value
}
