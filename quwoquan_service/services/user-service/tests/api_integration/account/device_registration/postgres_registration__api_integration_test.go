// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/device-token-register/spec.md#gwt-001
// readiness_case: upsert-device-push-endpoint-api
// readiness_case: remove-device-push-endpoint-api
// readiness_case: resolve-incoming-call-push-destinations-api
// readiness_case: resolve-push-endpoint-secret-api
// readiness_case: invalidate-device-push-endpoint-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	registrationhttp "quwoquan_service/services/user-service/internal/account/device_registration/adapters/inbound/http"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	registrationpersistence "quwoquan_service/services/user-service/internal/account/device_registration/infrastructure/persistence"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestDeviceRegistrationPostgresRefreshAndPushEndpointHTTP(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(ctx, pool, "device-owner", "device-persona"); err != nil {
			t.Fatal(err)
		}
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
		if err != nil || replayed.IdempotentReplay ||
			replayed.Registration.Version != first.Registration.Version+1 ||
			!replayed.Registration.LastActiveAt.After(first.Registration.LastActiveAt) {
			t.Fatalf("DeviceRegistration refresh drift: first=%+v refreshed=%+v err=%v", first, replayed, err)
		}
		var count int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM user_devices WHERE account_id=$1 AND device_id=$2`, command.AccountID, command.DeviceID).Scan(&count); err != nil || count != 1 {
			t.Fatalf("DeviceRegistration rows=%d err=%v", count, err)
		}

		queries := registrationapp.NewQueryFacade(
			store,
			store,
			personapersistence.NewOwnerReader(pool),
			cipher,
		)
		mux := http.NewServeMux()
		registrationhttp.NewHandler(facade, queries).RegisterRoutes(mux)
		accountPrincipal := rtauth.Principal{
			Claims: rtauth.Claims{TokenType: rtauth.TokenTypeAccess},
			Actor:  operation.ActorContext{AccountID: "device-owner"},
		}
		integrationPrincipal := func(scope string) rtauth.Principal {
			return rtauth.Principal{
				Claims: rtauth.Claims{Roles: []string{"service"}, Scope: scope},
				Actor: operation.ActorContext{
					AccountID: registrationapp.IntegrationServicePrincipal,
				},
			}
		}
		serve := func(request *http.Request, principal rtauth.Principal) *httptest.ResponseRecorder {
			request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
				OperationID: "device-registration-api-integration",
				RequestID:   "device-registration-api-integration",
				TraceID:     "device-registration-api-integration",
			}))
			request = request.WithContext(rtauth.WithPrincipal(request.Context(), principal))
			response := httptest.NewRecorder()
			mux.ServeHTTP(response, request)
			return response
		}

		upsert := func(kind, token string) string {
			request := httptest.NewRequest(
				http.MethodPut,
				"/user/devices/device-http/push-endpoints/"+kind,
				bytes.NewBufferString(`{"token":"`+token+`","appVersion":"1.0.0"}`),
			)
			request.Header.Set("Content-Type", "application/json")
			response := serve(request, accountPrincipal)
			if response.Code != http.StatusOK {
				t.Fatalf("production UpsertDevicePushEndpoint(%s) status=%d body=%s", kind, response.Code, response.Body.String())
			}
			var payload struct {
				EndpointRef string `json:"endpointRef"`
			}
			if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil || payload.EndpointRef == "" {
				t.Fatalf("decode endpoint ref: value=%+v err=%v", payload, err)
			}
			return payload.EndpointRef
		}

		fcmRef := upsert("fcm", "fcm-registration-token")
		apnsRef := upsert("apns_voip", "apns-voip-registration-token")

		destinationResponse := serve(
			httptest.NewRequest(
				http.MethodGet,
				"/internal/user/personas/device-persona/push-destinations",
				nil,
			),
			integrationPrincipal(registrationapp.PushDestinationReadScope),
		)
		if destinationResponse.Code != http.StatusOK ||
			!bytes.Contains(destinationResponse.Body.Bytes(), []byte(fcmRef)) ||
			!bytes.Contains(destinationResponse.Body.Bytes(), []byte(apnsRef)) ||
			bytes.Contains(destinationResponse.Body.Bytes(), []byte("registration-token")) {
			t.Fatalf("production ResolveIncomingCallPushDestinations status=%d body=%s", destinationResponse.Code, destinationResponse.Body.String())
		}

		secretResponse := serve(
			httptest.NewRequest(
				http.MethodGet,
				"/internal/user/push-endpoints/"+fcmRef+"/secret",
				nil,
			),
			integrationPrincipal(registrationapp.PushEndpointSecretReadScope),
		)
		if secretResponse.Code != http.StatusOK ||
			secretResponse.Header().Get("Cache-Control") != "no-store, max-age=0" ||
			!bytes.Contains(secretResponse.Body.Bytes(), []byte("fcm-registration-token")) {
			t.Fatalf("production ResolvePushEndpointSecret status=%d headers=%v body=%s", secretResponse.Code, secretResponse.Header(), secretResponse.Body.String())
		}

		invalidateRequest := httptest.NewRequest(
			http.MethodPost,
			"/internal/user/push-endpoints/"+fcmRef+"/invalidate",
			bytes.NewBufferString(`{"reason":"provider_unregistered"}`),
		)
		invalidateRequest.Header.Set("Content-Type", "application/json")
		invalidateResponse := serve(
			invalidateRequest,
			integrationPrincipal(registrationapp.PushEndpointInvalidateScope),
		)
		if invalidateResponse.Code != http.StatusOK {
			t.Fatalf("production InvalidateDevicePushEndpoint status=%d body=%s", invalidateResponse.Code, invalidateResponse.Body.String())
		}

		removeResponse := serve(
			httptest.NewRequest(
				http.MethodDelete,
				"/user/devices/device-http/push-endpoints/apns_voip",
				nil,
			),
			accountPrincipal,
		)
		if removeResponse.Code != http.StatusOK {
			t.Fatalf("production RemoveDevicePushEndpoint status=%d body=%s", removeResponse.Code, removeResponse.Body.String())
		}
		var inactiveCount int
		if err := pool.QueryRow(
			ctx,
			`SELECT COUNT(*) FROM device_push_endpoints WHERE endpoint_ref IN ($1,$2) AND status <> 'active'`,
			fcmRef,
			apnsRef,
		).Scan(&inactiveCount); err != nil || inactiveCount != 2 {
			t.Fatalf("production endpoint terminal states=%d err=%v", inactiveCount, err)
		}
	})
}
