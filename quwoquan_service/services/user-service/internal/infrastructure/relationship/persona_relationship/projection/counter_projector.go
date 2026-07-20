package projection

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	relevent "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/event"
	relmodel "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/model"
	reltelemetry "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/telemetry"
)

// ProfileCacheInvalidator keeps the derived profile count cache behind the
// committed PostgreSQL projection. A replay retries invalidation even when the
// counter event was already applied.
type ProfileCacheInvalidator interface {
	Del(ctx context.Context, userID string) error
}

// CounterProjector materializes owner-level follower/following counts from the
// canonical PersonaRelationship outbox. The outbox row is also the idempotency
// ledger, so a relay replay cannot apply a delta twice.
type CounterProjector struct {
	pool  *pgxpool.Pool
	cache ProfileCacheInvalidator
}

func NewCounterProjector(
	pool *pgxpool.Pool,
	cache ProfileCacheInvalidator,
) *CounterProjector {
	if pool == nil {
		panic("persona relationship counter projector pool is required")
	}
	return &CounterProjector{pool: pool, cache: cache}
}

func (p *CounterProjector) Apply(
	ctx context.Context,
	event relmodel.OutboxEvent,
) error {
	if p == nil || p.pool == nil {
		return errors.New("persona relationship counter projector is unavailable")
	}
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.Payload.PairID) == "" ||
		event.Payload.Version <= 0 {
		return errors.New("invalid persona relationship counter projection event")
	}

	ownerIDs, applied, err := p.project(ctx, event)
	if err != nil {
		return err
	}
	for _, ownerID := range ownerIDs {
		if p.cache == nil {
			continue
		}
		if err := p.cache.Del(ctx, ownerID); err != nil {
			return fmt.Errorf(
				"invalidate projected relationship counter cache for %s: %w",
				ownerID,
				err,
			)
		}
	}
	if applied {
		lag := time.Since(event.Payload.OccurredAt)
		if event.Payload.OccurredAt.IsZero() {
			lag = 0
		}
		reltelemetry.Collector().RecordCounterProjectionLag(lag)
	}
	return nil
}

func (p *CounterProjector) project(
	ctx context.Context,
	event relmodel.OutboxEvent,
) ([]string, bool, error) {
	tx, err := p.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return nil, false, fmt.Errorf("begin relationship counter projection: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()

	var (
		aggregateID      string
		aggregateVersion int64
		projectedAt      *time.Time
	)
	err = tx.QueryRow(ctx, `
		SELECT aggregate_id, aggregate_version, counter_projected_at
		FROM persona_relationship_outbox
		WHERE event_id = $1
		FOR UPDATE`,
		event.EventID,
	).Scan(&aggregateID, &aggregateVersion, &projectedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, false, fmt.Errorf(
			"persona relationship outbox event %q not found",
			event.EventID,
		)
	}
	if err != nil {
		return nil, false, fmt.Errorf("lock relationship counter event: %w", err)
	}
	if aggregateID != event.Payload.PairID ||
		aggregateVersion != event.Payload.Version {
		return nil, false, errors.New(
			"persona relationship counter event identity mismatch",
		)
	}

	sourceOwnerID, err := resolveOwnerID(
		ctx,
		tx,
		event.Payload.SourcePersonaID,
	)
	if err != nil {
		return nil, false, err
	}
	targetOwnerID, err := resolveOwnerID(
		ctx,
		tx,
		event.Payload.TargetPersonaID,
	)
	if err != nil {
		return nil, false, err
	}
	ownerIDs := uniqueOwnerIDs(sourceOwnerID, targetOwnerID)

	if projectedAt == nil {
		deltas := counterDeltas(event, sourceOwnerID, targetOwnerID)
		for ownerID, delta := range deltas {
			if err := applyCounterDelta(ctx, tx, ownerID, delta); err != nil {
				return nil, false, err
			}
		}
		if _, err := tx.Exec(ctx, `
			UPDATE persona_relationship_outbox
			SET counter_projected_at = NOW()
			WHERE event_id = $1`,
			event.EventID,
		); err != nil {
			return nil, false, fmt.Errorf(
				"mark relationship counters projected: %w",
				err,
			)
		}
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, false, fmt.Errorf("commit relationship counter projection: %w", err)
	}
	committed = true
	return ownerIDs, projectedAt == nil, nil
}

type counterDelta struct {
	followers int64
	following int64
}

func counterDeltas(
	event relmodel.OutboxEvent,
	sourceOwnerID string,
	targetOwnerID string,
) map[string]counterDelta {
	deltas := map[string]counterDelta{}
	applyFollowDelta := func(sourceID, targetID string, delta int64) {
		source := deltas[sourceID]
		source.following += delta
		deltas[sourceID] = source
		target := deltas[targetID]
		target.followers += delta
		deltas[targetID] = target
	}

	switch event.EventName {
	case relevent.PersonaFollowStateChanged:
		delta := int64(-1)
		if event.Payload.Following {
			delta = 1
		}
		applyFollowDelta(sourceOwnerID, targetOwnerID, delta)
	case relevent.PersonaBlocked:
		if event.Payload.SourceFollowCleared {
			applyFollowDelta(sourceOwnerID, targetOwnerID, -1)
		}
		if event.Payload.TargetFollowCleared {
			applyFollowDelta(targetOwnerID, sourceOwnerID, -1)
		}
	}
	return deltas
}

func resolveOwnerID(
	ctx context.Context,
	tx pgx.Tx,
	personaID string,
) (string, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return "", errors.New("persona relationship counter owner is required")
	}
	var ownerID string
	err := tx.QueryRow(ctx, `
		SELECT owner_id
		FROM (
			SELECT user_id AS owner_id, 0 AS priority
			FROM personas
			WHERE sub_account_id = $1
			UNION ALL
			SELECT user_id AS owner_id, 1 AS priority
			FROM user_profiles
			WHERE user_id = $1
		) AS candidates
		ORDER BY priority
		LIMIT 1`,
		personaID,
	).Scan(&ownerID)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", fmt.Errorf(
			"owner profile for persona %q not found",
			personaID,
		)
	}
	if err != nil {
		return "", fmt.Errorf(
			"resolve owner profile for persona %q: %w",
			personaID,
			err,
		)
	}
	return ownerID, nil
}

func applyCounterDelta(
	ctx context.Context,
	tx pgx.Tx,
	ownerID string,
	delta counterDelta,
) error {
	command, err := tx.Exec(ctx, `
		UPDATE user_profiles
		SET follower_count = GREATEST(0, follower_count + $2),
			following_count = GREATEST(0, following_count + $3),
			updated_at = NOW()
		WHERE user_id = $1`,
		ownerID,
		delta.followers,
		delta.following,
	)
	if err != nil {
		return fmt.Errorf(
			"apply relationship counter delta for %s: %w",
			ownerID,
			err,
		)
	}
	if command.RowsAffected() != 1 {
		return fmt.Errorf("owner profile %q not found during counter projection", ownerID)
	}
	return nil
}

func uniqueOwnerIDs(values ...string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}
