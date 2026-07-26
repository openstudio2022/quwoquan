package persistence

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

func erasePersonaPrivateState(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	personaIDs []string,
	closedAt time.Time,
) error {
	if err := reconcileCounterpartRelationshipCounts(
		ctx,
		tx,
		personaIDs,
		closedAt,
	); err != nil {
		return err
	}
	if err := removeClosedPersonasFromContactMatches(
		ctx,
		tx,
		accountID,
		personaIDs,
	); err != nil {
		return err
	}
	if err := anonymizePersonaRelationships(
		ctx,
		tx,
		personaIDs,
		closedAt,
	); err != nil {
		return err
	}
	if err := eraseGreetingRequests(
		ctx,
		tx,
		personaIDs,
		closedAt,
	); err != nil {
		return err
	}
	if err := eraseSubjectFollows(
		ctx,
		tx,
		personaIDs,
		closedAt,
	); err != nil {
		return err
	}
	if err := eraseProfileUpdateProposals(
		ctx,
		tx,
		personaIDs,
		closedAt,
	); err != nil {
		return err
	}
	if err := redactPersonaCommandHistory(
		ctx,
		tx,
		personaIDs,
		closedAt,
	); err != nil {
		return err
	}
	return nil
}

func reconcileCounterpartRelationshipCounts(
	ctx context.Context,
	tx pgx.Tx,
	personaIDs []string,
	closedAt time.Time,
) error {
	if err := execCloseStep(
		ctx,
		tx,
		"decrement counterpart follower counters",
		`WITH impacts AS (
		   SELECT target_persona.user_id, COUNT(*)::integer AS delta
		     FROM persona_relationship_directions AS direction
		     JOIN personas AS target_persona
		       ON target_persona.sub_account_id=direction.target_persona_id
		    WHERE direction.following=true
		      AND direction.source_persona_id=ANY($1::text[])
		    GROUP BY target_persona.user_id
		 )
		 UPDATE user_profiles AS profile
		    SET follower_count=GREATEST(0, profile.follower_count-impacts.delta),
		        updated_at=CASE
		          WHEN profile.account_state='closed' THEN profile.updated_at
		          ELSE $2
		        END
		   FROM impacts
		  WHERE profile.user_id=impacts.user_id`,
		personaIDs,
		closedAt,
	); err != nil {
		return err
	}
	return execCloseStep(
		ctx,
		tx,
		"decrement counterpart following counters",
		`WITH impacts AS (
		   SELECT source_persona.user_id, COUNT(*)::integer AS delta
		     FROM persona_relationship_directions AS direction
		     JOIN personas AS source_persona
		       ON source_persona.sub_account_id=direction.source_persona_id
		    WHERE direction.following=true
		      AND direction.target_persona_id=ANY($1::text[])
		    GROUP BY source_persona.user_id
		 )
		 UPDATE user_profiles AS profile
		    SET following_count=GREATEST(0, profile.following_count-impacts.delta),
		        updated_at=CASE
		          WHEN profile.account_state='closed' THEN profile.updated_at
		          ELSE $2
		        END
		   FROM impacts
		  WHERE profile.user_id=impacts.user_id`,
		personaIDs,
		closedAt,
	)
}

func removeClosedPersonasFromContactMatches(
	ctx context.Context,
	tx pgx.Tx,
	accountID string,
	personaIDs []string,
) error {
	return execCloseStep(
		ctx,
		tx,
		"remove closed personas from contact discovery matches",
		`WITH cleaned AS (
		   SELECT record.id,
		          ARRAY(
		            SELECT matched_id
		              FROM unnest(COALESCE(record.matched_sub_account_ids, ARRAY[]::text[]))
		                   AS matched_id
		             WHERE NOT (matched_id=ANY($1::text[]))
		          ) AS remaining
		     FROM contact_discovery_records AS record
		    WHERE record.owner_account_id<>$2
		      AND COALESCE(record.matched_sub_account_ids, ARRAY[]::text[])
		          && $1::text[]
		 )
		 UPDATE contact_discovery_records AS record
		    SET matched_sub_account_ids=cleaned.remaining,
		        match_count=cardinality(cleaned.remaining)
		   FROM cleaned
		  WHERE record.id=cleaned.id`,
		personaIDs,
		accountID,
	)
}

func anonymizePersonaRelationships(
	ctx context.Context,
	tx pgx.Tx,
	personaIDs []string,
	closedAt time.Time,
) error {
	pairPredicate := `
SELECT pair_id
FROM persona_relationships
WHERE lower_persona_id=ANY($1::text[])
   OR upper_persona_id=ANY($1::text[])`
	if _, err := tx.Exec(ctx, `
UPDATE persona_relationship_outbox
SET payload_json='{"redacted":true}'::jsonb,
    published_at=COALESCE(published_at,$2),
    claim_owner=NULL,
    claimed_at=NULL,
    counter_projected_at=COALESCE(counter_projected_at,$2)
WHERE aggregate_id IN (`+pairPredicate+`)`, personaIDs, closedAt); err != nil {
		return fmt.Errorf("redact relationship outbox on account close: %w", err)
	}
	if _, err := tx.Exec(ctx, `
DELETE FROM persona_relationship_command_receipts
WHERE pair_id IN (`+pairPredicate+`)`, personaIDs); err != nil {
		return fmt.Errorf("delete relationship receipts on account close: %w", err)
	}
	if _, err := tx.Exec(ctx, `
DELETE FROM persona_relationship_directions
WHERE pair_id IN (`+pairPredicate+`)`, personaIDs); err != nil {
		return fmt.Errorf("delete relationship directions on account close: %w", err)
	}
	if _, err := tx.Exec(ctx, `
UPDATE persona_relationships
SET lower_persona_id='closed-l:' || pair_id,
    upper_persona_id='closed-u:' || pair_id,
    version=version+1,
    updated_at=$2
WHERE pair_id IN (`+pairPredicate+`)`, personaIDs, closedAt); err != nil {
		return fmt.Errorf("tombstone relationship aggregate on account close: %w", err)
	}
	return nil
}

func eraseGreetingRequests(
	ctx context.Context,
	tx pgx.Tx,
	personaIDs []string,
	closedAt time.Time,
) error {
	requestPredicate := `
SELECT id
FROM greeting_requests
WHERE requester_sub_account_id=ANY($1::text[])
   OR target_sub_account_id=ANY($1::text[])`
	if _, err := tx.Exec(ctx, `
UPDATE greeting_request_outbox
SET payload_json='{"redacted":true}'::jsonb,
    published_at=COALESCE(published_at,$2),
    claim_owner=NULL,
    claimed_at=NULL
WHERE aggregate_id IN (`+requestPredicate+`)`, personaIDs, closedAt); err != nil {
		return fmt.Errorf("redact greeting outbox on account close: %w", err)
	}
	if _, err := tx.Exec(ctx, `
DELETE FROM greeting_request_command_receipts
WHERE actor_sub_account_id=ANY($1::text[])
   OR request_id IN (`+requestPredicate+`)`, personaIDs); err != nil {
		return fmt.Errorf("delete greeting receipts on account close: %w", err)
	}
	if _, err := tx.Exec(ctx, `
DELETE FROM greeting_requests
WHERE id IN (`+requestPredicate+`)`, personaIDs); err != nil {
		return fmt.Errorf("delete greeting requests on account close: %w", err)
	}
	return nil
}

func eraseSubjectFollows(
	ctx context.Context,
	tx pgx.Tx,
	personaIDs []string,
	closedAt time.Time,
) error {
	followPredicate := `
SELECT id
FROM subject_follows
WHERE persona_id=ANY($1::text[])`
	if _, err := tx.Exec(ctx, `
UPDATE subject_follow_outbox
SET payload_json='{"redacted":true}'::jsonb,
    published_at=COALESCE(published_at,$2),
    claim_owner=NULL,
    claimed_at=NULL
WHERE aggregate_id IN (`+followPredicate+`)`, personaIDs, closedAt); err != nil {
		return fmt.Errorf("redact subject follow outbox on account close: %w", err)
	}
	if _, err := tx.Exec(ctx, `
DELETE FROM subject_follow_command_receipts
WHERE persona_id=ANY($1::text[])
   OR aggregate_id IN (`+followPredicate+`)`, personaIDs); err != nil {
		return fmt.Errorf("delete subject follow receipts on account close: %w", err)
	}
	if _, err := tx.Exec(ctx, `
DELETE FROM subject_follows
WHERE id IN (`+followPredicate+`)`, personaIDs); err != nil {
		return fmt.Errorf("delete subject follows on account close: %w", err)
	}
	return nil
}

func eraseProfileUpdateProposals(
	ctx context.Context,
	tx pgx.Tx,
	personaIDs []string,
	closedAt time.Time,
) error {
	proposalPredicate := `
SELECT id
FROM profile_update_proposals
WHERE persona_id=ANY($1::text[])`
	if _, err := tx.Exec(ctx, `
UPDATE profile_update_proposals_outbox
SET payload_json='{"redacted":true}'::jsonb,
    published_at=COALESCE(published_at,$2),
    next_attempt_at=$2,
    last_error=''
WHERE aggregate_id IN (`+proposalPredicate+`)`, personaIDs, closedAt); err != nil {
		return fmt.Errorf("redact profile proposal outbox on account close: %w", err)
	}
	if _, err := tx.Exec(ctx, `
DELETE FROM profile_update_proposals_command_receipts
WHERE proposal_id IN (`+proposalPredicate+`)`, personaIDs); err != nil {
		return fmt.Errorf("delete profile proposal receipts on account close: %w", err)
	}
	if _, err := tx.Exec(ctx, `
DELETE FROM profile_update_proposals
WHERE id IN (`+proposalPredicate+`)`, personaIDs); err != nil {
		return fmt.Errorf("delete profile proposals on account close: %w", err)
	}
	return nil
}

func redactPersonaCommandHistory(
	ctx context.Context,
	tx pgx.Tx,
	personaIDs []string,
	closedAt time.Time,
) error {
	if _, err := tx.Exec(ctx, `
UPDATE personas_outbox
SET payload_json=jsonb_build_object(
      'personaId', aggregate_id,
      'redacted', true
    ),
    published_at=COALESCE(published_at,$2),
    next_attempt_at=$2,
    last_error=''
WHERE aggregate_id=ANY($1::text[])`, personaIDs, closedAt); err != nil {
		return fmt.Errorf("redact persona outbox on account close: %w", err)
	}
	if _, err := tx.Exec(ctx, `
DELETE FROM personas_command_receipts
WHERE aggregate_id=ANY($1::text[])`, personaIDs); err != nil {
		return fmt.Errorf("delete persona command receipts on account close: %w", err)
	}
	return nil
}
