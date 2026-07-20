// Package persistence 提供 SubjectFollow 的 PostgreSQL 对象专属 Store：
// state/version、幂等 receipt 与事务 outbox 在同一事务原子提交。
package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	sfmodel "quwoquan_service/services/user-service/internal/domain/relationship/subject_follow/model"
	sfports "quwoquan_service/services/user-service/internal/domain/relationship/subject_follow/ports"
)

type PgSubjectFollowStore struct {
	pool *pgxpool.Pool
}

var _ sfports.SubjectFollowStore = (*PgSubjectFollowStore)(nil)
var _ sfports.SubjectFollowOutbox = (*PgSubjectFollowStore)(nil)

func NewPgSubjectFollowStore(pool *pgxpool.Pool) *PgSubjectFollowStore {
	return &PgSubjectFollowStore{pool: pool}
}

func (s *PgSubjectFollowStore) Apply(
	ctx context.Context,
	command sfmodel.Command,
) (sfmodel.MutationResult, error) {
	if s == nil || s.pool == nil {
		return sfmodel.MutationResult{}, errors.New("subject follow store is unavailable")
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return sfmodel.MutationResult{}, fmt.Errorf("begin subject follow transaction: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()

	if command.IdempotencyKey != "" {
		if err := lockIdempotencyKey(ctx, tx, command.PersonaID, command.IdempotencyKey); err != nil {
			return sfmodel.MutationResult{}, err
		}
		replay, found, err := loadReceipt(ctx, tx, command)
		if err != nil {
			return sfmodel.MutationResult{}, err
		}
		if found {
			if err := tx.Commit(ctx); err != nil {
				return sfmodel.MutationResult{}, fmt.Errorf("commit subject follow replay: %w", err)
			}
			committed = true
			replay.IdempotentReplay = true
			return replay, nil
		}
	}

	current, exists, err := lockRow(ctx, tx, command)
	if err != nil {
		return sfmodel.MutationResult{}, err
	}
	now := time.Now().UTC()
	next, changed := sfmodel.Apply(current, exists, command, now)
	result := sfmodel.MutationResult{Follow: next, Changed: changed, OccurredAt: now}
	if changed {
		if !exists {
			next.ID = "sf_" + uuid.NewString()
			result.Follow.ID = next.ID
			if _, err := tx.Exec(ctx, `
				INSERT INTO subject_follows (id, persona_id, subject_type, subject_id, state, version, followed_at, updated_at)
				VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
				next.ID, next.PersonaID, next.SubjectType, next.SubjectID,
				next.State, next.Version, next.FollowedAt, next.UpdatedAt,
			); err != nil {
				return sfmodel.MutationResult{}, fmt.Errorf("insert subject follow: %w", err)
			}
		} else {
			tag, err := tx.Exec(ctx, `
				UPDATE subject_follows
				SET state = $2, version = $3, followed_at = $4, updated_at = $5
				WHERE id = $1 AND version = $6`,
				next.ID, next.State, next.Version, next.FollowedAt, next.UpdatedAt, current.Version,
			)
			if err != nil {
				return sfmodel.MutationResult{}, fmt.Errorf("update subject follow: %w", err)
			}
			if tag.RowsAffected() != 1 {
				return sfmodel.MutationResult{}, errors.New("subject follow version changed before commit")
			}
		}
		if err := appendOutbox(ctx, tx, next, now); err != nil {
			return sfmodel.MutationResult{}, err
		}
	}
	if command.IdempotencyKey != "" {
		if err := saveReceipt(ctx, tx, command, result); err != nil {
			return sfmodel.MutationResult{}, err
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return sfmodel.MutationResult{}, fmt.Errorf("commit subject follow command: %w", err)
	}
	committed = true
	return result, nil
}

func lockIdempotencyKey(ctx context.Context, tx pgx.Tx, personaID, key string) error {
	digest := sha256.Sum256([]byte(personaID + "\x1f" + key))
	lockKey := hex.EncodeToString(digest[:])
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`, lockKey); err != nil {
		return fmt.Errorf("lock subject follow idempotency key: %w", err)
	}
	return nil
}

func loadReceipt(ctx context.Context, tx pgx.Tx, command sfmodel.Command) (sfmodel.MutationResult, bool, error) {
	var (
		operation string
		payload   []byte
	)
	err := tx.QueryRow(ctx, `
		SELECT operation, response_json
		FROM subject_follow_command_receipts
		WHERE persona_id = $1 AND idempotency_key = $2`,
		command.PersonaID, command.IdempotencyKey,
	).Scan(&operation, &payload)
	if errors.Is(err, pgx.ErrNoRows) {
		return sfmodel.MutationResult{}, false, nil
	}
	if err != nil {
		return sfmodel.MutationResult{}, false, fmt.Errorf("load subject follow receipt: %w", err)
	}
	if operation != command.Kind {
		return sfmodel.MutationResult{}, false, errors.New(
			"subject follow idempotency key was reused with a different command",
		)
	}
	var result sfmodel.MutationResult
	if err := json.Unmarshal(payload, &result); err != nil {
		return sfmodel.MutationResult{}, false, fmt.Errorf("decode subject follow receipt: %w", err)
	}
	return result, true, nil
}

func saveReceipt(ctx context.Context, tx pgx.Tx, command sfmodel.Command, result sfmodel.MutationResult) error {
	payload, err := json.Marshal(result)
	if err != nil {
		return fmt.Errorf("encode subject follow receipt: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO subject_follow_command_receipts (
			receipt_id, persona_id, idempotency_key, operation,
			aggregate_id, aggregate_version, response_json
		) VALUES ($1, $2, $3, $4, $5, $6, $7)`,
		"sfr_"+uuid.NewString(), command.PersonaID, command.IdempotencyKey,
		command.Kind, result.Follow.ID, result.Follow.Version, payload,
	); err != nil {
		return fmt.Errorf("save subject follow receipt: %w", err)
	}
	return nil
}

func lockRow(ctx context.Context, tx pgx.Tx, command sfmodel.Command) (sfmodel.SubjectFollow, bool, error) {
	var follow sfmodel.SubjectFollow
	err := tx.QueryRow(ctx, `
		SELECT id, persona_id, subject_type, subject_id, state, version, followed_at, updated_at
		FROM subject_follows
		WHERE persona_id = $1 AND subject_type = $2 AND subject_id = $3
		FOR UPDATE`,
		command.PersonaID, command.SubjectType, command.SubjectID,
	).Scan(&follow.ID, &follow.PersonaID, &follow.SubjectType, &follow.SubjectID,
		&follow.State, &follow.Version, &follow.FollowedAt, &follow.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return sfmodel.SubjectFollow{}, false, nil
	}
	if err != nil {
		return sfmodel.SubjectFollow{}, false, fmt.Errorf("lock subject follow row: %w", err)
	}
	return follow, true, nil
}

func appendOutbox(ctx context.Context, tx pgx.Tx, follow sfmodel.SubjectFollow, now time.Time) error {
	payload := sfmodel.EventPayload{
		ID:          follow.ID,
		PersonaID:   follow.PersonaID,
		SubjectType: follow.SubjectType,
		SubjectID:   follow.SubjectID,
		State:       follow.State,
		Version:     follow.Version,
		OccurredAt:  now,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("encode subject follow event: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO subject_follow_outbox (
			event_id, aggregate_id, aggregate_version, event_name, payload_json, occurred_at
		) VALUES ($1, $2, $3, $4, $5, $6)`,
		"sfe_"+uuid.NewString(), follow.ID, follow.Version,
		sfmodel.EventSubjectFollowStateChanged, body, now,
	); err != nil {
		return fmt.Errorf("append subject follow outbox: %w", err)
	}
	return nil
}

func (s *PgSubjectFollowStore) Get(
	ctx context.Context,
	personaID, subjectType, subjectID string,
) (sfmodel.SubjectFollow, bool, error) {
	var follow sfmodel.SubjectFollow
	err := s.pool.QueryRow(ctx, `
		SELECT id, persona_id, subject_type, subject_id, state, version, followed_at, updated_at
		FROM subject_follows
		WHERE persona_id = $1 AND subject_type = $2 AND subject_id = $3`,
		personaID, subjectType, subjectID,
	).Scan(&follow.ID, &follow.PersonaID, &follow.SubjectType, &follow.SubjectID,
		&follow.State, &follow.Version, &follow.FollowedAt, &follow.UpdatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return sfmodel.SubjectFollow{}, false, nil
	}
	if err != nil {
		return sfmodel.SubjectFollow{}, false, fmt.Errorf("get subject follow: %w", err)
	}
	return follow, true, nil
}

func (s *PgSubjectFollowStore) ListFollowingByPersona(
	ctx context.Context,
	personaID string,
) ([]sfmodel.SubjectFollow, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, persona_id, subject_type, subject_id, state, version, followed_at, updated_at
		FROM subject_follows
		WHERE persona_id = $1 AND state = 'following'
		ORDER BY followed_at DESC`,
		personaID,
	)
	if err != nil {
		return nil, fmt.Errorf("list subject follows: %w", err)
	}
	defer rows.Close()
	var result []sfmodel.SubjectFollow
	for rows.Next() {
		var follow sfmodel.SubjectFollow
		if err := rows.Scan(&follow.ID, &follow.PersonaID, &follow.SubjectType, &follow.SubjectID,
			&follow.State, &follow.Version, &follow.FollowedAt, &follow.UpdatedAt); err != nil {
			return nil, fmt.Errorf("scan subject follow: %w", err)
		}
		result = append(result, follow)
	}
	return result, rows.Err()
}

func (s *PgSubjectFollowStore) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	lease time.Duration,
	limit int,
) ([]sfmodel.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	rows, err := s.pool.Query(ctx, `
		UPDATE subject_follow_outbox
		SET claim_owner = $1, claimed_at = NOW()
		WHERE event_id IN (
			SELECT event_id FROM subject_follow_outbox
			WHERE published_at IS NULL
			  AND (claim_owner IS NULL OR claimed_at < NOW() - $2::interval)
			ORDER BY occurred_at
			LIMIT $3
			FOR UPDATE SKIP LOCKED
		)
		RETURNING event_id, aggregate_id, aggregate_version, event_name, payload_json, occurred_at`,
		ownerID, lease.String(), limit,
	)
	if err != nil {
		return nil, fmt.Errorf("claim subject follow outbox: %w", err)
	}
	defer rows.Close()
	var events []sfmodel.OutboxEvent
	for rows.Next() {
		var (
			event   sfmodel.OutboxEvent
			payload []byte
		)
		if err := rows.Scan(&event.EventID, &event.AggregateID, &event.Version,
			&event.EventName, &payload, &event.OccurredAt); err != nil {
			return nil, fmt.Errorf("scan subject follow outbox: %w", err)
		}
		if err := json.Unmarshal(payload, &event.Payload); err != nil {
			return nil, fmt.Errorf("decode subject follow outbox payload: %w", err)
		}
		events = append(events, event)
	}
	return events, rows.Err()
}

func (s *PgSubjectFollowStore) MarkOutboxPublished(ctx context.Context, eventID, ownerID string) error {
	tag, err := s.pool.Exec(ctx, `
		UPDATE subject_follow_outbox
		SET published_at = NOW()
		WHERE event_id = $1 AND claim_owner = $2 AND published_at IS NULL`,
		eventID, ownerID,
	)
	if err != nil {
		return fmt.Errorf("mark subject follow outbox published: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return sfports.ErrOutboxClaimLost
	}
	return nil
}

func (s *PgSubjectFollowStore) ReleaseOutboxClaim(ctx context.Context, eventID, ownerID string) error {
	if _, err := s.pool.Exec(ctx, `
		UPDATE subject_follow_outbox
		SET claim_owner = NULL, claimed_at = NULL
		WHERE event_id = $1 AND claim_owner = $2 AND published_at IS NULL`,
		eventID, ownerID,
	); err != nil {
		return fmt.Errorf("release subject follow outbox claim: %w", err)
	}
	return nil
}
