package api_integration

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	registrationpersistence "quwoquan_service/services/user-service/internal/account/device_registration/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestDeviceRegistrationPostgresNaturalReplay(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store, err := registrationpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		cipher, err := registrationpersistence.NewAESGCMTokenCipher([]byte("0123456789abcdef0123456789abcdef"))
		if err != nil {
			t.Fatal(err)
		}
		facade := registrationapp.NewCommandFacade(store, cipher)
		command := registrationapp.RegisterCommand{AccountID: "device-owner", DeviceID: "device-a", AppVersion: "1.0.0"}
		first, err := facade.Register(ctx, command)
		if err != nil {
			t.Fatal(err)
		}
		replayed, err := facade.Register(ctx, command)
		if err != nil || !replayed.IdempotentReplay || replayed.Registration.Version != first.Registration.Version {
			t.Fatalf("DeviceRegistration replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var count int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM user_devices WHERE account_id=$1 AND device_id=$2`, command.AccountID, command.DeviceID).Scan(&count); err != nil || count != 1 {
			t.Fatalf("DeviceRegistration rows=%d err=%v", count, err)
		}
	})
}
