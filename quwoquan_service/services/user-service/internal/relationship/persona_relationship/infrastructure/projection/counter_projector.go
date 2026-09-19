package projection

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	relevent "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/event"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	reltelemetry "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/telemetry"
)

const DefaultRelationshipStatisticsBuckets = 64

// ProfileCacheInvalidator keeps any owner-side compatibility cache behind the
// persona-owned statistics generation. It is optional and never participates
// in the contribution transaction.
type ProfileCacheInvalidator interface {
	Del(ctx context.Context, userID string) error
}

type relationshipContribution struct {
	PersonaID string
	Kind      string
	Value     int64
}

// CounterProjector applies complete relationship after-state facts to a
// persona-owned contribution ledger. Replays and old versions are no-ops;
// equal-version/different-payload is rejected. No profile row or COUNT query is
// touched by this event path.
type CounterProjector struct {
	pool        *pgxpool.Pool
	cache       ProfileCacheInvalidator
	bucketCount int
}

func NewCounterProjector(pool *pgxpool.Pool, cache ProfileCacheInvalidator) *CounterProjector {
	if pool == nil {
		panic("persona relationship counter projector pool is required")
	}
	return &CounterProjector{pool: pool, cache: cache, bucketCount: DefaultRelationshipStatisticsBuckets}
}

func (p *CounterProjector) Apply(ctx context.Context, event relmodel.OutboxEvent) error {
	if p == nil || p.pool == nil {
		return errors.New("persona relationship counter projector is unavailable")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.Payload.PairID) == "" || event.Payload.Version <= 0 {
		return errors.New("invalid persona relationship counter projection event")
	}
	personaIDs, applied, err := p.project(ctx, event)
	if err != nil {
		return err
	}
	if applied {
		lag := time.Since(event.Payload.OccurredAt)
		if event.Payload.OccurredAt.IsZero() {
			lag = 0
		}
		reltelemetry.Collector().RecordCounterProjectionLag(lag)
	}
	// Compatibility invalidation is deliberately outside the ledger
	// transaction. A replay retries it without replaying a contribution.
	if p.cache != nil {
		for _, personaID := range personaIDs {
			if err := p.cache.Del(ctx, personaID); err != nil {
				return fmt.Errorf("invalidate relationship statistics cache for %s: %w", personaID, err)
			}
		}
	}
	return nil
}

func (p *CounterProjector) project(ctx context.Context, event relmodel.OutboxEvent) ([]string, bool, error) {
	contributions, err := relationshipContributions(event)
	if err != nil {
		return nil, false, err
	}
	digest, err := relationshipEventDigest(event)
	if err != nil {
		return nil, false, err
	}
	tx, err := p.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return nil, false, fmt.Errorf("begin relationship contribution projection: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()

	var storedDigest string
	err = tx.QueryRow(ctx, `
		SELECT payload_digest
		FROM persona_relationship_statistics_inbox
		WHERE event_id = $1
		FOR UPDATE`, event.EventID).Scan(&storedDigest)
	if err == nil {
		if storedDigest != digest {
			return nil, false, errors.New("persona relationship statistics event digest mismatch")
		}
		if err := tx.Commit(ctx); err != nil {
			return nil, false, fmt.Errorf("commit relationship contribution replay: %w", err)
		}
		committed = true
		return relationshipPersonaIDs(contributions), false, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return nil, false, fmt.Errorf("read relationship statistics inbox: %w", err)
	}

	for _, contribution := range contributions {
		if err := applyRelationshipContribution(ctx, tx, event, contribution, p.bucketCount, digest); err != nil {
			return nil, false, err
		}
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO persona_relationship_statistics_inbox (
			event_id, pair_id, aggregate_version, payload_digest, applied_at
		) VALUES ($1,$2,$3,$4,NOW())`,
		event.EventID, event.Payload.PairID, event.Payload.Version, digest,
	); err != nil {
		return nil, false, fmt.Errorf("record relationship statistics inbox: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, false, fmt.Errorf("commit relationship contribution projection: %w", err)
	}
	committed = true
	return relationshipPersonaIDs(contributions), true, nil
}

func relationshipContributions(event relmodel.OutboxEvent) ([]relationshipContribution, error) {
	payload := event.Payload
	if strings.TrimSpace(payload.SourcePersonaID) == "" || strings.TrimSpace(payload.TargetPersonaID) == "" || payload.SourcePersonaID == payload.TargetPersonaID {
		return nil, errors.New("relationship contribution endpoints are invalid")
	}
	sourceFollowing := int64(0)
	if payload.Following {
		sourceFollowing = 1
	}
	switch event.EventName {
	case relevent.PersonaFollowStateChanged:
		return []relationshipContribution{
			{PersonaID: payload.SourcePersonaID, Kind: "following", Value: sourceFollowing},
			{PersonaID: payload.TargetPersonaID, Kind: "follower", Value: sourceFollowing},
		}, nil
	case relevent.PersonaBlocked:
		// Block clears both directions in the authoritative transaction. Apply
		// both complete after-states so a replay or partial prior projection
		// cannot leave the opposite contribution alive.
		return []relationshipContribution{
			{PersonaID: payload.SourcePersonaID, Kind: "following", Value: 0},
			{PersonaID: payload.TargetPersonaID, Kind: "follower", Value: 0},
			{PersonaID: payload.TargetPersonaID, Kind: "following", Value: 0},
			{PersonaID: payload.SourcePersonaID, Kind: "follower", Value: 0},
		}, nil
	case relevent.PersonaUnblocked:
		// Unblock never restores historical follows and therefore has no
		// statistics member transition.
		return nil, nil
	default:
		return nil, fmt.Errorf("unsupported relationship statistics event %q", event.EventName)
	}
}

func applyRelationshipContribution(ctx context.Context, tx pgx.Tx, event relmodel.OutboxEvent, contribution relationshipContribution, bucketCount int, digest string) error {
	memberID := event.Payload.PairID + ":" + contribution.Kind + ":" + contribution.PersonaID
	var storedVersion, oldValue int64
	var storedDigest string
	err := tx.QueryRow(ctx, `
		SELECT last_applied_version, current_contribution, payload_digest
		FROM persona_relationship_statistics_members
		WHERE member_id = $1
		FOR UPDATE`, memberID).Scan(&storedVersion, &oldValue, &storedDigest)
	if err == nil {
		if storedVersion > event.Payload.Version {
			return nil
		}
		if storedVersion == event.Payload.Version {
			if storedDigest != digest {
				return errors.New("persona relationship statistics member version digest mismatch")
			}
			return nil
		}
	} else if !errors.Is(err, pgx.ErrNoRows) {
		return fmt.Errorf("lock relationship statistics member: %w", err)
	}
	delta := contribution.Value - oldValue
	bucket := stableBucket(memberID, bucketCount)
	if _, err := tx.Exec(ctx, `
		INSERT INTO persona_relationship_statistics_members (
			member_id, pair_id, persona_id, contribution_kind, bucket,
			last_applied_version, current_contribution, payload_digest,
			source_event_id, updated_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
		ON CONFLICT (member_id) DO UPDATE SET
			last_applied_version = EXCLUDED.last_applied_version,
			current_contribution = EXCLUDED.current_contribution,
			payload_digest = EXCLUDED.payload_digest,
			source_event_id = EXCLUDED.source_event_id,
			updated_at = EXCLUDED.updated_at`,
		memberID, event.Payload.PairID, contribution.PersonaID, contribution.Kind,
		bucket, event.Payload.Version, contribution.Value, digest, event.EventID,
		event.Payload.OccurredAt,
	); err != nil {
		return fmt.Errorf("upsert relationship statistics member: %w", err)
	}
	if delta == 0 {
		return nil
	}
	var command pgconn.CommandTag
	if delta > 0 {
		command, err = tx.Exec(ctx, `
			INSERT INTO persona_relationship_statistics_buckets (
				generation, persona_id, contribution_kind, bucket, value,
				max_source_version, updated_at
			) VALUES ('live', $1,$2,$3,$4,$5,NOW())
			ON CONFLICT (generation, persona_id, contribution_kind, bucket) DO UPDATE SET
				value = persona_relationship_statistics_buckets.value + EXCLUDED.value,
				max_source_version = GREATEST(
					persona_relationship_statistics_buckets.max_source_version,
					EXCLUDED.max_source_version
				),
				updated_at = NOW()`,
			contribution.PersonaID, contribution.Kind, bucket, delta, event.Payload.Version,
		)
	} else {
		command, err = tx.Exec(ctx, `
			UPDATE persona_relationship_statistics_buckets
			SET value = value + $4,
				max_source_version = GREATEST(max_source_version, $5),
				updated_at = NOW()
			WHERE generation='live' AND persona_id=$1
				AND contribution_kind=$2 AND bucket=$3
				AND value + $4 >= 0`,
			contribution.PersonaID, contribution.Kind, bucket, delta, event.Payload.Version,
		)
	}
	if err != nil {
		return fmt.Errorf("update relationship statistics bucket: %w", err)
	}
	if command.RowsAffected() != 1 {
		return errors.New("relationship statistics contribution would make bucket negative")
	}
	return nil
}

func relationshipEventDigest(event relmodel.OutboxEvent) (string, error) {
	payload, err := json.Marshal(struct {
		Name    string                 `json:"name"`
		Payload relmodel.OutboxPayload `json:"payload"`
	}{Name: event.EventName, Payload: event.Payload})
	if err != nil {
		return "", fmt.Errorf("encode relationship statistics digest: %w", err)
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func relationshipPersonaIDs(contributions []relationshipContribution) []string {
	seen := make(map[string]struct{})
	for _, contribution := range contributions {
		seen[contribution.PersonaID] = struct{}{}
	}
	result := make([]string, 0, len(seen))
	for personaID := range seen {
		result = append(result, personaID)
	}
	sort.Strings(result)
	return result
}

func stableBucket(identity string, count int) int {
	if count <= 0 {
		count = DefaultRelationshipStatisticsBuckets
	}
	sum := sha256.Sum256([]byte(identity))
	value := uint64(0)
	for _, part := range sum[:8] {
		value = value<<8 | uint64(part)
	}
	return int(value % uint64(count))
}
