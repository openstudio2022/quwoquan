package tests

import (
	"context"
	"testing"

	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
)

func TestManagedMigrationsAreIdempotent(t *testing.T) {
	ctx := context.Background()
	runTestMigrations(ctx, pgPool)

	if _, err := pgPool.Exec(ctx, `
		INSERT INTO user_profiles (
			user_id,
			account_state,
			identity_origin,
			logical_shard,
			anonymous_retention_policy,
			phone,
			nickname,
			status,
			profile_version
		) VALUES (
			'migration_repeat_user',
			'active',
			'phone',
			7,
			'preserve',
			'migration_repeat_phone',
			'migration_repeat_nickname',
			'active',
			1
		)
	`); err != nil {
		t.Fatalf("seed persisted row: %v", err)
	}

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
}
