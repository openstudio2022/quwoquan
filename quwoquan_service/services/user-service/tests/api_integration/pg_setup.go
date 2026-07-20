package api_integration

import (
	"context"
	"fmt"
	"net"
	"os"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
)

var embeddedPG *embeddedpostgres.EmbeddedPostgres
var embeddedPGRuntimePath string

func startEmbeddedPostgres() string {
	port := reserveEmbeddedPostgresPort()
	runtimePath, err := os.MkdirTemp("", "quwoquan-user-api-postgres-*")
	if err != nil {
		panic("embedded-postgres runtime: " + err.Error())
	}
	embeddedPGRuntimePath = runtimePath
	// Use the 'postgres' default database to avoid embedded-postgres PG-18 custom DB creation issue.
	dsn := fmt.Sprintf("postgres://postgres:postgres@localhost:%d/postgres?sslmode=disable", port)

	embeddedPG = embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Version(testinfra.StableEmbeddedPostgresVersion).
			Port(port).
			RuntimePath(runtimePath).
			Username("postgres").
			Password("postgres"),
	)
	if err := embeddedPG.Start(); err != nil {
		_ = os.RemoveAll(runtimePath)
		panic("embedded-postgres start: " + err.Error())
	}
	return dsn
}

func reserveEmbeddedPostgresPort() uint32 {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		panic("reserve embedded-postgres port: " + err.Error())
	}
	defer listener.Close()
	address, ok := listener.Addr().(*net.TCPAddr)
	if !ok {
		panic(fmt.Sprintf("unexpected embedded-postgres listener address %T", listener.Addr()))
	}
	return uint32(address.Port)
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
