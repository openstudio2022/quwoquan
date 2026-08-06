package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"

	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

func (store *PersonaCommandPostgresStore) ClaimPendingOutbox(
	ctx context.Context,
	now time.Time,
	lease time.Duration,
) (personaports.PersonaOutboxEvent, bool, error) {
	now = now.UTC()
	if store == nil || store.pool == nil || now.IsZero() || lease <= 0 {
		return personaports.PersonaOutboxEvent{}, false, errors.New("Persona outbox claim is invalid")
	}
	var event personaports.PersonaOutboxEvent
	err := store.pool.QueryRow(ctx, `
WITH candidate AS (
  SELECT outbox.event_id, persona.user_id
  FROM personas_outbox AS outbox
  JOIN personas AS persona ON persona.persona_id=outbox.aggregate_id
  WHERE outbox.published_at IS NULL
    AND outbox.next_attempt_at <= $1
  ORDER BY outbox.occurred_at, outbox.event_id
  FOR UPDATE OF outbox SKIP LOCKED
  LIMIT 1
)
UPDATE personas_outbox AS outbox
SET next_attempt_at=$2,
    retry_count=outbox.retry_count+1,
    last_error=''
FROM candidate
WHERE outbox.event_id=candidate.event_id
RETURNING outbox.event_id, candidate.user_id, outbox.aggregate_id, outbox.aggregate_version,
	          outbox.event_type, outbox.payload_json, outbox.occurred_at,
	          outbox.retry_count, outbox.next_attempt_at`, now, now.Add(lease)).Scan(
		&event.EventID,
		&event.OwnerID,
		&event.AggregateID,
		&event.AggregateVersion,
		&event.EventType,
		&event.PayloadJSON,
		&event.OccurredAt,
		&event.AttemptCount,
		&event.ClaimUntil,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return personaports.PersonaOutboxEvent{}, false, nil
	}
	if err != nil {
		return personaports.PersonaOutboxEvent{}, false, fmt.Errorf("claim Persona outbox: %w", err)
	}
	return event, true, nil
}

func (store *PersonaCommandPostgresStore) MarkPublished(
	ctx context.Context,
	eventID string,
	claimUntil time.Time,
	publishedAt time.Time,
) error {
	result, err := store.pool.Exec(ctx, `
UPDATE personas_outbox
SET published_at=$2, next_attempt_at=$2, last_error=''
WHERE event_id=$1 AND published_at IS NULL AND next_attempt_at=$3`,
		strings.TrimSpace(eventID), publishedAt.UTC(), claimUntil.UTC())
	if err != nil {
		return fmt.Errorf("mark Persona outbox published: %w", err)
	}
	if result.RowsAffected() != 1 {
		return personaports.ErrPersonaOutboxCheckpointLost
	}
	return nil
}

func (store *PersonaCommandPostgresStore) SchedulePublicationRetry(
	ctx context.Context,
	eventID string,
	claimUntil time.Time,
	nextAttemptAt time.Time,
	failureDigest string,
) error {
	failureDigest = strings.TrimSpace(failureDigest)
	if len(failureDigest) > 96 {
		failureDigest = failureDigest[:96]
	}
	result, err := store.pool.Exec(ctx, `
UPDATE personas_outbox
SET next_attempt_at=$2, last_error=$3
WHERE event_id=$1 AND published_at IS NULL AND next_attempt_at=$4`,
		strings.TrimSpace(eventID), nextAttemptAt.UTC(), failureDigest, claimUntil.UTC())
	if err != nil {
		return fmt.Errorf("schedule Persona outbox retry: %w", err)
	}
	if result.RowsAffected() != 1 {
		return personaports.ErrPersonaOutboxCheckpointLost
	}
	return nil
}

var _ personaports.PersonaPublicationOutbox = (*PersonaCommandPostgresStore)(nil)
