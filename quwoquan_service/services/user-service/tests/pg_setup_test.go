package tests

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
	"github.com/jackc/pgx/v5/pgxpool"
)

var embeddedPG *embeddedpostgres.EmbeddedPostgres

func startEmbeddedPostgres() string {
	port := uint32(15433)
	// Use the 'postgres' default database to avoid embedded-postgres PG-18 custom DB creation issue.
	dsn := fmt.Sprintf("postgres://postgres:postgres@localhost:%d/postgres?sslmode=disable", port)

	embeddedPG = embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Version(embeddedpostgres.V16).
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
	dirs := []string{
		"internal/infrastructure/migration",
		"../internal/infrastructure/migration",
		"../services/user-service/internal/infrastructure/migration",
		"services/user-service/internal/infrastructure/migration",
	}
	var migrationDir string
	for _, d := range dirs {
		if _, err := os.Stat(d); err == nil {
			migrationDir = d
			break
		}
	}
	if migrationDir == "" {
		panic("migration directory not found")
	}
	entries, err := os.ReadDir(migrationDir)
	if err != nil {
		panic("read migration dir: " + err.Error())
	}
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Name() < entries[j].Name()
	})
	for _, entry := range entries {
		if !strings.HasSuffix(entry.Name(), ".up.sql") {
			continue
		}
		content, err := os.ReadFile(filepath.Join(migrationDir, entry.Name()))
		if err != nil {
			panic("read " + entry.Name() + ": " + err.Error())
		}
		if _, err := pool.Exec(ctx, string(content)); err != nil {
			panic("execute " + entry.Name() + ": " + err.Error())
		}
	}
}
