package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
)

// PgPersonaRelationshipStore is the single authoritative store for every
// direction in a persona pair. It deliberately owns follow and block together
// so a block can clear both follow directions and write the outbox atomically.
type PgPersonaRelationshipStore struct {
	pool *pgxpool.Pool
}

var _ relports.PersonaRelationshipStore = (*PgPersonaRelationshipStore)(nil)
var _ relports.PersonaRelationshipOutbox = (*PgPersonaRelationshipStore)(nil)

func NewPgPersonaRelationshipStore(pool *pgxpool.Pool) *PgPersonaRelationshipStore {
	return &PgPersonaRelationshipStore{pool: pool}
}

func (s *PgPersonaRelationshipStore) Apply(
	ctx context.Context,
	command relmodel.Command,
) (relmodel.MutationResult, error) {
	pair, err := relmodel.NewPair(command.SourcePersonaID, command.TargetPersonaID)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	if s == nil || s.pool == nil {
		return relmodel.MutationResult{}, errors.New("persona relationship store is unavailable")
	}

	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return relmodel.MutationResult{}, fmt.Errorf("begin persona relationship transaction: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()

	command.IdempotencyKey = strings.TrimSpace(command.IdempotencyKey)
	if command.IdempotencyKey != "" {
		if err := lockIdempotencyKey(ctx, tx, command.SourcePersonaID, command.IdempotencyKey); err != nil {
			return relmodel.MutationResult{}, err
		}
		replay, found, err := loadReceipt(ctx, tx, command)
		if err != nil {
			return relmodel.MutationResult{}, err
		}
		if found {
			if err := tx.Commit(ctx); err != nil {
				return relmodel.MutationResult{}, fmt.Errorf("commit persona relationship replay: %w", err)
			}
			committed = true
			replay.IdempotentReplay = true
			return replay, nil
		}
	}

	version, exists, err := lockPair(ctx, tx, pair, command.Kind)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	if !exists {
		result := relmodel.MutationResult{OccurredAt: time.Now().UTC()}
		if err := tx.Commit(ctx); err != nil {
			return relmodel.MutationResult{}, fmt.Errorf("commit missing persona relationship command: %w", err)
		}
		committed = true
		return result, nil
	}

	directions, err := loadLockedDirections(ctx, tx, pair.ID)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	result, dirty, err := applyCommand(command, pair, version, directions)
	if err != nil {
		return relmodel.MutationResult{}, err
	}
	if result.Changed {
		version++
		result.State.Version = version
		if _, err := tx.Exec(ctx, `
			UPDATE persona_relationships
			SET version = $2, updated_at = $3
			WHERE pair_id = $1`, pair.ID, version, result.OccurredAt); err != nil {
			return relmodel.MutationResult{}, fmt.Errorf("advance persona relationship version: %w", err)
		}
		for _, direction := range dirty {
			if err := upsertDirection(ctx, tx, direction); err != nil {
				return relmodel.MutationResult{}, err
			}
		}
		if err := appendOutbox(ctx, tx, pair.ID, version, command, result); err != nil {
			return relmodel.MutationResult{}, err
		}
	}
	if err := saveReceipt(ctx, tx, command, pair.ID, result.State.Version, result); err != nil {
		return relmodel.MutationResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return relmodel.MutationResult{}, fmt.Errorf("commit persona relationship command: %w", err)
	}
	committed = true
	return result, nil
}

func lockIdempotencyKey(ctx context.Context, tx pgx.Tx, actorPersonaID, key string) error {
	// PostgreSQL text parameters cannot contain NUL. Hash the structured input
	// before it reaches SQL so delimiters in IDs or client keys cannot alias a
	// different command and no binary control character reaches the driver.
	digest := sha256.Sum256([]byte(actorPersonaID + "\x1f" + key))
	lockKey := hex.EncodeToString(digest[:])
	_, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`, lockKey)
	if err != nil {
		return fmt.Errorf("lock persona relationship idempotency key: %w", err)
	}
	return nil
}

func loadReceipt(ctx context.Context, tx pgx.Tx, command relmodel.Command) (relmodel.MutationResult, bool, error) {
	var (
		operation string
		target    string
		payload   []byte
	)
	err := tx.QueryRow(ctx, `
		SELECT operation, target_persona_id, response_json
		FROM persona_relationship_command_receipts
		WHERE actor_persona_id = $1 AND idempotency_key = $2`,
		command.SourcePersonaID, command.IdempotencyKey,
	).Scan(&operation, &target, &payload)
	if errors.Is(err, pgx.ErrNoRows) {
		return relmodel.MutationResult{}, false, nil
	}
	if err != nil {
		return relmodel.MutationResult{}, false, fmt.Errorf("load persona relationship receipt: %w", err)
	}
	if operation != string(command.Kind) || target != command.TargetPersonaID {
		return relmodel.MutationResult{}, false, errors.New("idempotency key already belongs to a different persona relationship command")
	}
	var result relmodel.MutationResult
	if err := json.Unmarshal(payload, &result); err != nil {
		return relmodel.MutationResult{}, false, fmt.Errorf("decode persona relationship receipt: %w", err)
	}
	return result, true, nil
}

func lockPair(ctx context.Context, tx pgx.Tx, pair relmodel.Pair, kind relmodel.CommandKind) (int64, bool, error) {
	if kind == relmodel.CommandFollow || kind == relmodel.CommandBlock {
		if _, err := tx.Exec(ctx, `
			INSERT INTO persona_relationships (
				pair_id, lower_persona_id, upper_persona_id, version, created_at, updated_at
			) VALUES ($1, $2, $3, 0, NOW(), NOW())
			ON CONFLICT (lower_persona_id, upper_persona_id) DO NOTHING`,
			pair.ID, pair.LowerPersonaID, pair.UpperPersonaID); err != nil {
			return 0, false, fmt.Errorf("ensure persona relationship pair: %w", err)
		}
	}
	var version int64
	err := tx.QueryRow(ctx, `
		SELECT version FROM persona_relationships WHERE pair_id = $1 FOR UPDATE`, pair.ID,
	).Scan(&version)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, false, nil
	}
	if err != nil {
		return 0, false, fmt.Errorf("lock persona relationship pair: %w", err)
	}
	return version, true, nil
}

func loadLockedDirections(ctx context.Context, tx pgx.Tx, pairID string) (map[string]relmodel.Direction, error) {
	rows, err := tx.Query(ctx, `
		SELECT pair_id, source_persona_id, target_persona_id, following, blocked,
			follow_source, followed_at, blocked_at, updated_at
		FROM persona_relationship_directions
		WHERE pair_id = $1 FOR UPDATE`, pairID)
	if err != nil {
		return nil, fmt.Errorf("load persona relationship directions: %w", err)
	}
	defer rows.Close()
	directions := make(map[string]relmodel.Direction, 2)
	for rows.Next() {
		direction, err := scanDirection(rows)
		if err != nil {
			return nil, err
		}
		directions[direction.SourcePersonaID] = direction
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate persona relationship directions: %w", err)
	}
	return directions, nil
}

func applyCommand(
	command relmodel.Command,
	pair relmodel.Pair,
	version int64,
	directions map[string]relmodel.Direction,
) (relmodel.MutationResult, []relmodel.Direction, error) {
	now := time.Now().UTC()
	result := relmodel.MutationResult{
		OccurredAt: now,
		State:      relationshipState(pair.ID, version, command.SourcePersonaID, command.TargetPersonaID, directions, now),
	}
	source := directions[command.SourcePersonaID]
	if source.SourcePersonaID == "" {
		source = relmodel.Direction{
			PairID:          pair.ID,
			SourcePersonaID: command.SourcePersonaID,
			TargetPersonaID: command.TargetPersonaID,
			UpdatedAt:       now,
		}
	}
	dirty := make([]relmodel.Direction, 0, 2)

	switch command.Kind {
	case relmodel.CommandFollow:
		for _, direction := range directions {
			if direction.Blocked {
				return relmodel.MutationResult{}, nil, relmodel.ErrFollowBlocked
			}
		}
		if !source.Following {
			source.Following = true
			source.FollowSource = normalizedFollowSource(command.FollowSource)
			source.FollowedAt = &now
			source.UpdatedAt = now
			directions[source.SourcePersonaID] = source
			dirty = append(dirty, source)
			result.Changed = true
			result.EventName = "PersonaFollowStateChanged"
		}
	case relmodel.CommandUnfollow:
		if source.SourcePersonaID != "" && source.Following {
			source.Following = false
			source.UpdatedAt = now
			directions[source.SourcePersonaID] = source
			dirty = append(dirty, source)
			result.Changed = true
			result.EventName = "PersonaFollowStateChanged"
		}
	case relmodel.CommandBlock:
		if !source.Blocked {
			source.Blocked = true
			source.BlockedAt = &now
			source.UpdatedAt = now
			directions[source.SourcePersonaID] = source
			dirty = append(dirty, source)
			result.Changed = true
		}
		for actorID, direction := range directions {
			if !direction.Following {
				continue
			}
			result.ClearedFollowing = append(result.ClearedFollowing, direction)
			direction.Following = false
			direction.UpdatedAt = now
			directions[actorID] = direction
			dirty = upsertDirtyDirection(dirty, direction)
			result.Changed = true
		}
		if result.Changed {
			result.EventName = "PersonaBlocked"
		}
	case relmodel.CommandUnblock:
		if source.SourcePersonaID != "" && source.Blocked {
			source.Blocked = false
			source.BlockedAt = nil
			source.UpdatedAt = now
			directions[source.SourcePersonaID] = source
			dirty = append(dirty, source)
			result.Changed = true
			result.EventName = "PersonaUnblocked"
		}
	default:
		return relmodel.MutationResult{}, nil, fmt.Errorf("unsupported persona relationship command %q", command.Kind)
	}
	if result.Changed {
		result.State = relationshipState(pair.ID, version+1, command.SourcePersonaID, command.TargetPersonaID, directions, now)
	}
	return result, dirty, nil
}

func upsertDirtyDirection(values []relmodel.Direction, next relmodel.Direction) []relmodel.Direction {
	for index := range values {
		if values[index].SourcePersonaID == next.SourcePersonaID {
			values[index] = next
			return values
		}
	}
	return append(values, next)
}

func normalizedFollowSource(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "profile"
	}
	return value
}

func relationshipState(
	pairID string,
	version int64,
	viewerPersonaID, targetPersonaID string,
	directions map[string]relmodel.Direction,
	updatedAt time.Time,
) relmodel.RelationshipState {
	viewer := directions[viewerPersonaID]
	target := directions[targetPersonaID]
	return relmodel.RelationshipState{
		PairID:       pairID,
		Version:      version,
		IsFollowing:  viewer.Following,
		IsFollowedBy: target.Following,
		IsMutual:     viewer.Following && target.Following,
		IsBlocked:    viewer.Blocked,
		IsBlockedBy:  target.Blocked,
		UpdatedAt:    updatedAt,
	}
}

func upsertDirection(ctx context.Context, tx pgx.Tx, direction relmodel.Direction) error {
	_, err := tx.Exec(ctx, `
		INSERT INTO persona_relationship_directions (
			pair_id, source_persona_id, target_persona_id, following, blocked,
			follow_source, followed_at, blocked_at, updated_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
		ON CONFLICT (pair_id, source_persona_id) DO UPDATE SET
			target_persona_id = EXCLUDED.target_persona_id,
			following = EXCLUDED.following,
			blocked = EXCLUDED.blocked,
			follow_source = EXCLUDED.follow_source,
			followed_at = EXCLUDED.followed_at,
			blocked_at = EXCLUDED.blocked_at,
			updated_at = EXCLUDED.updated_at`,
		direction.PairID,
		direction.SourcePersonaID,
		direction.TargetPersonaID,
		direction.Following,
		direction.Blocked,
		nullableString(direction.FollowSource),
		direction.FollowedAt,
		direction.BlockedAt,
		direction.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("upsert persona relationship direction: %w", err)
	}
	return nil
}

func appendOutbox(
	ctx context.Context,
	tx pgx.Tx,
	pairID string,
	version int64,
	command relmodel.Command,
	result relmodel.MutationResult,
) error {
	sourceFollowCleared, targetFollowCleared := clearedFollowDirections(
		command,
		result.ClearedFollowing,
	)
	payload, err := json.Marshal(relmodel.OutboxPayload{
		PairID:                  pairID,
		SourcePersonaID:         command.SourcePersonaID,
		TargetPersonaID:         command.TargetPersonaID,
		Following:               result.State.IsFollowing,
		SourceFollowCleared:     sourceFollowCleared,
		TargetFollowCleared:     targetFollowCleared,
		ClearedFollowDirections: len(result.ClearedFollowing),
		Version:                 version,
		OccurredAt:              result.OccurredAt,
	})
	if err != nil {
		return fmt.Errorf("marshal persona relationship outbox: %w", err)
	}
	_, err = tx.Exec(ctx, `
		INSERT INTO persona_relationship_outbox (
			event_id, aggregate_id, aggregate_version, event_name, payload_json, occurred_at
		) VALUES ($1,$2,$3,$4,$5,$6)`,
		uuid.NewString(), pairID, version, result.EventName, payload, result.OccurredAt,
	)
	if err != nil {
		return fmt.Errorf("append persona relationship outbox: %w", err)
	}
	return nil
}

func clearedFollowDirections(
	command relmodel.Command,
	directions []relmodel.Direction,
) (sourceCleared bool, targetCleared bool) {
	for _, direction := range directions {
		switch {
		case direction.SourcePersonaID == command.SourcePersonaID &&
			direction.TargetPersonaID == command.TargetPersonaID:
			sourceCleared = true
		case direction.SourcePersonaID == command.TargetPersonaID &&
			direction.TargetPersonaID == command.SourcePersonaID:
			targetCleared = true
		}
	}
	return sourceCleared, targetCleared
}

func (s *PgPersonaRelationshipStore) ClaimPendingOutbox(
	ctx context.Context,
	owner string,
	lease time.Duration,
	limit int,
) ([]relmodel.OutboxEvent, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	owner = strings.TrimSpace(owner)
	if owner == "" {
		return nil, errors.New("persona relationship outbox claim owner is required")
	}
	if lease <= 0 {
		lease = time.Minute
	}
	leaseBefore := time.Now().UTC().Add(-lease)
	rows, err := s.pool.Query(ctx, `
		WITH candidates AS (
			SELECT candidate.event_id
			FROM persona_relationship_outbox AS candidate
			WHERE candidate.published_at IS NULL
				AND (candidate.claim_owner IS NULL OR candidate.claimed_at < $2)
				AND NOT EXISTS (
					SELECT 1
					FROM persona_relationship_outbox AS earlier
					WHERE earlier.aggregate_id = candidate.aggregate_id
						AND earlier.published_at IS NULL
						AND earlier.aggregate_version < candidate.aggregate_version
				)
			ORDER BY candidate.occurred_at, candidate.event_id
			LIMIT $3
			FOR UPDATE SKIP LOCKED
		)
		UPDATE persona_relationship_outbox AS outbox
		SET claim_owner = $1, claimed_at = NOW()
		FROM candidates
		WHERE outbox.event_id = candidates.event_id
		RETURNING outbox.event_id, outbox.event_name, outbox.payload_json`, owner, leaseBefore, limit)
	if err != nil {
		return nil, fmt.Errorf("claim pending persona relationship outbox: %w", err)
	}
	defer rows.Close()
	events := make([]relmodel.OutboxEvent, 0, limit)
	for rows.Next() {
		var (
			event   relmodel.OutboxEvent
			payload []byte
		)
		if err := rows.Scan(&event.EventID, &event.EventName, &payload); err != nil {
			return nil, fmt.Errorf("scan claimed persona relationship outbox: %w", err)
		}
		if err := json.Unmarshal(payload, &event.Payload); err != nil {
			return nil, fmt.Errorf("decode claimed persona relationship outbox payload: %w", err)
		}
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate claimed persona relationship outbox: %w", err)
	}
	return events, nil
}

func (s *PgPersonaRelationshipStore) MarkOutboxPublished(ctx context.Context, eventID, owner string) error {
	command, err := s.pool.Exec(ctx, `
		UPDATE persona_relationship_outbox
		SET published_at = NOW(), claim_owner = NULL, claimed_at = NULL
		WHERE event_id = $1 AND published_at IS NULL AND claim_owner = $2`, eventID, owner)
	if err != nil {
		return fmt.Errorf("mark persona relationship outbox published: %w", err)
	}
	if command.RowsAffected() != 1 {
		return fmt.Errorf("%w: event %q", relports.ErrOutboxClaimLost, eventID)
	}
	return nil
}

func (s *PgPersonaRelationshipStore) ReleaseOutboxClaim(ctx context.Context, eventID, owner string) error {
	_, err := s.pool.Exec(ctx, `
		UPDATE persona_relationship_outbox
		SET claim_owner = NULL, claimed_at = NULL
		WHERE event_id = $1 AND published_at IS NULL AND claim_owner = $2`, eventID, owner)
	if err != nil {
		return fmt.Errorf("release persona relationship outbox claim: %w", err)
	}
	return nil
}

func saveReceipt(
	ctx context.Context,
	tx pgx.Tx,
	command relmodel.Command,
	pairID string,
	version int64,
	result relmodel.MutationResult,
) error {
	if command.IdempotencyKey == "" {
		return nil
	}
	payload, err := json.Marshal(result)
	if err != nil {
		return fmt.Errorf("marshal persona relationship receipt: %w", err)
	}
	_, err = tx.Exec(ctx, `
		INSERT INTO persona_relationship_command_receipts (
			receipt_id, actor_persona_id, idempotency_key, operation, target_persona_id,
			pair_id, aggregate_version, response_json, created_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW())`,
		uuid.NewString(), command.SourcePersonaID, command.IdempotencyKey,
		string(command.Kind), command.TargetPersonaID, pairID, version, payload,
	)
	if err != nil {
		return fmt.Errorf("save persona relationship receipt: %w", err)
	}
	return nil
}

func (s *PgPersonaRelationshipStore) Get(
	ctx context.Context,
	viewerPersonaID, targetPersonaID string,
) (relmodel.RelationshipState, error) {
	pair, err := relmodel.NewPair(viewerPersonaID, targetPersonaID)
	if err != nil {
		return relmodel.RelationshipState{}, err
	}
	var version int64
	var updatedAt time.Time
	err = s.pool.QueryRow(ctx, `
		SELECT version, updated_at FROM persona_relationships WHERE pair_id = $1`, pair.ID,
	).Scan(&version, &updatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return relmodel.RelationshipState{}, nil
	}
	if err != nil {
		return relmodel.RelationshipState{}, fmt.Errorf("read persona relationship: %w", err)
	}
	directions, err := s.loadDirections(ctx, pair.ID)
	if err != nil {
		return relmodel.RelationshipState{}, err
	}
	return relationshipState(pair.ID, version, viewerPersonaID, targetPersonaID, directions, updatedAt), nil
}

func (s *PgPersonaRelationshipStore) loadDirections(ctx context.Context, pairID string) (map[string]relmodel.Direction, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT pair_id, source_persona_id, target_persona_id, following, blocked,
			follow_source, followed_at, blocked_at, updated_at
		FROM persona_relationship_directions WHERE pair_id = $1`, pairID)
	if err != nil {
		return nil, fmt.Errorf("read persona relationship directions: %w", err)
	}
	defer rows.Close()
	directions := make(map[string]relmodel.Direction, 2)
	for rows.Next() {
		direction, err := scanDirection(rows)
		if err != nil {
			return nil, err
		}
		directions[direction.SourcePersonaID] = direction
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate persona relationship directions: %w", err)
	}
	return directions, nil
}

func scanDirection(row pgx.Row) (relmodel.Direction, error) {
	var direction relmodel.Direction
	var followSource *string
	err := row.Scan(
		&direction.PairID,
		&direction.SourcePersonaID,
		&direction.TargetPersonaID,
		&direction.Following,
		&direction.Blocked,
		&followSource,
		&direction.FollowedAt,
		&direction.BlockedAt,
		&direction.UpdatedAt,
	)
	if err != nil {
		return relmodel.Direction{}, fmt.Errorf("scan persona relationship direction: %w", err)
	}
	if followSource != nil {
		direction.FollowSource = *followSource
	}
	return direction, nil
}

func (s *PgPersonaRelationshipStore) ListFollowing(ctx context.Context, sourcePersonaID, cursor string, limit int) ([]relmodel.Direction, string, error) {
	return s.listDirections(ctx, sourcePersonaID, cursor, limit, "source_persona_id", "following", "followed_at")
}

func (s *PgPersonaRelationshipStore) ListFollowers(ctx context.Context, targetPersonaID, cursor string, limit int) ([]relmodel.Direction, string, error) {
	return s.listDirections(ctx, targetPersonaID, cursor, limit, "target_persona_id", "following", "followed_at")
}

func (s *PgPersonaRelationshipStore) ListBlocked(
	ctx context.Context,
	sourcePersonaID, cursor string,
	limit int,
) ([]relports.BlockedListItem, string, error) {
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	args := []any{sourcePersonaID}
	where := "d.source_persona_id = $1 AND d.blocked = TRUE"
	if cursorTime, cursorPairID, ok := parseCursor(cursor); ok {
		args = append(args, cursorTime, cursorPairID)
		where += fmt.Sprintf(
			" AND (d.blocked_at, d.pair_id) < ($%d, $%d)",
			len(args)-1,
			len(args),
		)
	}
	args = append(args, limit+1)
	rows, err := s.pool.Query(ctx, fmt.Sprintf(`
		SELECT d.pair_id, d.target_persona_id,
			COALESCE(NULLIF(p.display_name, ''), d.target_persona_id),
			COALESCE(NULLIF(p.user_handle, ''), d.target_persona_id),
			COALESCE(p.avatar_url, ''),
			d.blocked_at
		FROM persona_relationship_directions d
		LEFT JOIN personas p ON p.sub_account_id = d.target_persona_id
		WHERE %s
		ORDER BY d.blocked_at DESC, d.pair_id DESC
		LIMIT $%d`, where, len(args)), args...)
	if err != nil {
		return nil, "", fmt.Errorf("list blocked persona views: %w", err)
	}
	defer rows.Close()

	type blockedRow struct {
		pairID string
		item   relports.BlockedListItem
	}
	items := make([]blockedRow, 0, limit+1)
	for rows.Next() {
		var row blockedRow
		if err := rows.Scan(
			&row.pairID,
			&row.item.TargetSubAccountID,
			&row.item.DisplayName,
			&row.item.UserHandle,
			&row.item.AvatarURL,
			&row.item.BlockedAt,
		); err != nil {
			return nil, "", fmt.Errorf("scan blocked persona view: %w", err)
		}
		row.item.BlockedAt = row.item.BlockedAt.UTC()
		items = append(items, row)
	}
	if err := rows.Err(); err != nil {
		return nil, "", fmt.Errorf("iterate blocked persona views: %w", err)
	}

	nextCursor := ""
	if len(items) > limit {
		items = items[:limit]
		last := items[len(items)-1]
		nextCursor = last.item.BlockedAt.Format(time.RFC3339Nano) + "|" + last.pairID
	}
	result := make([]relports.BlockedListItem, 0, len(items))
	for _, row := range items {
		result = append(result, row.item)
	}
	return result, nextCursor, nil
}

func (s *PgPersonaRelationshipStore) listDirections(
	ctx context.Context,
	personaID, cursor string,
	limit int,
	personaColumn, activeColumn, orderColumn string,
) ([]relmodel.Direction, string, error) {
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	args := []any{personaID}
	where := personaColumn + " = $1 AND " + activeColumn + " = TRUE"
	if cursorTime, cursorPairID, ok := parseCursor(cursor); ok {
		args = append(args, cursorTime, cursorPairID)
		where += fmt.Sprintf(" AND (%s, pair_id) < ($%d, $%d)", orderColumn, len(args)-1, len(args))
	}
	args = append(args, limit+1)
	query := fmt.Sprintf(`
		SELECT pair_id, source_persona_id, target_persona_id, following, blocked,
			follow_source, followed_at, blocked_at, updated_at
		FROM persona_relationship_directions
		WHERE %s
		ORDER BY %s DESC, pair_id DESC
		LIMIT $%d`, where, orderColumn, len(args))
	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, "", fmt.Errorf("list persona relationship directions: %w", err)
	}
	defer rows.Close()
	items := make([]relmodel.Direction, 0, limit)
	for rows.Next() {
		direction, err := scanDirection(rows)
		if err != nil {
			return nil, "", err
		}
		items = append(items, direction)
	}
	if err := rows.Err(); err != nil {
		return nil, "", fmt.Errorf("iterate persona relationship list: %w", err)
	}
	if len(items) <= limit {
		return items, "", nil
	}
	items = items[:limit]
	return items, directionCursor(items[len(items)-1], orderColumn), nil
}

func parseCursor(cursor string) (time.Time, string, bool) {
	parts := strings.SplitN(strings.TrimSpace(cursor), "|", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return time.Time{}, "", false
	}
	value, err := time.Parse(time.RFC3339Nano, parts[0])
	if err != nil {
		return time.Time{}, "", false
	}
	return value, parts[1], true
}

func directionCursor(direction relmodel.Direction, orderColumn string) string {
	value := direction.FollowedAt
	if orderColumn == "blocked_at" {
		value = direction.BlockedAt
	}
	if value == nil {
		return ""
	}
	return value.UTC().Format(time.RFC3339Nano) + "|" + direction.PairID
}

func nullableString(value string) *string {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	return &value
}
