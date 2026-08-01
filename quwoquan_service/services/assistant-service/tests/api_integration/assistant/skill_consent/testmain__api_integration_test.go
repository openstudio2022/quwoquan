package api_integration

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/internal/platform/testinfra"
	consentpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/infrastructure/persistence"
)

var (
	skillConsentPool  *pgxpool.Pool
	skillConsentStore *consentpersistence.PgStore
)

func TestMain(m *testing.M) {
	fixtureRoot, err := os.MkdirTemp("", "qwq-assistant-skill-consent-pg-")
	if err != nil {
		panic(fmt.Sprintf("create SkillConsent PostgreSQL root: %v", err))
	}
	fixture, err := testinfra.StartPostgresFixture(fixtureRoot, 0)
	if err != nil {
		_ = os.RemoveAll(fixtureRoot)
		panic(fmt.Sprintf("start SkillConsent PostgreSQL: %v", err))
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	skillConsentPool, err = pgxpool.New(ctx, fixture.DSN())
	if err == nil {
		err = skillConsentPool.Ping(ctx)
	}
	if err == nil {
		skillConsentStore = consentpersistence.NewPgStore(skillConsentPool)
		err = skillConsentStore.EnsureSchema(ctx)
	}
	cancel()
	if err != nil {
		if skillConsentPool != nil {
			skillConsentPool.Close()
		}
		_ = fixture.Close()
		_ = os.RemoveAll(fixtureRoot)
		panic(fmt.Sprintf("initialize SkillConsent PostgreSQL: %v", err))
	}

	exitCode := m.Run()
	skillConsentPool.Close()
	if closeErr := fixture.Close(); closeErr != nil {
		fmt.Fprintf(os.Stderr, "close SkillConsent PostgreSQL: %v\n", closeErr)
		exitCode = 1
	}
	if removeErr := os.RemoveAll(fixtureRoot); removeErr != nil {
		fmt.Fprintf(os.Stderr, "remove SkillConsent PostgreSQL root: %v\n", removeErr)
		exitCode = 1
	}
	os.Exit(exitCode)
}

func resetSkillConsentState(t *testing.T) {
	t.Helper()
	if _, err := skillConsentPool.Exec(
		context.Background(),
		`TRUNCATE TABLE skill_consent_events, skill_consent_command_receipts, skill_consents`,
	); err != nil {
		t.Fatalf("reset SkillConsent tables: %v", err)
	}
}
