package api_integration

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/internal/platform/testinfra"
	settingpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/infrastructure/persistence"
)

var (
	settingPool  *pgxpool.Pool
	settingStore *settingpersistence.PgStore
)

func TestMain(m *testing.M) {
	fixtureRoot, err := os.MkdirTemp("", "qwq-assistant-skill-setting-pg-")
	if err != nil {
		panic(fmt.Sprintf("create SkillUserSetting PostgreSQL root: %v", err))
	}
	fixture, err := testinfra.StartPostgresFixture(fixtureRoot, 0)
	if err != nil {
		_ = os.RemoveAll(fixtureRoot)
		panic(fmt.Sprintf("start SkillUserSetting PostgreSQL: %v", err))
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	settingPool, err = pgxpool.New(ctx, fixture.DSN())
	if err == nil {
		err = settingPool.Ping(ctx)
	}
	if err == nil {
		settingStore = settingpersistence.NewPgStore(settingPool)
		err = settingStore.EnsureSchema(ctx)
	}
	cancel()
	if err != nil {
		if settingPool != nil {
			settingPool.Close()
		}
		_ = fixture.Close()
		_ = os.RemoveAll(fixtureRoot)
		panic(fmt.Sprintf("initialize SkillUserSetting PostgreSQL: %v", err))
	}

	exitCode := m.Run()
	settingPool.Close()
	if closeErr := fixture.Close(); closeErr != nil {
		fmt.Fprintf(os.Stderr, "close SkillUserSetting PostgreSQL: %v\n", closeErr)
		exitCode = 1
	}
	if removeErr := os.RemoveAll(fixtureRoot); removeErr != nil {
		fmt.Fprintf(os.Stderr, "remove SkillUserSetting PostgreSQL root: %v\n", removeErr)
		exitCode = 1
	}
	os.Exit(exitCode)
}

func resetSettingState(t *testing.T) {
	t.Helper()
	if _, err := settingPool.Exec(context.Background(), `
TRUNCATE TABLE skill_user_setting_outbox,
  skill_user_setting_command_receipts,
  skill_user_settings`); err != nil {
		t.Fatalf("reset SkillUserSetting tables: %v", err)
	}
}
