// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-001
package api_integration

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	accountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestCloseAccountThenCreatePersonaWithReusedIdempotencyKey(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		const (
			firstOwnerID     = "orphan-outbox-owner-before-close"
			firstPrimaryID   = "orphan-outbox-primary-before-close"
			firstPersonaID   = "orphan-outbox-persona-before-close"
			secondOwnerID    = "orphan-outbox-owner-after-close"
			secondPrimaryID  = "orphan-outbox-primary-after-close"
			secondPersonaID  = "orphan-outbox-persona-after-close"
			reusedCommandKey = "persona-orphan-outbox-reused-key"
		)
		meta := personaports.PersonaCommandMeta{
			IdempotencyKey: reusedCommandKey,
			CommandDigest:  "same-create-persona-command",
		}
		if err := usersupport.SeedAccountPersona(
			ctx,
			pool,
			firstOwnerID,
			firstPrimaryID,
		); err != nil {
			t.Fatal(err)
		}
		personaStore, err := personapersistence.NewPersonaCommandPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		firstResult, err := personaStore.CommitCreate(
			ctx,
			&usermodel.Persona{
				PersonaID:                firstPersonaID,
				UserID:                   firstOwnerID,
				DisplayName:              "注销前分身",
				IdentityTags:             []string{},
				IsolationLevel:           "open",
				Status:                   "active",
				InheritsProfileFromOwner: true,
				OverriddenProfileFields:  []string{},
			},
			meta,
		)
		if err != nil || firstResult.PersonaID != firstPersonaID {
			t.Fatalf("create Persona before close: result=%+v err=%v", firstResult, err)
		}

		var (
			orphanEventID          string
			orphanAggregateVersion int64
			orphanEventType        string
			orphanPayload          []byte
			orphanOccurredAt       time.Time
		)
		if err := pool.QueryRow(ctx, `
SELECT event_id, aggregate_version, event_type, payload_json, occurred_at
FROM personas_outbox
WHERE aggregate_id=$1 AND event_type='PersonaCreated'`,
			firstPersonaID,
		).Scan(
			&orphanEventID,
			&orphanAggregateVersion,
			&orphanEventType,
			&orphanPayload,
			&orphanOccurredAt,
		); err != nil {
			t.Fatalf("load first Persona packet: %v", err)
		}

		// This trigger turns transaction order into behavior: if CloseAccount
		// deletes the receipt before the outbox, the close transaction fails.
		if _, err := pool.Exec(ctx, `
CREATE TABLE persona_outbox_delete_order_guard (
  event_id text PRIMARY KEY
);
CREATE FUNCTION require_persona_receipt_before_outbox_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF EXISTS (
       SELECT 1
       FROM persona_outbox_delete_order_guard
       WHERE event_id=OLD.event_id
     )
     AND NOT EXISTS (
       SELECT 1
       FROM personas_command_receipts
       WHERE aggregate_id=OLD.aggregate_id
     ) THEN
    RAISE EXCEPTION 'persona receipt deleted before outbox';
  END IF;
  RETURN OLD;
END;
$$;
CREATE TRIGGER require_persona_receipt_before_outbox_delete_trigger
BEFORE DELETE ON personas_outbox
FOR EACH ROW EXECUTE FUNCTION require_persona_receipt_before_outbox_delete();`); err != nil {
			t.Fatalf("install Persona close-order guard: %v", err)
		}
		if _, err := pool.Exec(ctx,
			`INSERT INTO persona_outbox_delete_order_guard(event_id) VALUES ($1)`,
			orphanEventID,
		); err != nil {
			t.Fatalf("arm Persona close-order guard: %v", err)
		}
		t.Cleanup(func() {
			if _, err := pool.Exec(context.Background(), `
DROP TRIGGER IF EXISTS require_persona_receipt_before_outbox_delete_trigger
  ON personas_outbox;
DROP FUNCTION IF EXISTS require_persona_receipt_before_outbox_delete();
DROP TABLE IF EXISTS persona_outbox_delete_order_guard;`); err != nil {
				t.Errorf("remove Persona close-order guard: %v", err)
			}
		})

		closeStore, err := accountpersistence.NewCloseStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := closeStore.CommitClose(ctx, firstOwnerID, time.Now().UTC()); err != nil {
			t.Fatalf("CloseAccount ordered Persona packet cleanup: %v", err)
		}
		var remainingPackets int
		if err := pool.QueryRow(ctx, `
SELECT
  (SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=$1)
  + (SELECT COUNT(*) FROM personas_command_receipts WHERE aggregate_id=$1)`,
			firstPersonaID,
		).Scan(&remainingPackets); err != nil {
			t.Fatalf("count Persona packets after close: %v", err)
		}
		if remainingPackets != 0 {
			t.Fatalf("CloseAccount left %d Persona packet rows", remainingPackets)
		}

		if _, err := pool.Exec(ctx, `
DROP TRIGGER require_persona_receipt_before_outbox_delete_trigger
  ON personas_outbox`); err != nil {
			t.Fatalf("disarm Persona close-order guard: %v", err)
		}
		if _, err := pool.Exec(ctx, `
INSERT INTO personas_outbox(
  event_id,
  aggregate_id,
  aggregate_version,
  event_type,
  payload_json,
  occurred_at
) VALUES ($1,$2,$3,$4,$5,$6)`,
			orphanEventID,
			firstPersonaID,
			orphanAggregateVersion,
			orphanEventType,
			orphanPayload,
			orphanOccurredAt,
		); err != nil {
			t.Fatalf("seed legacy orphan Persona outbox packet: %v", err)
		}

		if err := usersupport.SeedAccountPersona(
			ctx,
			pool,
			secondOwnerID,
			secondPrimaryID,
		); err != nil {
			t.Fatal(err)
		}
		secondResult, err := personaStore.CommitCreate(
			ctx,
			&usermodel.Persona{
				PersonaID:                secondPersonaID,
				UserID:                   secondOwnerID,
				DisplayName:              "注销后分身",
				IdentityTags:             []string{},
				IsolationLevel:           "open",
				Status:                   "active",
				InheritsProfileFromOwner: true,
				OverriddenProfileFields:  []string{},
			},
			meta,
		)
		if err != nil {
			t.Fatalf(
				"CreatePersona must self-heal a legacy orphan instead of returning personas_outbox_pkey: %v",
				err,
			)
		}
		if secondResult.PersonaID != secondPersonaID {
			t.Fatalf("CreatePersona after close result=%+v", secondResult)
		}

		var (
			eventAggregateID    string
			outboxPacketCount   int
			commandReceiptCount int
		)
		if err := pool.QueryRow(ctx, `
SELECT aggregate_id
FROM personas_outbox
WHERE event_id=$1`,
			orphanEventID,
		).Scan(&eventAggregateID); err != nil {
			t.Fatalf("read self-healed Persona outbox: %v", err)
		}
		if err := pool.QueryRow(ctx, `
SELECT
  (SELECT COUNT(*) FROM personas_outbox WHERE event_id=$1),
  (SELECT COUNT(*) FROM personas_command_receipts
    WHERE idempotency_key=$2 AND aggregate_id=$3)`,
			orphanEventID,
			reusedCommandKey,
			secondPersonaID,
		).Scan(&outboxPacketCount, &commandReceiptCount); err != nil {
			t.Fatalf("count self-healed Persona packet: %v", err)
		}
		if eventAggregateID != secondPersonaID ||
			outboxPacketCount != 1 ||
			commandReceiptCount != 1 {
			t.Fatalf(
				"self-healed packet mismatch: eventAggregate=%q Persona=%q outbox=%d receipts=%d",
				eventAggregateID,
				secondPersonaID,
				outboxPacketCount,
				commandReceiptCount,
			)
		}

		testConcurrentPersonaCommandSerialization(t, ctx, pool, personaStore)
		testPersonaCommandWaitsForCloseCleanup(t, ctx, pool, personaStore)
	})
}

func testConcurrentPersonaCommandSerialization(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	store *personapersistence.PersonaCommandPostgresStore,
) {
	t.Helper()
	const (
		ownerA          = "persona-concurrent-owner-a"
		primaryA        = "persona-concurrent-primary-a"
		personaA        = "persona-concurrent-a"
		ownerB          = "persona-concurrent-owner-b"
		primaryB        = "persona-concurrent-primary-b"
		personaB        = "persona-concurrent-b"
		conflictOwner   = "persona-concurrent-conflict-owner"
		conflictPrimary = "persona-concurrent-conflict-primary"
		conflictPersona = "persona-concurrent-conflict"
		commandKey      = "persona-concurrent-command-key"
	)
	for _, fixture := range []struct {
		owner   string
		primary string
	}{
		{ownerA, primaryA},
		{ownerB, primaryB},
		{conflictOwner, conflictPrimary},
	} {
		if err := usersupport.SeedAccountPersona(
			ctx,
			pool,
			fixture.owner,
			fixture.primary,
		); err != nil {
			t.Fatal(err)
		}
	}
	meta := personaports.PersonaCommandMeta{
		IdempotencyKey: commandKey,
		CommandDigest:  "same-concurrent-create-digest",
	}
	type outcome struct {
		result personaports.PersonaCommandResult
		err    error
	}
	start := make(chan struct{})
	outcomes := make(chan outcome, 2)
	for _, persona := range []*usermodel.Persona{
		newPersonaForCommand(personaA, ownerA, "并发分身 A"),
		newPersonaForCommand(personaB, ownerB, "并发分身 B"),
	} {
		go func() {
			<-start
			result, err := store.CommitCreate(ctx, persona, meta)
			outcomes <- outcome{result: result, err: err}
		}()
	}
	close(start)
	first := <-outcomes
	second := <-outcomes
	for index, got := range []outcome{first, second} {
		if got.err != nil {
			t.Fatalf(
				"concurrent CreatePersona outcome %d returned pkey/error: %v",
				index,
				got.err,
			)
		}
	}
	if first.result.PersonaID != second.result.PersonaID {
		t.Fatalf(
			"same-key replay results diverged: first=%+v second=%+v",
			first.result,
			second.result,
		)
	}
	if first.result.Replayed == second.result.Replayed {
		t.Fatalf(
			"same-key concurrent results must contain one commit and one replay: first=%+v second=%+v",
			first.result,
			second.result,
		)
	}
	var (
		personaCount int
		outboxCount  int
		receiptCount int
	)
	if err := pool.QueryRow(ctx, `
SELECT
  (SELECT COUNT(*) FROM personas WHERE persona_id=ANY($1::text[])),
  (SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=ANY($1::text[])),
  (SELECT COUNT(*) FROM personas_command_receipts WHERE idempotency_key=$2)`,
		[]string{personaA, personaB},
		commandKey,
	).Scan(&personaCount, &outboxCount, &receiptCount); err != nil {
		t.Fatalf("count concurrent Persona packet: %v", err)
	}
	if personaCount != 1 || outboxCount != 1 || receiptCount != 1 {
		t.Fatalf(
			"concurrent Persona packet must have one authority: personas=%d outbox=%d receipts=%d",
			personaCount,
			outboxCount,
			receiptCount,
		)
	}

	_, err := store.CommitCreate(
		ctx,
		newPersonaForCommand(conflictPersona, conflictOwner, "冲突分身"),
		personaports.PersonaCommandMeta{
			IdempotencyKey: commandKey,
			CommandDigest:  "different-concurrent-create-digest",
		},
	)
	if !errors.Is(err, personaports.ErrPersonaIdempotencyConflict) {
		t.Fatalf("same key with different digest error=%v, want idempotency conflict", err)
	}
	if err := pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM personas WHERE persona_id=$1`,
		conflictPersona,
	).Scan(&personaCount); err != nil {
		t.Fatalf("count conflicting Persona state: %v", err)
	}
	if personaCount != 0 {
		t.Fatal("different-digest conflict must not mutate Persona state or packet")
	}
	var authoritativeAggregate string
	if err := pool.QueryRow(ctx, `
SELECT aggregate_id
FROM personas_command_receipts
WHERE idempotency_key=$1`,
		commandKey,
	).Scan(&authoritativeAggregate); err != nil {
		t.Fatalf("read authoritative receipt after conflict: %v", err)
	}
	if err := pool.QueryRow(ctx, `
SELECT
  (SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=$1),
  (SELECT COUNT(*) FROM personas_command_receipts
    WHERE idempotency_key=$2 AND aggregate_id=$1)`,
		authoritativeAggregate,
		commandKey,
	).Scan(&outboxCount, &receiptCount); err != nil {
		t.Fatalf("count authoritative packet after conflict: %v", err)
	}
	if authoritativeAggregate != first.result.PersonaID ||
		outboxCount != 1 ||
		receiptCount != 1 {
		t.Fatalf(
			"different-digest conflict changed authority: aggregate=%q result=%q outbox=%d receipts=%d",
			authoritativeAggregate,
			first.result.PersonaID,
			outboxCount,
			receiptCount,
		)
	}
}

func testPersonaCommandWaitsForCloseCleanup(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	store *personapersistence.PersonaCommandPostgresStore,
) {
	t.Helper()
	const (
		oldOwner    = "persona-close-race-old-owner"
		oldPrimary  = "persona-close-race-old-primary"
		oldPersona  = "persona-close-race-old"
		newOwner    = "persona-close-race-new-owner"
		newPrimary  = "persona-close-race-new-primary"
		newPersona  = "persona-close-race-new"
		commandKey  = "persona-close-race-command-key"
		commandHash = "persona-close-race-command-digest"
	)
	for _, fixture := range []struct {
		owner   string
		primary string
	}{
		{oldOwner, oldPrimary},
		{newOwner, newPrimary},
	} {
		if err := usersupport.SeedAccountPersona(
			ctx,
			pool,
			fixture.owner,
			fixture.primary,
		); err != nil {
			t.Fatal(err)
		}
	}
	meta := personaports.PersonaCommandMeta{
		IdempotencyKey: commandKey,
		CommandDigest:  commandHash,
	}
	if _, err := store.CommitCreate(
		ctx,
		newPersonaForCommand(oldPersona, oldOwner, "注销竞态旧分身"),
		meta,
	); err != nil {
		t.Fatalf("seed Persona packet before close cleanup: %v", err)
	}

	cleanupTx, err := pool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin close cleanup transaction: %v", err)
	}
	defer func() { _ = cleanupTx.Rollback(ctx) }()
	if _, err := cleanupTx.Exec(
		ctx,
		`DELETE FROM personas_outbox WHERE aggregate_id=$1`,
		oldPersona,
	); err != nil {
		t.Fatalf("delete Persona outbox in close cleanup: %v", err)
	}
	if _, err := cleanupTx.Exec(
		ctx,
		`DELETE FROM personas_command_receipts WHERE idempotency_key=$1`,
		commandKey,
	); err != nil {
		t.Fatalf("delete Persona receipt in close cleanup: %v", err)
	}

	type outcome struct {
		result personaports.PersonaCommandResult
		err    error
	}
	completed := make(chan outcome, 1)
	go func() {
		result, commitErr := store.CommitCreate(
			ctx,
			newPersonaForCommand(newPersona, newOwner, "注销竞态新分身"),
			meta,
		)
		completed <- outcome{result: result, err: commitErr}
	}()
	waitDeadline := time.Now().Add(2 * time.Second)
	for {
		select {
		case got := <-completed:
			t.Fatalf(
				"CreatePersona crossed uncommitted close cleanup: result=%+v err=%v",
				got.result,
				got.err,
			)
		default:
		}
		var waitingForReceiptDelete int
		if err := pool.QueryRow(ctx, `
SELECT COUNT(*)
FROM pg_stat_activity
WHERE datname=current_database()
  AND pid<>pg_backend_pid()
  AND state='active'
  AND wait_event_type='Lock'
  AND query LIKE '%personas_command_receipts%'
  AND query LIKE '%FOR SHARE%'`,
		).Scan(&waitingForReceiptDelete); err != nil {
			t.Fatalf("observe receipt row-lock wait: %v", err)
		}
		if waitingForReceiptDelete > 0 {
			break
		}
		if time.Now().After(waitDeadline) {
			t.Fatal("CreatePersona did not wait on the receipt DELETE row lock")
		}
		time.Sleep(10 * time.Millisecond)
	}
	if err := cleanupTx.Commit(ctx); err != nil {
		t.Fatalf("commit close cleanup transaction: %v", err)
	}
	var got outcome
	select {
	case got = <-completed:
	case <-time.After(5 * time.Second):
		t.Fatal("CreatePersona did not resume after close cleanup committed")
	}
	if got.err != nil || got.result.PersonaID != newPersona || got.result.Replayed {
		t.Fatalf("CreatePersona after close cleanup result=%+v err=%v", got.result, got.err)
	}
	var (
		outboxCount  int
		receiptCount int
	)
	if err := pool.QueryRow(ctx, `
SELECT
  (SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=$1),
  (SELECT COUNT(*) FROM personas_command_receipts
    WHERE idempotency_key=$2 AND aggregate_id=$1)`,
		newPersona,
		commandKey,
	).Scan(&outboxCount, &receiptCount); err != nil {
		t.Fatalf("count post-close Persona packet: %v", err)
	}
	if outboxCount != 1 || receiptCount != 1 {
		t.Fatalf(
			"post-close Persona packet missing: outbox=%d receipts=%d",
			outboxCount,
			receiptCount,
		)
	}
}

func newPersonaForCommand(
	personaID string,
	ownerID string,
	displayName string,
) *usermodel.Persona {
	return &usermodel.Persona{
		PersonaID:                personaID,
		UserID:                   ownerID,
		DisplayName:              displayName,
		IdentityTags:             []string{},
		IsolationLevel:           "open",
		Status:                   "active",
		InheritsProfileFromOwner: true,
		OverriddenProfileFields:  []string{},
	}
}
