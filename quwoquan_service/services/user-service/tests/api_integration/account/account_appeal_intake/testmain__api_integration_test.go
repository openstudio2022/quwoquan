package api_integration

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/internal/platform/testinfra"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

var appealIntakePGPool *pgxpool.Pool

func TestMain(m *testing.M) {
	fixtureRoot, err := os.MkdirTemp("", "qwq-user-account-appeal-pg-")
	if err != nil {
		panic(fmt.Sprintf("create AccountAppealIntake PostgreSQL root: %v", err))
	}
	fixture, err := testinfra.StartPostgresFixture(fixtureRoot, 0)
	if err != nil {
		_ = os.RemoveAll(fixtureRoot)
		panic(fmt.Sprintf("start AccountAppealIntake PostgreSQL: %v", err))
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	appealIntakePGPool, err = pgxpool.New(ctx, fixture.DSN())
	if err == nil {
		err = appealIntakePGPool.Ping(ctx)
	}
	if err == nil {
		err = useraccountpersistence.RunManagedMigrations(ctx, appealIntakePGPool)
	}
	cancel()
	if err != nil {
		if appealIntakePGPool != nil {
			appealIntakePGPool.Close()
		}
		_ = fixture.Close()
		panic(fmt.Sprintf("initialize AccountAppealIntake PostgreSQL: %v", err))
	}

	exitCode := m.Run()
	appealIntakePGPool.Close()
	if closeErr := fixture.Close(); closeErr != nil {
		fmt.Fprintf(os.Stderr, "close AccountAppealIntake PostgreSQL: %v\n", closeErr)
		exitCode = 1
	}
	os.Exit(exitCode)
}
