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
			firstOwnerID    = "orphan-outbox-owner-before-close"
			firstPrimaryID  = "orphan-outbox-primary-before-close"
			firstPersonaID  = "orphan-outbox-persona-before-close"
			closeCommandKey = "persona-orphan-outbox-close-key"
		)
		meta := personaports.PersonaCommandMeta{
			IdempotencyKey: closeCommandKey,
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

		var closedOwnerEventID string
		if err := pool.QueryRow(ctx, `
SELECT event_id
FROM personas_outbox
WHERE aggregate_id=$1 AND event_type='PersonaCreated'`,
			firstPersonaID,
		).Scan(&closedOwnerEventID); err != nil {
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
			closedOwnerEventID,
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

		testPersonaCommandRepairsSameOwnerOrphanOutbox(t, ctx, pool, personaStore)
		testPersonaCommandReceiptIsolatesOwners(t, ctx, pool, personaStore)
		testConcurrentPersonaCommandSerialization(t, ctx, pool, personaStore)
		testPersonaCommandWaitsForCloseCleanup(t, ctx, pool, personaStore)
	})
}

// 命令身份按 owner 隔离后，孤儿 outbox 只可能来自同一 owner 复用同一幂等键：
// receipt 已被保留期清理，outbox 行还在。此时新命令必须自愈该 packet，而不是
// 撞 personas_outbox_pkey。
func testPersonaCommandRepairsSameOwnerOrphanOutbox(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	store *personapersistence.PersonaCommandPostgresStore,
) {
	t.Helper()
	const (
		ownerID    = "persona-orphan-repair-owner"
		primaryID  = "persona-orphan-repair-primary"
		firstID    = "persona-orphan-repair-first"
		secondID   = "persona-orphan-repair-second"
		commandKey = "persona-orphan-repair-key"
	)
	if err := usersupport.SeedAccountPersona(ctx, pool, ownerID, primaryID); err != nil {
		t.Fatal(err)
	}
	meta := personaports.PersonaCommandMeta{
		IdempotencyKey: commandKey,
		CommandDigest:  "persona-orphan-repair-digest",
	}
	if _, err := store.CommitCreate(
		ctx,
		newPersonaForCommand(firstID, ownerID, "孤儿修复首个分身"),
		meta,
	); err != nil {
		t.Fatalf("seed first Persona packet: %v", err)
	}
	var orphanEventID string
	if err := pool.QueryRow(ctx,
		`SELECT event_id FROM personas_outbox WHERE aggregate_id=$1`,
		firstID,
	).Scan(&orphanEventID); err != nil {
		t.Fatalf("read seeded outbox event: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`DELETE FROM personas_command_receipts WHERE owner_id=$1 AND idempotency_key=$2`,
		ownerID, commandKey,
	); err != nil {
		t.Fatalf("simulate retention receipt cleanup: %v", err)
	}

	result, err := store.CommitCreate(
		ctx,
		newPersonaForCommand(secondID, ownerID, "孤儿修复后续分身"),
		meta,
	)
	if err != nil {
		t.Fatalf("CommitCreate must repair the orphan outbox row, got %v", err)
	}
	if result.PersonaID != secondID || result.Replayed {
		t.Fatalf("orphan repair result=%+v, want fresh commit of %q", result, secondID)
	}
	var (
		eventAggregateID string
		outboxCount      int
		receiptCount     int
	)
	if err := pool.QueryRow(ctx, `
SELECT
  (SELECT aggregate_id FROM personas_outbox WHERE event_id=$1),
  (SELECT COUNT(*) FROM personas_outbox WHERE event_id=$1),
  (SELECT COUNT(*) FROM personas_command_receipts
    WHERE owner_id=$2 AND idempotency_key=$3)`,
		orphanEventID, ownerID, commandKey,
	).Scan(&eventAggregateID, &outboxCount, &receiptCount); err != nil {
		t.Fatalf("count repaired packet: %v", err)
	}
	if eventAggregateID != secondID || outboxCount != 1 || receiptCount != 1 {
		t.Fatalf(
			"repaired packet mismatch: aggregate=%q outbox=%d receipts=%d",
			eventAggregateID, outboxCount, receiptCount,
		)
	}
}

// 同一 Idempotency-Key 在两个 owner 下是两条独立命令：各自提交自己的 Persona，
// 互不回放、互不冲突，也不会返回对方的身份。
func testPersonaCommandReceiptIsolatesOwners(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	store *personapersistence.PersonaCommandPostgresStore,
) {
	t.Helper()
	const (
		ownerA     = "persona-owner-scope-owner-a"
		primaryA   = "persona-owner-scope-primary-a"
		personaA   = "persona-owner-scope-a"
		ownerB     = "persona-owner-scope-owner-b"
		primaryB   = "persona-owner-scope-primary-b"
		personaB   = "persona-owner-scope-b"
		commandKey = "persona-owner-scope-shared-key"
	)
	for _, fixture := range [][2]string{{ownerA, primaryA}, {ownerB, primaryB}} {
		if err := usersupport.SeedAccountPersona(ctx, pool, fixture[0], fixture[1]); err != nil {
			t.Fatal(err)
		}
	}
	meta := personaports.PersonaCommandMeta{
		IdempotencyKey: commandKey,
		CommandDigest:  "persona-owner-scope-digest",
	}
	resultA, err := store.CommitCreate(
		ctx, newPersonaForCommand(personaA, ownerA, "owner A 分身"), meta,
	)
	if err != nil || resultA.PersonaID != personaA || resultA.Replayed {
		t.Fatalf("owner A create result=%+v err=%v", resultA, err)
	}
	resultB, err := store.CommitCreate(
		ctx, newPersonaForCommand(personaB, ownerB, "owner B 分身"), meta,
	)
	if err != nil {
		t.Fatalf("owner B must not inherit owner A receipt: %v", err)
	}
	if resultB.PersonaID != personaB || resultB.Replayed {
		t.Fatalf("owner B create result=%+v, want fresh commit of %q", resultB, personaB)
	}

	var personaCount, outboxCount, receiptCount int
	if err := pool.QueryRow(ctx, `
SELECT
  (SELECT COUNT(*) FROM personas WHERE persona_id=ANY($1::text[])),
  (SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=ANY($1::text[])),
  (SELECT COUNT(*) FROM personas_command_receipts WHERE idempotency_key=$2)`,
		[]string{personaA, personaB}, commandKey,
	).Scan(&personaCount, &outboxCount, &receiptCount); err != nil {
		t.Fatalf("count owner-scoped packets: %v", err)
	}
	if personaCount != 2 || outboxCount != 2 || receiptCount != 2 {
		t.Fatalf(
			"owner-scoped same key must keep two authorities: personas=%d outbox=%d receipts=%d",
			personaCount, outboxCount, receiptCount,
		)
	}
	for owner, persona := range map[string]string{ownerA: personaA, ownerB: personaB} {
		var aggregateID string
		if err := pool.QueryRow(ctx, `
SELECT aggregate_id FROM personas_command_receipts
WHERE owner_id=$1 AND idempotency_key=$2`,
			owner, commandKey,
		).Scan(&aggregateID); err != nil {
			t.Fatalf("read receipt for owner %q: %v", owner, err)
		}
		if aggregateID != persona {
			t.Fatalf("owner %q receipt points at %q, want %q", owner, aggregateID, persona)
		}
	}
}

func testConcurrentPersonaCommandSerialization(
	t *testing.T,
	ctx context.Context,
	pool *pgxpool.Pool,
	store *personapersistence.PersonaCommandPostgresStore,
) {
	t.Helper()
	// 同一 owner 内并发复用同一幂等键：一次提交、一次回放，且两次都指向同一个
	// 真实 Persona。跨 owner 隔离由 testPersonaCommandReceiptIsolatesOwners 覆盖。
	const (
		ownerID         = "persona-concurrent-owner"
		primaryID       = "persona-concurrent-primary"
		personaA        = "persona-concurrent-a"
		personaB        = "persona-concurrent-b"
		conflictPersona = "persona-concurrent-conflict"
		commandKey      = "persona-concurrent-command-key"
	)
	if err := usersupport.SeedAccountPersona(ctx, pool, ownerID, primaryID); err != nil {
		t.Fatal(err)
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
		newPersonaForCommand(personaA, ownerID, "并发分身 A"),
		newPersonaForCommand(personaB, ownerID, "并发分身 B"),
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
  (SELECT COUNT(*) FROM personas_command_receipts
    WHERE owner_id=$3 AND idempotency_key=$2)`,
		[]string{personaA, personaB},
		commandKey,
		ownerID,
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
		newPersonaForCommand(conflictPersona, ownerID, "冲突分身"),
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
WHERE owner_id=$1 AND idempotency_key=$2`,
		ownerID,
		commandKey,
	).Scan(&authoritativeAggregate); err != nil {
		t.Fatalf("read authoritative receipt after conflict: %v", err)
	}
	if err := pool.QueryRow(ctx, `
SELECT
  (SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=$1),
  (SELECT COUNT(*) FROM personas_command_receipts
    WHERE owner_id=$3 AND idempotency_key=$2 AND aggregate_id=$1)`,
		authoritativeAggregate,
		commandKey,
		ownerID,
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
	// receipt 的行锁与命令身份同为 owner 维度，因此竞态发生在同一 owner 复用
	// 同一幂等键时：新命令必须等待未提交的清理事务，不能跨过它自建 packet。
	const (
		ownerID     = "persona-close-race-owner"
		primaryID   = "persona-close-race-primary"
		oldPersona  = "persona-close-race-old"
		newPersona  = "persona-close-race-new"
		commandKey  = "persona-close-race-command-key"
		commandHash = "persona-close-race-command-digest"
	)
	if err := usersupport.SeedAccountPersona(ctx, pool, ownerID, primaryID); err != nil {
		t.Fatal(err)
	}
	meta := personaports.PersonaCommandMeta{
		IdempotencyKey: commandKey,
		CommandDigest:  commandHash,
	}
	if _, err := store.CommitCreate(
		ctx,
		newPersonaForCommand(oldPersona, ownerID, "注销竞态旧分身"),
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
		`DELETE FROM personas_command_receipts WHERE owner_id=$1 AND idempotency_key=$2`,
		ownerID,
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
			newPersonaForCommand(newPersona, ownerID, "注销竞态新分身"),
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
    WHERE owner_id=$3 AND idempotency_key=$2 AND aggregate_id=$1)`,
		newPersona,
		commandKey,
		ownerID,
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
