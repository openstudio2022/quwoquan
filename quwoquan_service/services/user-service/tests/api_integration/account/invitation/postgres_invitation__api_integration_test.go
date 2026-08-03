package api_integration

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	invitationapp "quwoquan_service/services/user-service/internal/account/invitation/application"
	invitationpersistence "quwoquan_service/services/user-service/internal/account/invitation/infrastructure/persistence"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestInvitationPostgresLifecycleUsesPersonaAuthority(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(ctx, pool, "invitation-owner", "invitation-persona"); err != nil {
			t.Fatal(err)
		}
		store, err := invitationpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		facade, err := invitationapp.NewFacade(store, personapersistence.NewOwnerReader(pool))
		if err != nil {
			t.Fatal(err)
		}
		created, err := facade.Generate(ctx, "invitation-owner", "invitation-persona", "copy_link", "+8613800000000")
		if err != nil || created.LinkCode == "" {
			t.Fatalf("generate Invitation: value=%+v err=%v", created, err)
		}
		delivered, err := facade.GetByCode(ctx, created.LinkCode)
		if err != nil || delivered.Status != "delivered" {
			t.Fatalf("deliver Invitation: value=%+v err=%v", delivered, err)
		}
		var count int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM invite_records WHERE inviter_persona_id=$1`, "invitation-persona").Scan(&count); err != nil || count != 1 {
			t.Fatalf("Invitation rows=%d err=%v", count, err)
		}
	})
}
