package tests

import (
	"context"
	"fmt"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/runtime/testinfra"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
)

var embeddedPG *embeddedpostgres.EmbeddedPostgres

func startEmbeddedPostgres() string {
	port := uint32(15433)
	// Use the 'postgres' default database to avoid embedded-postgres PG-18 custom DB creation issue.
	dsn := fmt.Sprintf("postgres://postgres:postgres@localhost:%d/postgres?sslmode=disable", port)

	embeddedPG = embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Version(testinfra.StableEmbeddedPostgresVersion).
			Port(port).
			Username("postgres").
			Password("postgres"),
	)
	if err := embeddedPG.Start(); err != nil {
		panic("embedded-postgres start: " + err.Error())
	}
	return dsn
}

func runTestMigrations(ctx context.Context, pool *pgxpool.Pool) {
	// Reset schema for clean migration run.
	if _, err := pool.Exec(ctx, "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO postgres;"); err != nil {
		panic("reset schema: " + err.Error())
	}
	if err := persistence.RunManagedMigrations(ctx, pool); err != nil {
		panic("run managed migrations: " + err.Error())
	}
}
