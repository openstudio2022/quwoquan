package api_integration

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	testsupport "quwoquan_service/services/product-ops-service/tests/support"
)

var assignmentPGPool *pgxpool.Pool

func TestMain(m *testing.M) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	dsn := strings.TrimSpace(os.Getenv("QWQ_TEST_POSTGRES_DSN"))
	if dsn == "" {
		dsn = strings.TrimSpace(os.Getenv("TEST_PG_DSN"))
	}
	var embedded *testsupport.EmbeddedPostgres
	if dsn == "" {
		var err error
		embedded, dsn, err = testsupport.StartEmbeddedPostgres()
		if err != nil {
			panic(err)
		}
	}
	var err error
	assignmentPGPool, err = pgxpool.New(ctx, dsn)
	if err != nil {
		panic("connect PostgreSQL: " + err.Error())
	}
	if err := assignmentPGPool.Ping(ctx); err != nil {
		panic("ping PostgreSQL: " + err.Error())
	}
	code := m.Run()
	assignmentPGPool.Close()
	if embedded != nil {
		if err := embedded.Stop(); err != nil {
			panic(err)
		}
	}
	os.Exit(code)
}
