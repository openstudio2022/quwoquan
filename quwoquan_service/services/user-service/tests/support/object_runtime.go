// Package support provides real dependency fixtures shared by object-scoped
// API integration suites. It never substitutes in-memory repositories.
package support

import (
	"context"
	"crypto/sha256"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/internal/platform/testinfra"
	userpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

func SeedAccountPersona(
	ctx context.Context,
	pool *pgxpool.Pool,
	accountID string,
	personaID string,
) error {
	digest := sha256.Sum256([]byte(accountID))
	phone := fmt.Sprintf("t_%x", digest[:8])
	if _, err := pool.Exec(ctx, `
INSERT INTO user_profiles (
  user_id, account_state, identity_origin, logical_shard, anonymous_retention_policy,
  phone, nickname, nickname_customized, avatar_url, avatar_asset_id, avatar_version,
  background_url, bio, identity_tags, gender, region, owner_display_name,
  profile_version, persona_count, created_at, updated_at
) VALUES (
  $1, 'active', 'api_integration', 1, 'preserve',
  $2, $1, false, '', '', 0, '', '', '', '', '', '', 1, 1, NOW(), NOW()
)`, accountID, phone); err != nil {
		return fmt.Errorf("seed account authority: %w", err)
	}
	if _, err := pool.Exec(ctx, `
INSERT INTO personas (
  user_id, persona_id, display_name, user_handle, avatar_url, purpose_hint,
  inherits_profile_from_owner, overridden_profile_fields, is_primary,
  is_private, is_active, status, isolation_level, version, created_at, updated_at
) VALUES ($1, $2, $2, '', '', '', true, '{}', true, false, true, 'active', 'open', 1, NOW(), NOW())`,
		accountID, personaID,
	); err != nil {
		return fmt.Errorf("seed Persona authority: %w", err)
	}
	return nil
}

func WithUserPostgres(
	t testing.TB,
	test func(context.Context, *pgxpool.Pool),
) {
	t.Helper()
	root, err := os.MkdirTemp("", "qwq-user-object-pg-")
	if err != nil {
		t.Fatalf("create PostgreSQL fixture root: %v", err)
	}
	fixture, err := testinfra.StartPostgresFixture(root, 0)
	if err != nil {
		_ = os.RemoveAll(root)
		t.Fatalf("start real PostgreSQL fixture: %v", err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	pool, err := pgxpool.New(ctx, fixture.DSN())
	if err == nil {
		err = pool.Ping(ctx)
	}
	if err == nil {
		err = userpersistence.RunManagedMigrations(ctx, pool)
	}
	if err != nil {
		cancel()
		if pool != nil {
			pool.Close()
		}
		_ = fixture.Close()
		t.Fatalf("initialize real User PostgreSQL: %v", err)
	}
	t.Cleanup(func() {
		cancel()
		pool.Close()
		if closeErr := fixture.Close(); closeErr != nil {
			t.Errorf("close PostgreSQL fixture: %v", closeErr)
		}
	})
	test(ctx, pool)
}

func WithUserMongo(
	t testing.TB,
	test func(context.Context, *testinfra.RealMongo),
) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	runtime, err := testinfra.StartRealMongo(
		ctx,
		fmt.Sprintf("user_object_%d", time.Now().UnixNano()),
	)
	if err != nil {
		cancel()
		t.Fatalf("start real User MongoDB: %v", err)
	}
	t.Cleanup(func() {
		cancel()
		cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cleanupCancel()
		if closeErr := runtime.Close(cleanupCtx); closeErr != nil {
			t.Errorf("close User MongoDB: %v", closeErr)
		}
	})
	test(ctx, runtime)
}
