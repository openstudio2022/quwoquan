package api_integration

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5"

	"quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

func TestManagedMigrationsAreIdempotent(t *testing.T) {
	ctx := context.Background()
	if _, err := pgPool.Exec(ctx, `
		INSERT INTO user_profiles (
			user_id,
			account_state,
			identity_origin,
			logical_shard,
			anonymous_retention_policy,
			phone,
			nickname,
			profile_version
		) VALUES (
			'migration_repeat_user',
			'active',
			'phone',
			7,
			'preserve',
			'migration_repeat_phone',
			'migration_repeat_nickname',
			1
		)
	`); err != nil {
		t.Fatalf("seed persisted row: %v", err)
	}
	t.Cleanup(func() {
		_, _ = pgPool.Exec(context.Background(), `DELETE FROM user_profiles WHERE user_id = 'migration_repeat_user'`)
	})

	if err := persistence.RunManagedMigrations(ctx, pgPool); err != nil {
		t.Fatalf("rerun managed migrations: %v", err)
	}

	var count int
	if err := pgPool.QueryRow(ctx, `SELECT COUNT(*) FROM user_profiles WHERE user_id = 'migration_repeat_user'`).Scan(&count); err != nil {
		t.Fatalf("count persisted row: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected persisted row to survive repeated migration run, got %d", count)
	}

	// 真相源对齐：ledger 行数必须等于磁盘上的受管迁移文件数（每个迁移恰好一行，
	// 重跑不重复、不遗漏），避免硬编码数字随新增迁移 stale。
	migrationNames, err := persistence.ManagedMigrationFilenames()
	if err != nil {
		t.Fatalf("list managed migrations: %v", err)
	}
	expectedCount := len(migrationNames)

	var appliedCount int
	if err := pgPool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM service_schema_migrations
		WHERE service_name = 'user-service'
	`).Scan(&appliedCount); err != nil {
		t.Fatalf("count migration ledger rows: %v", err)
	}
	if appliedCount != expectedCount {
		t.Fatalf("expected ledger to record %d managed migrations, got %d", expectedCount, appliedCount)
	}

	var personaContactColumnCount int
	if err := pgPool.QueryRow(ctx, `
		SELECT COUNT(*)
		FROM information_schema.columns
		WHERE table_schema = current_schema()
		  AND table_name = 'personas'
		  AND column_name IN ('phone', 'email')
	`).Scan(&personaContactColumnCount); err != nil {
		t.Fatalf("inspect persona contact columns: %v", err)
	}
	if personaContactColumnCount != 0 {
		t.Fatalf("Persona must not retain phone/email plaintext columns, got %d", personaContactColumnCount)
	}

	currentActorColumns := []struct {
		table  string
		column string
	}{
		{table: "user_profiles", column: "persona_count"},
		{table: "personas", column: "persona_id"},
		{table: "profile_update_proposals", column: "persona_id"},
		{table: "profile_qr_tokens", column: "persona_id"},
		{table: "contact_discovery_records", column: "matched_persona_ids"},
		{table: "greeting_requests", column: "requester_persona_id"},
		{table: "greeting_requests", column: "target_persona_id"},
		{
			table:  "greeting_request_command_receipts",
			column: "actor_persona_id",
		},
		{table: "invite_records", column: "inviter_persona_id"},
	}
	for _, expected := range currentActorColumns {
		var exists bool
		if err := pgPool.QueryRow(ctx, `
			SELECT EXISTS (
				SELECT 1
				FROM information_schema.columns
				WHERE table_schema = current_schema()
				  AND table_name = $1
				  AND column_name = $2
			)
		`, expected.table, expected.column).Scan(&exists); err != nil {
			t.Fatalf(
				"inspect canonical actor column %s.%s: %v",
				expected.table,
				expected.column,
				err,
			)
		}
		if !exists {
			t.Errorf(
				"managed migrations must expose canonical actor column %s.%s",
				expected.table,
				expected.column,
			)
		}
	}

	retiredActor := "sub" + "_account"
	retiredActorColumns := []struct {
		table  string
		column string
	}{
		{table: "user_profiles", column: retiredActor + "_count"},
		{table: "personas", column: retiredActor + "_id"},
		{table: "profile_update_proposals", column: retiredActor + "_id"},
		{table: "profile_qr_tokens", column: retiredActor + "_id"},
		{
			table:  "contact_discovery_records",
			column: "matched_" + retiredActor + "_ids",
		},
		{
			table:  "greeting_requests",
			column: "requester_" + retiredActor + "_id",
		},
		{
			table:  "greeting_requests",
			column: "target_" + retiredActor + "_id",
		},
		{
			table:  "greeting_request_command_receipts",
			column: "actor_" + retiredActor + "_id",
		},
		{
			table:  "invite_records",
			column: "inviter_" + retiredActor + "_id",
		},
	}
	for _, retired := range retiredActorColumns {
		var exists bool
		if err := pgPool.QueryRow(ctx, `
			SELECT EXISTS (
				SELECT 1
				FROM information_schema.columns
				WHERE table_schema = current_schema()
				  AND table_name = $1
				  AND column_name = $2
			)
		`, retired.table, retired.column).Scan(&exists); err != nil {
			t.Fatalf(
				"inspect retired actor column %s.%s: %v",
				retired.table,
				retired.column,
				err,
			)
		}
		if exists {
			t.Errorf(
				"managed migrations must remove retired actor column %s.%s",
				retired.table,
				retired.column,
			)
		}
	}
}

func TestPersonaActorSingleTrackMigrationPreservesGreetingJSONAndIsIdempotent(t *testing.T) {
	ctx := context.Background()
	tx, err := pgPool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin migration fixture transaction: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err := tx.Exec(ctx, `
		DELETE FROM greeting_request_command_receipts;
		DELETE FROM greeting_request_outbox;
	`); err != nil {
		t.Fatalf("isolate greeting migration fixtures: %v", err)
	}

	legacyRequesterKey, legacyTargetKey := retiredGreetingActorJSONKeys()
	legacyReceipt := mustJSON(t, map[string]any{
		"id":                 "00000000-0000-0000-0000-000000000101",
		legacyRequesterKey:   "persona-requester",
		legacyTargetKey:      "persona-target",
		"status":             "pending",
		"requestMessage":     "你好，成都",
		"source":             "profile",
		"nestedEvidence":     map[string]any{"attempt": 7, "accepted": false},
		"unchangedReference": []any{"alpha", 42, nil},
	})
	canonicalReceipt := mustJSON(t, map[string]any{
		"id":                 "00000000-0000-0000-0000-000000000101",
		"requesterPersonaId": "persona-requester",
		"targetPersonaId":    "persona-target",
		"status":             "pending",
		"requestMessage":     "你好，成都",
		"source":             "profile",
		"nestedEvidence":     map[string]any{"attempt": 7, "accepted": false},
		"unchangedReference": []any{"alpha", 42, nil},
	})
	legacyOutbox := mustJSON(t, map[string]any{
		"id":                           "00000000-0000-0000-0000-000000000201",
		legacyRequesterKey:             "persona-requester",
		legacyTargetKey:                "persona-target",
		"source":                       "profile",
		"targetAllowsStrangerGreeting": true,
		"nestedEvidence":               map[string]any{"labels": []any{"一", "二"}},
	})
	canonicalOutbox := mustJSON(t, map[string]any{
		"id":                           "00000000-0000-0000-0000-000000000201",
		"requesterPersonaId":           "persona-requester",
		"targetPersonaId":              "persona-target",
		"source":                       "profile",
		"targetAllowsStrangerGreeting": true,
		"nestedEvidence":               map[string]any{"labels": []any{"一", "二"}},
	})

	if _, err := tx.Exec(ctx, `
		INSERT INTO greeting_request_command_receipts (
			receipt_id, actor_persona_id, idempotency_key, operation,
			request_id, response_json, created_at
		) VALUES (
			'greeting-json-migration-receipt', 'persona-requester',
			'greeting-json-migration-key', 'SendGreetingRequest',
			'00000000-0000-0000-0000-000000000101', $1::jsonb, NOW()
		)
	`, legacyReceipt); err != nil {
		t.Fatalf("seed legacy greeting receipt JSON: %v", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO greeting_request_outbox (
			event_id, aggregate_id, event_name, payload_json, occurred_at
		) VALUES (
			'greeting-json-migration-pending',
			'00000000-0000-0000-0000-000000000201',
			'GreetingRequestSent', $1::jsonb, NOW()
		)
	`, legacyOutbox); err != nil {
		t.Fatalf("seed pending greeting outbox JSON: %v", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO greeting_request_outbox (
			event_id, aggregate_id, event_name, payload_json, occurred_at, published_at
		) VALUES (
			'greeting-json-migration-published',
			'00000000-0000-0000-0000-000000000202',
			'GreetingRequestSent', $1::jsonb, NOW(), NOW()
		)
	`, legacyOutbox); err != nil {
		t.Fatalf("seed published greeting outbox history: %v", err)
	}

	migrationSQL := readPersonaActorSingleTrackMigrationSQL(t)
	if _, err := tx.Exec(ctx, migrationSQL); err != nil {
		t.Fatalf("apply persona actor JSON migration: %v", err)
	}

	assertGreetingJSONMigrationState(
		t,
		ctx,
		tx,
		canonicalReceipt,
		canonicalOutbox,
		legacyOutbox,
	)
	receiptAfterFirst, pendingAfterFirst, publishedAfterFirst :=
		readGreetingMigrationJSON(t, ctx, tx)

	if _, err := tx.Exec(ctx, migrationSQL); err != nil {
		t.Fatalf("rerun persona actor JSON migration: %v", err)
	}
	assertGreetingJSONMigrationState(
		t,
		ctx,
		tx,
		canonicalReceipt,
		canonicalOutbox,
		legacyOutbox,
	)
	receiptAfterSecond, pendingAfterSecond, publishedAfterSecond :=
		readGreetingMigrationJSON(t, ctx, tx)
	if receiptAfterSecond != receiptAfterFirst ||
		pendingAfterSecond != pendingAfterFirst ||
		publishedAfterSecond != publishedAfterFirst {
		t.Fatalf(
			"second persona actor JSON migration changed persisted bytes:\nreceipt %s -> %s\npending %s -> %s\npublished %s -> %s",
			receiptAfterFirst,
			receiptAfterSecond,
			pendingAfterFirst,
			pendingAfterSecond,
			publishedAfterFirst,
			publishedAfterSecond,
		)
	}
}

func TestPersonaActorSingleTrackMigrationRejectsAmbiguousGreetingJSON(t *testing.T) {
	legacyRequesterKey, legacyTargetKey := retiredGreetingActorJSONKeys()
	conflictingPayload := mustJSON(t, map[string]any{
		legacyRequesterKey:   "persona-requester",
		legacyTargetKey:      "persona-target",
		"requesterPersonaId": "persona-requester",
		"targetPersonaId":    "persona-target",
	})
	migrationSQL := readPersonaActorSingleTrackMigrationSQL(t)

	for _, testCase := range []struct {
		name          string
		pendingOutbox bool
		wantError     string
	}{
		{
			name:      "command receipt",
			wantError: "greeting receipt JSON contains mixed",
		},
		{
			name:          "pending outbox",
			pendingOutbox: true,
			wantError:     "pending greeting outbox JSON contains mixed",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			ctx := context.Background()
			tx, err := pgPool.Begin(ctx)
			if err != nil {
				t.Fatalf("begin fail-closed fixture transaction: %v", err)
			}
			defer func() { _ = tx.Rollback(ctx) }()

			if _, err := tx.Exec(ctx, `
				DELETE FROM greeting_request_command_receipts;
				DELETE FROM greeting_request_outbox;
			`); err != nil {
				t.Fatalf("isolate fail-closed fixtures: %v", err)
			}
			if testCase.pendingOutbox {
				_, err = tx.Exec(ctx, `
					INSERT INTO greeting_request_outbox (
						event_id, aggregate_id, event_name, payload_json, occurred_at
					) VALUES (
						'greeting-json-migration-conflict',
						'00000000-0000-0000-0000-000000000301',
						'GreetingRequestSent', $1::jsonb, NOW()
					)
				`, conflictingPayload)
			} else {
				_, err = tx.Exec(ctx, `
					INSERT INTO greeting_request_command_receipts (
						receipt_id, actor_persona_id, idempotency_key, operation,
						request_id, response_json, created_at
					) VALUES (
						'greeting-json-migration-conflict', 'persona-requester',
						'greeting-json-migration-conflict', 'SendGreetingRequest',
						'00000000-0000-0000-0000-000000000301', $1::jsonb, NOW()
					)
				`, conflictingPayload)
			}
			if err != nil {
				t.Fatalf("seed fail-closed fixture: %v", err)
			}

			if _, err := tx.Exec(ctx, migrationSQL); err == nil {
				t.Fatal("ambiguous greeting JSON was accepted")
			} else if !strings.Contains(err.Error(), testCase.wantError) {
				t.Fatalf("unexpected migration failure: %v", err)
			}
		})
	}
}

func TestSubjectFollowReceiptPersonaMigrationIsCanonicalAndIdempotent(t *testing.T) {
	ctx := context.Background()
	tx, err := pgPool.Begin(ctx)
	if err != nil {
		t.Fatalf("begin subject follow receipt migration transaction: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if _, err := tx.Exec(ctx, `DELETE FROM subject_follow_command_receipts`); err != nil {
		t.Fatalf("isolate subject follow receipt fixtures: %v", err)
	}
	legacy := mustJSON(t, map[string]any{
		"Follow": map[string]any{
			"ID":          "sf_receipt_migration",
			"PersonaID":   "persona-receipt-migration",
			"SubjectType": "homepage",
			"SubjectID":   "homepage-receipt-migration",
			"State":       "following",
			"Version":     3,
			"FollowedAt":  "2026-07-30T12:00:00Z",
			"UpdatedAt":   "2026-07-30T12:01:00Z",
		},
		"Changed":          true,
		"IdempotentReplay": false,
		"OccurredAt":       "2026-07-30T12:01:00Z",
	})
	canonical := mustJSON(t, map[string]any{
		"follow": map[string]any{
			"id":          "sf_receipt_migration",
			"personaId":   "persona-receipt-migration",
			"subjectType": "homepage",
			"subjectId":   "homepage-receipt-migration",
			"state":       "following",
			"version":     3,
			"followedAt":  "2026-07-30T12:00:00Z",
			"updatedAt":   "2026-07-30T12:01:00Z",
		},
		"changed":          true,
		"idempotentReplay": false,
		"occurredAt":       "2026-07-30T12:01:00Z",
	})
	if _, err := tx.Exec(ctx, `
		INSERT INTO subject_follow_command_receipts (
			receipt_id, persona_id, idempotency_key, operation,
			aggregate_id, aggregate_version, response_json
		) VALUES (
			'subject-follow-receipt-migration',
			'persona-receipt-migration',
			'subject-follow-receipt-migration',
			'FollowSubject',
			'sf_receipt_migration', 3, $1::jsonb
		)
	`, legacy); err != nil {
		t.Fatalf("seed legacy subject follow receipt: %v", err)
	}

	migrationSQL := readSubjectFollowReceiptPersonaMigrationSQL(t)
	if _, err := tx.Exec(ctx, migrationSQL); err != nil {
		t.Fatalf("apply subject follow receipt migration: %v", err)
	}
	var (
		matches bool
		first   string
	)
	if err := tx.QueryRow(ctx, `
		SELECT response_json = $1::jsonb, response_json::text
		FROM subject_follow_command_receipts
		WHERE receipt_id = 'subject-follow-receipt-migration'
	`, canonical).Scan(&matches, &first); err != nil {
		t.Fatalf("read migrated subject follow receipt: %v", err)
	}
	if !matches {
		t.Fatalf("subject follow receipt did not migrate to canonical JSON")
	}

	if _, err := tx.Exec(ctx, migrationSQL); err != nil {
		t.Fatalf("rerun subject follow receipt migration: %v", err)
	}
	var second string
	if err := tx.QueryRow(ctx, `
		SELECT response_json::text
		FROM subject_follow_command_receipts
		WHERE receipt_id = 'subject-follow-receipt-migration'
	`).Scan(&second); err != nil {
		t.Fatalf("read idempotently migrated subject follow receipt: %v", err)
	}
	if second != first {
		t.Fatalf("second subject follow receipt migration changed JSON: %s -> %s", first, second)
	}
}

func TestSubjectFollowReceiptPersonaMigrationRejectsAmbiguousJSON(t *testing.T) {
	canonicalFollow := map[string]any{
		"id":          "sf_receipt_conflict",
		"personaId":   "persona-receipt-conflict",
		"subjectType": "homepage",
		"subjectId":   "homepage-receipt-conflict",
		"state":       "following",
		"version":     1,
		"followedAt":  "2026-07-30T12:00:00Z",
		"updatedAt":   "2026-07-30T12:00:00Z",
	}
	cases := []struct {
		name      string
		payload   map[string]any
		wantError string
	}{
		{
			name: "mixed top-level keys",
			payload: map[string]any{
				"follow":           canonicalFollow,
				"Follow":           canonicalFollow,
				"changed":          true,
				"idempotentReplay": false,
				"occurredAt":       "2026-07-30T12:00:00Z",
			},
			wantError: "mixed, partial, or unknown top-level keys",
		},
		{
			name: "mixed nested persona keys",
			payload: map[string]any{
				"follow": func() map[string]any {
					mixed := make(map[string]any, len(canonicalFollow)+1)
					for key, value := range canonicalFollow {
						mixed[key] = value
					}
					mixed["PersonaID"] = "persona-receipt-conflict"
					return mixed
				}(),
				"changed":          true,
				"idempotentReplay": false,
				"occurredAt":       "2026-07-30T12:00:00Z",
			},
			wantError: "mixed, partial, or unknown canonical follow keys",
		},
	}
	migrationSQL := readSubjectFollowReceiptPersonaMigrationSQL(t)
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			ctx := context.Background()
			tx, err := pgPool.Begin(ctx)
			if err != nil {
				t.Fatalf("begin subject follow receipt conflict transaction: %v", err)
			}
			defer func() { _ = tx.Rollback(ctx) }()
			if _, err := tx.Exec(ctx, `DELETE FROM subject_follow_command_receipts`); err != nil {
				t.Fatalf("isolate subject follow receipt conflict fixtures: %v", err)
			}
			if _, err := tx.Exec(ctx, `
				INSERT INTO subject_follow_command_receipts (
					receipt_id, persona_id, idempotency_key, operation,
					aggregate_id, aggregate_version, response_json
				) VALUES (
					'subject-follow-receipt-conflict',
					'persona-receipt-conflict',
					'subject-follow-receipt-conflict',
					'FollowSubject', 'sf_receipt_conflict', 1, $1::jsonb
				)
			`, mustJSON(t, testCase.payload)); err != nil {
				t.Fatalf("seed ambiguous subject follow receipt: %v", err)
			}
			if _, err := tx.Exec(ctx, migrationSQL); err == nil {
				t.Fatal("ambiguous subject follow receipt JSON was accepted")
			} else if !strings.Contains(err.Error(), testCase.wantError) {
				t.Fatalf("unexpected subject follow receipt migration failure: %v", err)
			}
		})
	}
}

func retiredGreetingActorJSONKeys() (string, string) {
	retiredActor := "Sub" + "Account"
	return "requester" + retiredActor + "Id", "target" + retiredActor + "Id"
}

func readPersonaActorSingleTrackMigrationSQL(t *testing.T) string {
	return readUserAccountMigrationSQL(t, "045_persona_actor_single_track.up.sql")
}

func readSubjectFollowReceiptPersonaMigrationSQL(t *testing.T) string {
	return readUserAccountMigrationSQL(
		t,
		"046_subject_follow_receipt_persona_single_track.up.sql",
	)
}

func readUserAccountMigrationSQL(t *testing.T, filename string) string {
	t.Helper()
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve migration test source path")
	}
	migrationPath := filepath.Clean(filepath.Join(
		filepath.Dir(sourcePath),
		"..", "..", "..", "..",
		"resources", "migrations", "account", "user_account",
		filename,
	))
	contents, err := os.ReadFile(migrationPath)
	if err != nil {
		t.Fatalf("read user account migration %s: %v", migrationPath, err)
	}
	return string(contents)
}

func mustJSON(t *testing.T, value any) string {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("encode JSON fixture: %v", err)
	}
	return string(encoded)
}

type greetingMigrationQueryer interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

func assertGreetingJSONMigrationState(
	t *testing.T,
	ctx context.Context,
	queryer greetingMigrationQueryer,
	canonicalReceipt string,
	canonicalPendingOutbox string,
	legacyPublishedOutbox string,
) {
	t.Helper()
	assertJSONBMatches := func(query, expected string) {
		t.Helper()
		var matches bool
		if err := queryer.QueryRow(ctx, query, expected).Scan(&matches); err != nil {
			t.Fatalf("read migrated greeting JSON: %v", err)
		}
		if !matches {
			t.Fatalf("migrated greeting JSON differs from expected value")
		}
	}
	assertJSONBMatches(`
		SELECT response_json = $1::jsonb
		FROM greeting_request_command_receipts
		WHERE receipt_id = 'greeting-json-migration-receipt'
	`, canonicalReceipt)
	assertJSONBMatches(`
		SELECT payload_json = $1::jsonb
		FROM greeting_request_outbox
		WHERE event_id = 'greeting-json-migration-pending'
	`, canonicalPendingOutbox)
	assertJSONBMatches(`
		SELECT payload_json = $1::jsonb
		FROM greeting_request_outbox
		WHERE event_id = 'greeting-json-migration-published'
	`, legacyPublishedOutbox)
}

func readGreetingMigrationJSON(
	t *testing.T,
	ctx context.Context,
	queryer greetingMigrationQueryer,
) (string, string, string) {
	t.Helper()
	read := func(query string) string {
		t.Helper()
		var value string
		if err := queryer.QueryRow(ctx, query).Scan(&value); err != nil {
			t.Fatalf("read greeting migration JSON: %v", err)
		}
		return value
	}
	return read(`
			SELECT response_json::text
			FROM greeting_request_command_receipts
			WHERE receipt_id = 'greeting-json-migration-receipt'
		`), read(`
			SELECT payload_json::text
			FROM greeting_request_outbox
			WHERE event_id = 'greeting-json-migration-pending'
		`), read(`
			SELECT payload_json::text
			FROM greeting_request_outbox
			WHERE event_id = 'greeting-json-migration-published'
		`)
}
