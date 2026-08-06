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

var controlPlanePGPool *pgxpool.Pool

func TestMain(m *testing.M) {
	// Focused object HTTP runners that exclusively assemble explicit in-memory
	// ports must not require the unrelated control-plane PostgreSQL fixture.
	// The default full package path still provisions and verifies PostgreSQL.
	if strings.TrimSpace(os.Getenv("QWQ_EVENT_RECORD_IN_MEMORY_ONLY")) == "1" {
		os.Exit(m.Run())
	}
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
	controlPlanePGPool, err = pgxpool.New(ctx, dsn)
	if err != nil {
		panic("connect PostgreSQL: " + err.Error())
	}
	if err := controlPlanePGPool.Ping(ctx); err != nil {
		panic("ping PostgreSQL: " + err.Error())
	}
	code := m.Run()
	controlPlanePGPool.Close()
	if err := embedded.Stop(); err != nil {
		panic(err)
	}
	os.Exit(code)
}
