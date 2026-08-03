package api_integration

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"quwoquan_service/runtime/operation"
	settingsapp "quwoquan_service/services/user-service/internal/account/user_settings/application"
	settingspersistence "quwoquan_service/services/user-service/internal/account/user_settings/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestUserSettingsPostgresCASNoopAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store, err := settingspersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		facade := settingsapp.NewUserSettingsCommandFacade(store)
		ctx = operation.WithContext(ctx, operation.Context{
			OperationID: "user.UpdateNotificationSettings", RequestID: "settings-request", TraceID: "settings-trace",
			Actor: operation.ActorContext{AccountID: "settings-owner"},
		})
		command := settingsapp.UpdateNotificationSettingsCommand{EnablePush: settingsapp.Set(false)}
		first, err := facade.UpdateNotificationSettings(ctx, command)
		if err != nil {
			t.Fatal(err)
		}
		replayed, err := facade.UpdateNotificationSettings(ctx, command)
		if err != nil || !replayed.IdempotentReplay || replayed.Version != first.Version {
			t.Fatalf("UserSettings replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var stateVersion, events int
		if err := pool.QueryRow(ctx, `SELECT version FROM user_settings WHERE user_id=$1`, "settings-owner").Scan(&stateVersion); err != nil {
			t.Fatal(err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM user_settings_outbox WHERE aggregate_id=$1`, "settings-owner").Scan(&events); err != nil {
			t.Fatal(err)
		}
		if stateVersion != 1 || events != 1 {
			t.Fatalf("UserSettings packet mismatch: version=%d outbox=%d", stateVersion, events)
		}
	})
}
