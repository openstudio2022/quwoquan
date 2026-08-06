// spec_ref: specs/feature-tree/runtime/runtime-assistant/proactive-subscription-delivery/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/settings-audit/spec.md#gwt-001
// readiness_case: get-notification-settings-api
// readiness_case: get-privacy-settings-api
// readiness_case: resolve-assistant-delivery-policy-api
// readiness_case: get-call-settings-api
// readiness_case: get-appearance-settings-api
// readiness_case: update-notification-settings-api
// readiness_case: update-privacy-settings-api
// readiness_case: update-call-settings-api
// readiness_case: update-appearance-settings-api
package api_integration

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"quwoquan_service/runtime/operation"
	settingshttp "quwoquan_service/services/user-service/internal/account/user_settings/adapters/inbound/http"
	settingsapp "quwoquan_service/services/user-service/internal/account/user_settings/application"
	settingspersistence "quwoquan_service/services/user-service/internal/account/user_settings/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestUserSettingsPostgresCASNoopAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(ctx, pool, "settings-owner", "settings-persona"); err != nil {
			t.Fatal(err)
		}
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

		queries := settingsapp.NewUserSettingsQueryFacade(store)
		handler := settingshttp.NewHandler(facade, queries)
		mux := http.NewServeMux()
		handler.RegisterRoutes(mux)
		serve := func(method, path, operationID, body string) *httptest.ResponseRecorder {
			request := httptest.NewRequest(method, path, bytes.NewBufferString(body))
			request.Header.Set("Content-Type", "application/json")
			request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
				OperationID: operationID,
				RequestID:   "settings-http-request",
				TraceID:     "settings-http-trace",
				Actor:       operation.ActorContext{AccountID: "settings-owner"},
			}))
			response := httptest.NewRecorder()
			mux.ServeHTTP(response, request)
			return response
		}
		assertOK := func(name string, response *httptest.ResponseRecorder) {
			t.Helper()
			if response.Code != http.StatusOK {
				t.Fatalf("production %s status=%d body=%s", name, response.Code, response.Body.String())
			}
		}

		assertOK("UpdateNotificationSettings", serve(
			http.MethodPatch,
			"/user/settings/notifications",
			"user.UpdateNotificationSettings",
			`{"enablePush":true,"enableMarketing":false,"quietHoursStart":"22:30","quietHoursEnd":"07:00"}`,
		))
		assertOK("GetNotificationSettings", serve(
			http.MethodGet, "/user/settings/notifications", "user.GetNotificationSettings", "",
		))
		assertOK("UpdatePrivacySettings", serve(
			http.MethodPatch,
			"/user/settings/privacy",
			"user.UpdatePrivacySettings",
			`{"allowStrangerMsg":false,"profileVisibility":"friends","blockedKeywords":["spoiler"],"assistantEnabled":false}`,
		))
		assertOK("GetPrivacySettings", serve(
			http.MethodGet, "/user/settings/privacy", "user.GetPrivacySettings", "",
		))
		assertOK("ResolveAssistantDeliveryPolicy", serve(
			http.MethodGet,
			"/internal/user/accounts/settings-owner/assistant-delivery-policy",
			"user.ResolveAssistantDeliveryPolicy",
			"",
		))
		assertOK("UpdateCallSettings", serve(
			http.MethodPatch,
			"/user/settings/calls",
			"user.UpdateCallSettings",
			`{"defaultIncomingCallRingtoneId":"official.classic","allowCallerRingtoneOverride":false,"enableCallVibration":true,"enableGroupCallRing":false}`,
		))
		assertOK("GetCallSettings", serve(
			http.MethodGet, "/user/settings/calls", "user.GetCallSettings", "",
		))
		assertOK("UpdateAppearanceSettings", serve(
			http.MethodPatch,
			"/user/settings/appearance",
			"user.UpdateAppearanceSettings",
			`{"themeMode":"dark","fontSizePreset":"lg","applyScope":"all_accounts"}`,
		))
		assertOK("GetAppearanceSettings", serve(
			http.MethodGet, "/user/settings/appearance", "user.GetAppearanceSettings", "",
		))

		var finalVersion, finalEvents int
		if err := pool.QueryRow(ctx, `SELECT version FROM user_settings WHERE user_id=$1`, "settings-owner").Scan(&finalVersion); err != nil {
			t.Fatal(err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM user_settings_outbox WHERE aggregate_id=$1`, "settings-owner").Scan(&finalEvents); err != nil {
			t.Fatal(err)
		}
		if finalVersion != 5 || finalEvents != 5 {
			t.Fatalf("production UserSettings HTTP packet mismatch: version=%d outbox=%d", finalVersion, finalEvents)
		}
	})
}
