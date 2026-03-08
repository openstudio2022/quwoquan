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
	dsn := fmt.Sprintf("postgres://postgres:postgres@localhost:%d/user_test?sslmode=disable", port)

	embeddedPG = embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Port(port).
			Database("user_test").
			Username("postgres").
			Password("postgres"),
	)
	if err := embeddedPG.Start(); err != nil {
		panic("embedded-postgres start: " + err.Error())
	}
	return dsn
}

func runTestMigrations(ctx context.Context, pool *pgxpool.Pool) {
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
