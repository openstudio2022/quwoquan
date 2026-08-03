package api_integration

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestPersonaProfileProposalPostgresCommitAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(ctx, pool, "persona-owner", "persona-object"); err != nil {
			t.Fatal(err)
		}
		store, err := personapersistence.NewProfileProposalPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		facade, err := personaapp.NewProfileProposalFacade(store)
		if err != nil {
			t.Fatal(err)
		}
		displayName := "归属 Persona 的新名称"
		result, err := facade.ApplyProfileProposal(ctx, personaports.ApplyProfileProposalCommand{
			ProposalID: "persona-proposal-1", PersonaID: "persona-object", ExpectedPersonaVersion: 1,
			Changes: personamodel.ProfileChangeSet{DisplayName: &displayName},
		})
		if err != nil || result.After.DisplayName != displayName || result.After.Version != 2 {
			t.Fatalf("apply Persona profile proposal: result=%+v err=%v", result, err)
		}
		var events int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM personas_outbox WHERE aggregate_id=$1`, "persona-object").Scan(&events); err != nil || events != 1 {
			t.Fatalf("Persona outbox=%d err=%v", events, err)
		}
	})
}
