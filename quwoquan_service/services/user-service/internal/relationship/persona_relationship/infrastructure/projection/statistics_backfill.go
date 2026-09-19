package projection

import (
	"context"

	"github.com/jackc/pgx/v5"
)

// BackfillAuthoritySnapshot rebuilds the live contribution ledger from one
// write-fenced PostgreSQL snapshot. The table locks are a rehearsal-safe
// fallback for migration; normal repair remains incremental and lock-light.
func (r *CounterReconciler) BackfillAuthoritySnapshot(ctx context.Context) (string, error) {
	tx, err := r.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return "", err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, `LOCK TABLE persona_relationships,persona_relationship_directions,persona_relationship_outbox IN SHARE MODE; LOCK TABLE persona_relationship_statistics_members,persona_relationship_statistics_buckets IN EXCLUSIVE MODE`); err != nil {
		return "", err
	}
	var watermark string
	if err := tx.QueryRow(ctx, `SELECT COALESCE(MAX(aggregate_version),0)::text FROM persona_relationship_outbox`).Scan(&watermark); err != nil {
		return "", err
	}
	if _, err := tx.Exec(ctx, `DELETE FROM persona_relationship_statistics_members; DELETE FROM persona_relationship_statistics_buckets WHERE generation='live'`); err != nil {
		return "", err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO persona_relationship_statistics_members(member_id,pair_id,persona_id,contribution_kind,bucket,last_applied_version,current_contribution,payload_digest,source_event_id,updated_at)
		SELECT md5(direction.pair_id||E'\\x1f'||direction.source_persona_id||E'\\x1f'||kind.name)||md5('member'||direction.pair_id||direction.source_persona_id||kind.name),direction.pair_id,
			CASE WHEN kind.name='following' THEN direction.source_persona_id ELSE direction.target_persona_id END,kind.name,
			MOD(ABS(hashtextextended(direction.pair_id||kind.name,0)),64)::integer,
			pair.version,CASE WHEN direction.following THEN 1 ELSE 0 END,md5(direction.pair_id||pair.version::text||direction.following::text)||md5('payload'||direction.pair_id||pair.version::text||direction.following::text),'backfill:'||$1,NOW()
		FROM persona_relationship_directions direction JOIN persona_relationships pair USING(pair_id)
		CROSS JOIN (VALUES('following'),('follower')) AS kind(name)`, watermark); err != nil {
		return "", err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO persona_relationship_statistics_buckets(generation,persona_id,contribution_kind,bucket,value,max_source_version,updated_at)
		SELECT 'live',persona_id,contribution_kind,bucket,SUM(current_contribution),MAX(last_applied_version),NOW()
		FROM persona_relationship_statistics_members GROUP BY persona_id,contribution_kind,bucket`); err != nil {
		return "", err
	}
	if err := tx.Commit(ctx); err != nil {
		return "", err
	}
	return watermark, nil
}
