// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-003
// readiness_case: list-connector-connections-api
// readiness_case: get-connector-connection-api
// readiness_case: create-connector-connection-api
// readiness_case: revoke-connector-connection-api
// readiness_case: resolve-connector-capability-grant-api
package connector_connection_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rtredis "quwoquan_service/runtime/redis"
	grantadapter "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/adapters/inbound/runtime"
	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	grantcandidate "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/candidate"
	grantpersistence "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/persistence"
	grantresolver "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/resolver"
	authorizationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/application"
	authorizationmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
	connectorgrant "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/grantreceipt"
	authorizationpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/persistence"
	authorizationreference "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/reference"
	connectionhttp "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/adapters/inbound/http"
	connectionapp "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/application"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	connectionpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/infrastructure/persistence"
	definitionapp "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/application"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	definitionpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/infrastructure/persistence"
)

type trustedNativeProofVerifier struct {
	now time.Time
}

func (verifier trustedNativeProofVerifier) VerifyNative(
	_ context.Context,
	authorization authorizationmodel.Authorization,
	proofRef string,
) (authorizationmodel.VerifiedProof, error) {
	if proofRef != "protected-native-proof-ref" {
		return authorizationmodel.VerifiedProof{}, authorizationmodel.ErrNativeProofInvalid
	}
	expiresAt := verifier.now.Add(24 * time.Hour)
	return authorizationmodel.VerifiedProof{
		CredentialRef:                "protected://native/calendar/account-1",
		ProviderAccountSubjectDigest: authorizationmodel.Hash("native-calendar-account-1"),
		ProofDigest:                  authorizationmodel.Hash(proofRef),
		GrantedCapabilities:          append([]string(nil), authorization.RequestedCapabilities...),
		CredentialExpiresAt:          &expiresAt,
	}, nil
}

func (trustedNativeProofVerifier) VerifyOAuth(
	context.Context,
	authorizationmodel.Authorization,
	string,
) (authorizationmodel.VerifiedProof, error) {
	return authorizationmodel.VerifiedProof{}, authorizationmodel.ErrOAuthCallbackInvalid
}

func TestConnectorConnectionMongoCreatesReplaysAndRevokesWithoutLeakingCredential(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "integration_connector_connection")
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

	now := time.Date(2026, time.August, 2, 12, 0, 0, 0, time.UTC)
	redisRuntime, err := testinfra.StartRealRedis(startupCtx)
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := redisRuntime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
	})
	if err := redisRuntime.FlushDBs(startupCtx, 0); err != nil {
		t.Fatalf("flush real Redis: %v", err)
	}
	redisRouter, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode: "standalone", Addr: redisRuntime.Addr,
				Password: redisRuntime.Password, DB: 0, TLS: redisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		t.Fatalf("new Redis router: %v", err)
	}
	t.Cleanup(func() { _ = redisRouter.Close() })
	definitionStore := definitionpersistence.NewMongoStore(runtime.Database)
	authorizationStore := authorizationpersistence.NewMongoStore(runtime.Database)
	connectionStore := connectionpersistence.NewMongoStore(runtime.Database, authorizationStore)
	grantVerifier := connectorgrant.NewMongoVerifier(runtime.Database, func() time.Time { return now })
	for name, ensure := range map[string]func(context.Context) error{
		"definition":    definitionStore.EnsureIndexes,
		"authorization": authorizationStore.EnsureIndexes,
		"connection":    connectionStore.EnsureIndexes,
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
				ConnectorID: "system_calendar", DisplayName: "系统日历",
				Description:        "用户确认后创建日历事项",
				Capabilities:       []string{"calendar.event.create"},
				AuthorizationMode:  definitionmodel.AuthorizationDeviceNative,
				ConfirmationPolicy: definitionmodel.ConfirmationUser,
				DataClassification: "sensitive", SupportedSurfaceKinds: []string{"personal"},
				Status:        definitionmodel.StatusActive,
				ReleaseDigest: "sha256:" + strings.Repeat("f", 64),
			},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	authorizationCommands := authorizationapp.NewCommandFacade(
		authorizationStore,
		definitionStore,
		authorizationreference.NewIssuer(nil),
		trustedNativeProofVerifier{now: now},
		func() time.Time { return now },
		func() string { return "authorization-connection-1" },
	)
	started, err := authorizationCommands.Start(startupCtx, authorizationmodel.StartInput{
		AccountID:             "account-1",
		ConnectorID:           "system_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		IdempotencyKey:        "start-calendar",
	})
	if err != nil {
		t.Fatal(err)
	}
	verified, err := authorizationCommands.CompleteNative(startupCtx, authorizationmodel.CompleteInput{
		AccountID:        "account-1",
		AuthorizationID:  started.Authorization.AuthorizationID,
		ExpectedRevision: 1,
		ProofRef:         "protected-native-proof-ref",
		IdempotencyKey:   "complete-calendar",
	})
	if err != nil {
		t.Fatal(err)
	}
	commands := connectionapp.NewCommandFacade(
		connectionStore, definitionStore, grantVerifier, func() time.Time { return now },
	)
	grantStore, err := grantpersistence.NewRedisSessionStore(
		redisRouter.Scene("general"),
	)
	if err != nil {
		t.Fatal(err)
	}
	assertCapabilityGrantTTLDoesNotRenew(
		t,
		startupCtx,
		redisRuntime,
		grantStore,
		now,
	)
	unavailable := grantcandidate.NewUnavailableSources("not bound in connector API runner")
	grantResolver := grantresolver.NewCandidateResolver(
		unavailable,
		grantcandidate.NewConnectorReaderSource(
			connectionStore,
			definitionStore,
			func() time.Time { return now },
		),
		unavailable,
		unavailable,
		func() time.Time { return now },
	)
	queries := connectionapp.NewCapabilityQueryFacade(
		connectionStore,
		grantadapter.NewMiddleware(
			grantapp.NewCapabilityGrantSessionFacade(grantResolver, grantStore),
		),
	)
	mux := http.NewServeMux()
	connectionhttp.NewHandler(commands, queries).RegisterRoutes(mux)
	create := connectionmodel.CreateInput{
		AccountID: "account-1", ConnectorID: "system_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		GrantReceiptRef:       verified.GrantReceiptRef, IdempotencyKey: "connect-calendar",
	}
	status, createBody := performConnectorConnectionRequest(
		t,
		mux,
		http.MethodPost,
		"/integrations/connections",
		map[string]any{
			"connectorId":           create.ConnectorID,
			"requestedCapabilities": create.RequestedCapabilities,
			"grantReceiptRef":       create.GrantReceiptRef,
		},
		true,
		create.IdempotencyKey,
	)
	if status != http.StatusOK {
		t.Fatalf("create route status=%d body=%#v", status, createBody)
	}
	connections, err := connectionStore.List(startupCtx, "account-1", 10)
	if err != nil || len(connections) != 1 || connections[0].Revision != 1 {
		t.Fatalf("create route did not persist one connection: connections=%+v err=%v", connections, err)
	}
	created := connectionmodel.MutationResult{Connection: connections[0]}
	authorizationAfterCreate, err := authorizationStore.Get(
		startupCtx, "account-1", started.Authorization.AuthorizationID,
	)
	if err != nil || authorizationAfterCreate.Status != authorizationmodel.StatusConsumed {
		t.Fatalf("grant was not atomically consumed: authorization=%+v err=%v", authorizationAfterCreate, err)
	}
	replay, err := commands.Create(startupCtx, create)
	if err != nil || !replay.Replayed || replay.Connection.ConnectionID != created.Connection.ConnectionID {
		t.Fatalf("replay failed: result=%+v err=%v", replay, err)
	}
	encoded, err := json.Marshal(created.Connection)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), "protected://") || strings.Contains(string(encoded), "receiptDigest") {
		t.Fatalf("connection response leaked protected material: %s", encoded)
	}
	status, listBody := performConnectorConnectionRequest(
		t, mux, http.MethodGet, "/integrations/connections?limit=10", nil, true, "",
	)
	items, ok := listBody["items"].([]any)
	if status != http.StatusOK || !ok || len(items) != 1 {
		t.Fatalf("list route status=%d body=%#v", status, listBody)
	}
	status, getBody := performConnectorConnectionRequest(
		t, mux, http.MethodGet,
		"/integrations/connections/"+created.Connection.ConnectionID,
		nil, true, "",
	)
	if status != http.StatusOK || getBody["connectionId"] != created.Connection.ConnectionID {
		t.Fatalf("get route status=%d body=%#v", status, getBody)
	}
	status, resolveBody := performConnectorGrantResolutionRequest(
		t,
		mux,
		map[string]any{
			"capabilityKey":  "calendar.event.create",
			"surfaceKind":    "personal",
			"connectionRefs": []string{created.Connection.ConnectionID},
		},
	)
	if status != http.StatusOK || resolveBody["allowed"] != true ||
		resolveBody["connectionId"] != created.Connection.ConnectionID {
		t.Fatalf("resolve route status=%d body=%#v", status, resolveBody)
	}
	status, revokeBody := performConnectorConnectionRequest(
		t,
		mux,
		http.MethodPost,
		"/integrations/connections/"+created.Connection.ConnectionID+"/revoke",
		map[string]any{"expectedRevision": 1},
		true,
		"revoke-calendar",
	)
	if status != http.StatusOK {
		t.Fatalf("revoke route status=%d body=%#v", status, revokeBody)
	}
	revokedConnection, err := connectionStore.Get(
		startupCtx, "account-1", created.Connection.ConnectionID,
	)
	if err != nil || revokedConnection.Status != connectionmodel.StatusRevoked ||
		revokedConnection.Revision != 2 || revokedConnection.CredentialRef != "" {
		t.Fatalf("revoke failed closed incorrectly: connection=%+v err=%v", revokedConnection, err)
	}
	status, revokedGrantBody := performConnectorGrantResolutionRequest(
		t,
		mux,
		map[string]any{
			"capabilityKey":  "calendar.event.create",
			"surfaceKind":    "personal",
			"connectionRefs": []string{created.Connection.ConnectionID},
		},
	)
	if status != http.StatusOK || revokedGrantBody["allowed"] != false ||
		revokedGrantBody["reason"] != connectionmodel.CapabilityReasonConnectionInactive {
		t.Fatalf("revoked grant status=%d body=%#v", status, revokedGrantBody)
	}
	authorizationAfterRevoke, err := authorizationStore.Get(
		startupCtx, "account-1", started.Authorization.AuthorizationID,
	)
	if err != nil || authorizationAfterRevoke.Status != authorizationmodel.StatusRevoked ||
		authorizationAfterRevoke.CredentialRef != "" {
		t.Fatalf("authorization was not atomically revoked: authorization=%+v err=%v", authorizationAfterRevoke, err)
	}
	for collection, want := range map[string]int64{
		"connector_connections":                 1,
		"connector_connection_command_receipts": 2,
		"connector_connection_outbox":           2,
		"connector_authorization_outbox":        4,
	} {
		count, countErr := runtime.Database.Collection(collection).CountDocuments(startupCtx, bson.M{})
		if countErr != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, countErr)
		}
	}
	var auditEvents []bson.M
	cursor, err := runtime.Database.Collection("connector_connection_outbox").Find(
		startupCtx,
		bson.M{},
	)
	if err != nil || cursor.All(startupCtx, &auditEvents) != nil || len(auditEvents) != 2 {
		t.Fatalf("connection audit events=%#v err=%v", auditEvents, err)
	}
	for _, event := range auditEvents {
		if _, stale := event["publishedAt"]; stale {
			t.Fatalf("self-retained connection audit event has delivery checkpoint: %#v", event)
		}
	}
}

func assertCapabilityGrantTTLDoesNotRenew(
	t *testing.T,
	ctx context.Context,
	redisRuntime *testinfra.RealRedis,
	store *grantpersistence.RedisSessionStore,
	now time.Time,
) {
	t.Helper()
	expiresAt := now.Add(grantmodel.GrantTTL)
	grant := grantmodel.ResolvedCapabilityGrant{
		ResolutionID:  "ttl-session-1",
		CapabilityKey: "calendar.event.create",
		BindingKind:   grantmodel.BindingDomainOperation,
		DomainOperation: &grantmodel.DomainOperationBinding{
			OwnerOperationID: "content.post.CreatePost",
			ContractDigest:   authorizationmodel.Hash("create-post-contract"),
		},
		ResolvedAt: now,
		ExpiresAt:  &expiresAt,
	}
	if err := store.Save(ctx, grant); err != nil {
		t.Fatalf("save initial capability grant session: %v", err)
	}
	key := "integration:capability-grant:ttl-session-1"
	before, err := redisRuntime.TTL(ctx, 0, key)
	if err != nil || before <= 0 || before > grantmodel.GrantTTL {
		t.Fatalf("initial capability grant TTL=%s err=%v", before, err)
	}
	time.Sleep(1100 * time.Millisecond)
	if err := store.Save(ctx, grant); err != nil {
		t.Fatalf("idempotent capability grant save: %v", err)
	}
	after, err := redisRuntime.TTL(ctx, 0, key)
	if err != nil || after >= before {
		t.Fatalf("capability grant TTL renewed: before=%s after=%s err=%v", before, after, err)
	}
}

func performConnectorGrantResolutionRequest(
	t *testing.T,
	handler http.Handler,
	body any,
) (int, map[string]any) {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("encode connector grant request: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/integrations/connector-capability-grants:resolve",
		bytes.NewReader(payload),
	)
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{
			TokenType:      rtauth.TokenTypeAccess,
			Subject:        "account-1",
			ServiceActorID: "assistant-service",
			Scope:          "integration.connector_grant.read",
			Roles:          []string{"service"},
		},
		Actor: operation.ActorContext{AccountID: "account-1"},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	decoded := map[string]any{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &decoded); err != nil {
		t.Fatalf(
			"decode connector grant response status=%d body=%q: %v",
			recorder.Code,
			recorder.Body.String(),
			err,
		)
	}
	return recorder.Code, decoded
}

func performConnectorConnectionRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body any,
	authenticated bool,
	idempotencyKey string,
) (int, map[string]any) {
	t.Helper()
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("encode connector connection request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	if authenticated {
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Actor: operation.ActorContext{AccountID: "account-1"},
		}))
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	decoded := map[string]any{}
	if err := json.Unmarshal(recorder.Body.Bytes(), &decoded); err != nil {
		t.Fatalf("decode connector connection response status=%d body=%q: %v", recorder.Code, recorder.Body.String(), err)
	}
	return recorder.Code, decoded
}
