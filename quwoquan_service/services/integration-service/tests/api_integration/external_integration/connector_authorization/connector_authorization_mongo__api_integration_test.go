// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: start-connector-authorization-api
// readiness_case: get-connector-authorization-api
// readiness_case: complete-native-connector-authorization-api
// readiness_case: complete-oauth-connector-authorization-api
package connector_authorization_test

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	authorizationhttp "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/adapters/inbound/http"
	authorizationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/application"
	authorizationmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
	authorizationpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/persistence"
	authorizationreference "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/reference"
	definitionapp "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/application"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	definitionpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/infrastructure/persistence"
)

type trustedProofVerifier struct {
	now time.Time
}

func (verifier trustedProofVerifier) VerifyNative(
	_ context.Context,
	authorization authorizationmodel.Authorization,
	proofRef string,
) (authorizationmodel.VerifiedProof, error) {
	if proofRef != "protected-native-proof-ref" {
		return authorizationmodel.VerifiedProof{}, authorizationmodel.ErrNativeProofInvalid
	}
	expiresAt := verifier.now.Add(24 * time.Hour)
	return authorizationmodel.VerifiedProof{
		CredentialRef:       "protected://native/calendar/account-1",
		ProofDigest:         authorizationmodel.Hash(proofRef),
		GrantedCapabilities: append([]string(nil), authorization.RequestedCapabilities...),
		CredentialExpiresAt: &expiresAt,
	}, nil
}

func (verifier trustedProofVerifier) VerifyOAuth(
	_ context.Context,
	authorization authorizationmodel.Authorization,
	proofRef string,
) (authorizationmodel.VerifiedProof, error) {
	if proofRef != "protected-oauth-callback-ref" {
		return authorizationmodel.VerifiedProof{}, authorizationmodel.ErrOAuthCallbackInvalid
	}
	expiresAt := verifier.now.Add(24 * time.Hour)
	return authorizationmodel.VerifiedProof{
		CredentialRef:                "protected://oauth/calendar/account-1",
		ProviderAccountSubjectDigest: authorizationmodel.Hash("google-subject-account-1"),
		ProofDigest:                  authorizationmodel.Hash(proofRef),
		GrantedCapabilities:          append([]string(nil), authorization.RequestedCapabilities...),
		CredentialExpiresAt:          &expiresAt,
		OAuthVerification: &authorizationmodel.OAuthVerification{
			StateVerified:           true,
			NonceVerified:           true,
			PKCEVerified:            true,
			AccountSubjectVerified:  true,
			CapabilityProbeVerified: true,
		},
	}, nil
}

func TestConnectorAuthorizationMongoAtomicallyPersistsVerifiedGrantAndReplay(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "integration_connector_authorization")
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	now := time.Date(2026, time.August, 3, 12, 0, 0, 0, time.UTC)
	definitionStore := definitionpersistence.NewMongoStore(runtime.Database)
	authorizationStore := authorizationpersistence.NewMongoStore(runtime.Database)
	for name, ensure := range map[string]func(context.Context) error{
		"definition":    definitionStore.EnsureIndexes,
		"authorization": authorizationStore.EnsureIndexes,
	} {
		if err := ensure(startupCtx); err != nil {
			t.Fatalf("ensure %s indexes: %v", name, err)
		}
	}
	_, err = definitionapp.NewCommandFacade(definitionStore, func() time.Time { return now }).Publish(
		startupCtx,
		definitionmodel.PublishInput{
			IdempotencyKey: "publish-calendar",
			Definition: definitionmodel.Definition{
				ConnectorID:           "system_calendar",
				DisplayName:           "系统日历",
				Description:           "用户确认后创建日历事项",
				Capabilities:          []string{"calendar.event.create"},
				AuthorizationMode:     definitionmodel.AuthorizationDeviceNative,
				ConfirmationPolicy:    definitionmodel.ConfirmationUser,
				DataClassification:    "sensitive",
				SupportedSurfaceKinds: []string{"personal"},
				Status:                definitionmodel.StatusActive,
				ReleaseDigest:         "sha256:" + strings.Repeat("f", 64),
			},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	_, err = definitionapp.NewCommandFacade(definitionStore, func() time.Time { return now }).Publish(
		startupCtx,
		definitionmodel.PublishInput{
			IdempotencyKey: "publish-oauth-calendar",
			Definition: definitionmodel.Definition{
				ConnectorID:           "oauth_calendar",
				DisplayName:           "OAuth 日历",
				Description:           "受信 OAuth callback 完成后创建日历事项",
				Capabilities:          []string{"calendar.event.create"},
				AuthorizationMode:     definitionmodel.AuthorizationOAuth2,
				ConfirmationPolicy:    definitionmodel.ConfirmationUser,
				DataClassification:    "sensitive",
				SupportedSurfaceKinds: []string{"personal"},
				Status:                definitionmodel.StatusActive,
				ReleaseDigest:         "sha256:" + strings.Repeat("e", 64),
			},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	commands := authorizationapp.NewCommandFacade(
		authorizationStore,
		definitionStore,
		authorizationreference.NewIssuer(nil),
		trustedProofVerifier{now: now},
		func() time.Time { return now },
		func() string { return "authorization-1" },
	)
	started, err := commands.Start(startupCtx, authorizationmodel.StartInput{
		AccountID:             "account-1",
		ConnectorID:           "system_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		IdempotencyKey:        "start-calendar",
	})
	if err != nil || started.Authorization.Revision != 1 || started.ContinuationRef == "" {
		t.Fatalf("start failed: result=%+v err=%v", started, err)
	}
	completed, err := commands.CompleteNative(startupCtx, authorizationmodel.CompleteInput{
		AccountID:        "account-1",
		AuthorizationID:  started.Authorization.AuthorizationID,
		ExpectedRevision: 1,
		ProofRef:         "protected-native-proof-ref",
		IdempotencyKey:   "complete-calendar",
	})
	if err != nil || completed.Authorization.Status != authorizationmodel.StatusVerified ||
		completed.Authorization.Revision != 2 || completed.GrantReceiptRef == "" {
		t.Fatalf("complete failed: result=%+v err=%v", completed, err)
	}
	replay, err := commands.CompleteNative(startupCtx, authorizationmodel.CompleteInput{
		AccountID:        "account-1",
		AuthorizationID:  started.Authorization.AuthorizationID,
		ExpectedRevision: 1,
		ProofRef:         "protected-native-proof-ref",
		IdempotencyKey:   "complete-calendar",
	})
	if err != nil || !replay.Replayed || replay.GrantReceiptRef != completed.GrantReceiptRef {
		t.Fatalf("completion replay failed: result=%+v err=%v", replay, err)
	}
	for collection, want := range map[string]int64{
		"connector_authorizations":                 1,
		"connector_authorization_command_receipts": 2,
		"connector_authorization_grant_receipts":   1,
		"connector_authorization_outbox":           2,
	} {
		count, countErr := runtime.Database.Collection(collection).CountDocuments(startupCtx, bson.M{})
		if countErr != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, countErr)
		}
	}
	var persisted bson.M
	if err := runtime.Database.Collection("connector_authorizations").FindOne(
		startupCtx, bson.M{"authorizationId": "authorization-1"},
	).Decode(&persisted); err != nil {
		t.Fatal(err)
	}
	encoded, err := bson.MarshalExtJSON(persisted, false, false)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{
		started.ContinuationRef,
		completed.GrantReceiptRef,
		"protected-native-proof-ref",
	} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("authoritative document leaked raw protected reference: %s", encoded)
		}
	}

	httpCommands := authorizationapp.NewCommandFacade(
		authorizationStore,
		definitionStore,
		authorizationreference.NewIssuer(nil),
		trustedProofVerifier{now: now},
		func() time.Time { return now },
		func() string { return "authorization-http-1" },
	)
	mux := http.NewServeMux()
	authorizationhttp.NewHandler(
		httpCommands,
		authorizationapp.NewQueryFacade(authorizationStore),
	).RegisterRoutes(mux)
	status, startBody := performConnectorAuthorizationRequest(
		t,
		mux,
		http.MethodPost,
		"/integrations/connector-authorizations",
		map[string]any{
			"connectorId":           "system_calendar",
			"requestedCapabilities": []string{"calendar.event.create"},
		},
		accountPrincipal(),
		"start-http-calendar",
	)
	if status != http.StatusOK {
		t.Fatalf("start route status=%d body=%#v", status, startBody)
	}
	status, getBody := performConnectorAuthorizationRequest(
		t,
		mux,
		http.MethodGet,
		"/integrations/connector-authorizations/authorization-http-1",
		nil,
		accountPrincipal(),
		"",
	)
	if status != http.StatusOK || getBody["authorizationId"] != "authorization-http-1" ||
		getBody["status"] != authorizationmodel.StatusPending {
		t.Fatalf("get route status=%d body=%#v", status, getBody)
	}
	status, completeBody := performConnectorAuthorizationRequest(
		t,
		mux,
		http.MethodPost,
		"/integrations/connector-authorizations/authorization-http-1/complete-native",
		map[string]any{
			"expectedRevision":    1,
			"nativeGrantProofRef": "protected-native-proof-ref",
		},
		accountPrincipal(),
		"complete-http-calendar",
	)
	completedAuthorization, _ := completeBody["authorization"].(map[string]any)
	if status != http.StatusOK ||
		completedAuthorization["authorizationId"] != "authorization-http-1" ||
		completedAuthorization["status"] != authorizationmodel.StatusVerified ||
		strings.TrimSpace(fmt.Sprint(completeBody["grantReceiptRef"])) == "" {
		t.Fatalf("complete-native route status=%d body=%#v", status, completeBody)
	}

	oauthCommands := authorizationapp.NewCommandFacade(
		authorizationStore,
		definitionStore,
		authorizationreference.NewIssuer(nil),
		trustedProofVerifier{now: now},
		func() time.Time { return now },
		func() string { return "authorization-oauth-http-1" },
	)
	oauthMux := http.NewServeMux()
	authorizationhttp.NewHandler(
		oauthCommands,
		authorizationapp.NewQueryFacade(authorizationStore),
	).RegisterRoutes(oauthMux)
	status, oauthStartBody := performConnectorAuthorizationRequest(
		t,
		oauthMux,
		http.MethodPost,
		"/integrations/connector-authorizations",
		map[string]any{
			"connectorId":           "oauth_calendar",
			"requestedCapabilities": []string{"calendar.event.create"},
		},
		accountPrincipal(),
		"start-http-oauth-calendar",
	)
	oauthStartAuthorization, _ := oauthStartBody["authorization"].(map[string]any)
	if status != http.StatusOK ||
		oauthStartAuthorization["authorizationId"] != "authorization-oauth-http-1" {
		t.Fatalf("start OAuth route status=%d body=%#v", status, oauthStartBody)
	}
	status, attackBody := performConnectorAuthorizationRequest(
		t,
		oauthMux,
		http.MethodPost,
		"/internal/integrations/connector-authorizations/authorization-oauth-http-1/complete-oauth",
		map[string]any{
			"accountId":        "attacker-account",
			"expectedRevision": 1,
			"oauthCallbackRef": "protected-oauth-callback-ref",
		},
		oauthCallbackServicePrincipal(),
		"complete-http-oauth-account-injection",
	)
	if status != http.StatusBadRequest {
		t.Fatalf("OAuth body accountId must not grant authority: status=%d body=%#v", status, attackBody)
	}
	status, oauthCompleteBody := performConnectorAuthorizationRequest(
		t,
		oauthMux,
		http.MethodPost,
		"/internal/integrations/connector-authorizations/authorization-oauth-http-1/complete-oauth",
		map[string]any{
			"expectedRevision": 1,
			"oauthCallbackRef": "protected-oauth-callback-ref",
		},
		oauthCallbackServicePrincipal(),
		"complete-http-oauth-calendar",
	)
	oauthAuthorization, _ := oauthCompleteBody["authorization"].(map[string]any)
	if status != http.StatusOK ||
		oauthAuthorization["authorizationId"] != "authorization-oauth-http-1" ||
		oauthAuthorization["status"] != authorizationmodel.StatusVerified ||
		strings.TrimSpace(fmt.Sprint(oauthCompleteBody["grantReceiptRef"])) == "" {
		t.Fatalf("complete-oauth route status=%d body=%#v", status, oauthCompleteBody)
	}
}

func accountPrincipal() *rtauth.Principal {
	return &rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "account-1"},
	}
}

// oauthCallbackServicePrincipal 匹配契约 authorization 段：complete-oauth 内部
// 路由要求 service principal 且携带 integration.connector_oauth_callback.write。
func oauthCallbackServicePrincipal() *rtauth.Principal {
	return &rtauth.Principal{
		Claims: rtauth.Claims{
			Scope: "integration.connector_oauth_callback.write",
			Roles: []string{"service"},
		},
		Actor: operation.ActorContext{
			AccountID: "service:integration-oauth-callback",
		},
	}
}

func performConnectorAuthorizationRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body any,
	principal *rtauth.Principal,
	idempotencyKey string,
) (int, map[string]any) {
	t.Helper()
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("encode connector authorization request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	if principal != nil {
		request = request.WithContext(
			rtauth.WithPrincipal(request.Context(), *principal),
		)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	decoded := map[string]any{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &decoded); err != nil {
		t.Fatalf("decode connector authorization response status=%d body=%q: %v", recorder.Code, recorder.Body.String(), err)
	}
	return recorder.Code, decoded
}
