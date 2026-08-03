package api_integration

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingpersistence "quwoquan_service/services/user-service/internal/account/credential_binding/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestCredentialBindingPostgresNaturalIdempotencyAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store, err := bindingpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		facade := bindingapp.NewCredentialCommandFacade(store)
		command := bindingapp.BindCredentialCommand{
			CredentialType: bindingmodel.CredentialTypePhone,
			CredentialKey:  "sha256:verified-phone-identity", DisplayLabel: "手机",
		}
		first, err := facade.BindVerifiedCredential(ctx, "binding-owner", command)
		if err != nil {
			t.Fatal(err)
		}
		replayed, err := facade.BindVerifiedCredential(ctx, "binding-owner", command)
		if err != nil || !replayed.IdempotentReplay || replayed.Version != first.Version {
			t.Fatalf("CredentialBinding replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var stateCount, eventCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM credential_bindings WHERE owner_id=$1`, "binding-owner").Scan(&stateCount); err != nil {
			t.Fatal(err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM credential_bindings_outbox WHERE aggregate_id IN (SELECT id FROM credential_bindings WHERE owner_id=$1)`, "binding-owner").Scan(&eventCount); err != nil {
			t.Fatal(err)
		}
		if stateCount != 1 || eventCount != 1 {
			t.Fatalf("CredentialBinding packet mismatch: state=%d outbox=%d", stateCount, eventCount)
		}
	})
}
