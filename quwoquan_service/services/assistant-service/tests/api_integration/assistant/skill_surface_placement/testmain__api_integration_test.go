package api_integration

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/internal/platform/testinfra"
	placementpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/persistence"
)

var (
	placementPool  *pgxpool.Pool
	placementStore *placementpersistence.PgStore
)

func TestMain(m *testing.M) {
	fixtureRoot, err := os.MkdirTemp("", "qwq-assistant-skill-placement-pg-")
	if err != nil {
		panic(fmt.Sprintf("create SkillSurfacePlacement PostgreSQL root: %v", err))
	}
	fixture, err := testinfra.StartPostgresFixture(fixtureRoot, 0)
	if err != nil {
		_ = os.RemoveAll(fixtureRoot)
		panic(fmt.Sprintf("start SkillSurfacePlacement PostgreSQL: %v", err))
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	placementPool, err = pgxpool.New(ctx, fixture.DSN())
	if err == nil {
		err = placementPool.Ping(ctx)
	}
	if err == nil {
		placementStore = placementpersistence.NewPgStore(placementPool)
		err = placementStore.EnsureSchema(ctx)
	}
	cancel()
	if err != nil {
		if placementPool != nil {
			placementPool.Close()
		}
		_ = fixture.Close()
		_ = os.RemoveAll(fixtureRoot)
		panic(fmt.Sprintf("initialize SkillSurfacePlacement PostgreSQL: %v", err))
	}

	exitCode := m.Run()
	placementPool.Close()
	if closeErr := fixture.Close(); closeErr != nil {
		fmt.Fprintf(os.Stderr, "close SkillSurfacePlacement PostgreSQL: %v\n", closeErr)
		exitCode = 1
	}
	if removeErr := os.RemoveAll(fixtureRoot); removeErr != nil {
		fmt.Fprintf(os.Stderr, "remove SkillSurfacePlacement PostgreSQL root: %v\n", removeErr)
		exitCode = 1
	}
	os.Exit(exitCode)
}

func resetPlacementState(t *testing.T) {
	t.Helper()
	if _, err := placementPool.Exec(context.Background(), `
TRUNCATE TABLE skill_surface_placement_outbox,
  skill_surface_placement_command_receipts,
  skill_surface_placements`); err != nil {
		t.Fatalf("reset SkillSurfacePlacement tables: %v", err)
	}
}
