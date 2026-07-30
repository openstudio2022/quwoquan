package api_integration

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	testsupport "quwoquan_service/services/product-ops-service/tests/support"
	userapisupport "quwoquan_service/services/user-service/tests/support"
)

var accountEnforcementPGPool *pgxpool.Pool
var accountEnforcementUserRuntime *userapisupport.AccountEnforcementRuntime

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
	accountEnforcementPGPool, err = pgxpool.New(ctx, dsn)
	if err != nil {
		panic("connect PostgreSQL: " + err.Error())
	}
	if err := accountEnforcementPGPool.Ping(ctx); err != nil {
		panic("ping PostgreSQL: " + err.Error())
	}
	accountEnforcementUserRuntime, err =
		userapisupport.StartAccountEnforcementRuntime(ctx, accountEnforcementPGPool)
	if err != nil {
		panic("start real UserAccount enforcement HTTP runtime: " + err.Error())
	}
	code := m.Run()
	accountEnforcementUserRuntime.Close()
	accountEnforcementPGPool.Close()
	if err := embedded.Stop(); err != nil {
		panic(err)
	}
	os.Exit(code)
}
