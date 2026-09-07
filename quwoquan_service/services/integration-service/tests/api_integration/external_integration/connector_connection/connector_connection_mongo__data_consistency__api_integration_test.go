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
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

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
	connectionports "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/ports"
	connectionpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/infrastructure/persistence"
	definitionapp "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/application"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	definitionpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/infrastructure/persistence"
	invocationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/application"
	invocationmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
	invocationports "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/ports"
	invocationpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/infrastructure/persistence"
)

type trustedNativeProofVerifier struct {
	now time.Time
}

type failAfterInvocationUpdate struct {
	delegate connectionports.PendingInvocationRevoker
	err      error
}

func (revoker failAfterInvocationUpdate) RevokePendingForConnection(
	ctx context.Context,
	accountID string,
	connectionID string,
	occurredAt time.Time,
) error {
	if err := revoker.delegate.RevokePendingForConnection(
		ctx, accountID, connectionID, occurredAt,
	); err != nil {
		return err
	}
	return revoker.err
}

type preclaimedWorkerStore struct {
	delegate invocationports.WorkerStore
	claim    invocationmodel.ExecutionClaim
	returned bool
}

func (store *preclaimedWorkerStore) ClaimNext(
	context.Context, string, time.Time, time.Duration,
) (invocationmodel.ExecutionClaim, bool, error) {
	if store.returned {
		return invocationmodel.ExecutionClaim{}, false, nil
	}
	store.returned = true
	return store.claim, true, nil
}

func (store *preclaimedWorkerStore) Complete(
	ctx context.Context,
	input invocationmodel.CompleteInput,
) (invocationmodel.MutationResult, error) {
	return store.delegate.Complete(ctx, input)
}

type blockingExecutionAuthority struct {
	entered chan struct{}
	release chan struct{}
	permit  invocationapp.ExecutionPermit
}

func (authority *blockingExecutionAuthority) AuthorizeExecution(
	context.Context, invocationapp.ExecutionAuthorityInput,
) (invocationapp.ExecutionPermit, error) {
	close(authority.entered)
	<-authority.release
	return authority.permit, nil
}

type recordingProviderExecutor struct{ called bool }

func (executor *recordingProviderExecutor) Execute(
	context.Context, invocationapp.CapabilityExecution,
) (invocationapp.CapabilityOutcome, error) {
	executor.called = true
	return invocationapp.CapabilityOutcome{
		ResultRef:    "protected://result/should-not-execute",
		ResultDigest: digestForConnectionTest("should-not-execute"),
	}, nil
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
	invocationStore := invocationpersistence.NewMongoStore(runtime.Database)
	connectionStore := connectionpersistence.NewMongoStore(runtime.Database, authorizationStore, invocationStore)
	grantVerifier := connectorgrant.NewMongoVerifier(runtime.Database, func() time.Time { return now })
	for name, ensure := range map[string]func(context.Context) error{
		"definition":    definitionStore.EnsureIndexes,
		"authorization": authorizationStore.EnsureIndexes,
		"connection":    connectionStore.EnsureIndexes,
		"invocation":    invocationStore.EnsureIndexes,
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
	seedConnectionInvocations(
		t, startupCtx, runtime.Database, created.Connection.ConnectionID, now,
	)
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
	var protectedGrant bson.M
	if err := runtime.Database.Collection("connector_authorization_grant_receipts").FindOne(
		startupCtx, bson.M{"grantReceiptDigest": created.Connection.GrantReceiptDigest},
	).Decode(&protectedGrant); err != nil || protectedGrant["credentialRef"] != "" {
		t.Fatalf("protected grant credential was not cleared: grant=%#v err=%v", protectedGrant, err)
	}
	assertConnectionInvocationsRevoked(
		t, startupCtx, runtime.Database, created.Connection.ConnectionID, now,
	)
	if claim, found, err := invocationStore.ClaimNext(
		startupCtx, "post-revoke-worker", now.Add(time.Minute), time.Minute,
	); err != nil || found {
		t.Fatalf("revoke committed before claim but invocation remained claimable: claim=%+v found=%v err=%v", claim, found, err)
	}
	for collection, want := range map[string]int64{
		"connector_connections":                 1,
		"connector_connection_command_receipts": 2,
		"connector_connection_outbox":           2,
		"connector_authorization_outbox":        4,
		"connector_invocations":                 4,
		"connector_invocation_payload_refs":     0,
		"connector_invocation_outbox":           3,
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

func TestConnectorConnectionMongoRollsBackEveryParticipantWhenRevokeFailsAfterInvocationUpdate(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "integration_connector_connection_rollback")
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
	now := time.Date(2026, time.August, 6, 12, 0, 0, 0, time.UTC)
	authorizationStore := authorizationpersistence.NewMongoStore(runtime.Database)
	invocationStore := invocationpersistence.NewMongoStore(runtime.Database)
	injected := errors.New("injected revoke failure after invocation update")
	connectionStore := connectionpersistence.NewMongoStore(
		runtime.Database, authorizationStore, failAfterInvocationUpdate{
			delegate: invocationStore, err: injected,
		},
	)
	for name, ensure := range map[string]func(context.Context) error{
		"authorization": authorizationStore.EnsureIndexes,
		"connection":    connectionStore.EnsureIndexes,
		"invocation":    invocationStore.EnsureIndexes,
	} {
		if err := ensure(startupCtx); err != nil {
			t.Fatalf("ensure %s indexes: %v", name, err)
		}
	}
	grantDigest := authorizationmodel.Hash("rollback-grant")
	authorization := authorizationmodel.Authorization{
		AuthorizationID: "rollback-authorization", AccountID: "account-rollback",
		ConnectorID: "system_calendar", AuthorizationMode: authorizationmodel.ModeDeviceNative,
		RequestedCapabilities: []string{"calendar.event.create"},
		GrantedCapabilities:   []string{"calendar.event.create"},
		Status:                authorizationmodel.StatusConsumed, GrantReceiptDigest: grantDigest,
		CredentialRef: "protected://credential/rollback", ExpiresAt: now.Add(time.Hour),
		Revision: 3, CreatedAt: now.Add(-time.Hour), UpdatedAt: now.Add(-time.Minute),
	}
	if _, err := runtime.Database.Collection("connector_authorizations").InsertOne(startupCtx, authorization); err != nil {
		t.Fatal(err)
	}
	if _, err := runtime.Database.Collection("connector_authorization_grant_receipts").InsertOne(startupCtx, authorizationmodel.GrantReceipt{
		AuthorizationID: authorization.AuthorizationID, AccountID: authorization.AccountID,
		ConnectorID: authorization.ConnectorID, AuthorizationMode: authorization.AuthorizationMode,
		GrantedCapabilities: authorization.GrantedCapabilities,
		CredentialRef:       authorization.CredentialRef, GrantReceiptDigest: grantDigest,
		ProofDigest: authorizationmodel.Hash("rollback-proof"), ExpiresAt: now.Add(time.Hour),
		ConsumedByConnectionID: "rollback-connection", CreatedAt: now.Add(-time.Hour),
	}); err != nil {
		t.Fatal(err)
	}
	connection := connectionmodel.Connection{
		ConnectionID: "rollback-connection", AccountID: authorization.AccountID,
		ConnectorID: authorization.ConnectorID, GrantedCapabilities: authorization.GrantedCapabilities,
		Status: connectionmodel.StatusActive, CredentialRef: authorization.CredentialRef,
		GrantReceiptDigest: grantDigest, FreshnessAt: now.Add(-time.Minute),
		Revision: 7, CreatedAt: now.Add(-time.Hour), UpdatedAt: now.Add(-time.Minute),
	}
	if _, err := runtime.Database.Collection("connector_connections").InsertOne(startupCtx, connection); err != nil {
		t.Fatal(err)
	}
	seedOnePendingInvocation(
		t, startupCtx, runtime.Database, authorization.AccountID, connection.ConnectionID,
		"rollback-invocation", invocationmodel.StatusAccepted, 5, now,
	)
	_, err = connectionStore.Revoke(startupCtx, connectionmodel.RevokeInput{
		AccountID: authorization.AccountID, ConnectionID: connection.ConnectionID,
		ExpectedRevision: connection.Revision, IdempotencyKey: "rollback-revoke",
		OccurredAt: now,
	})
	if !errors.Is(err, injected) {
		t.Fatalf("revoke error=%v want injected failure", err)
	}
	connectionAfter, err := connectionStore.Get(startupCtx, connection.AccountID, connection.ConnectionID)
	if err != nil || connectionAfter.Status != connectionmodel.StatusActive ||
		connectionAfter.CredentialRef != connection.CredentialRef || connectionAfter.Revision != connection.Revision {
		t.Fatalf("connection escaped rollback: connection=%+v err=%v", connectionAfter, err)
	}
	authorizationAfter, err := authorizationStore.Get(startupCtx, authorization.AccountID, authorization.AuthorizationID)
	if err != nil || authorizationAfter.Status != authorizationmodel.StatusConsumed ||
		authorizationAfter.CredentialRef != authorization.CredentialRef || authorizationAfter.Revision != authorization.Revision {
		t.Fatalf("authorization escaped rollback: authorization=%+v err=%v", authorizationAfter, err)
	}
	invocationAfter, err := invocationStore.Get(startupCtx, authorization.AccountID, "rollback-invocation")
	if err != nil || invocationAfter.Status != invocationmodel.StatusAccepted || invocationAfter.Revision != 5 {
		t.Fatalf("invocation escaped rollback: invocation=%+v err=%v", invocationAfter, err)
	}
	var grantAfter bson.M
	if err := runtime.Database.Collection("connector_authorization_grant_receipts").FindOne(
		startupCtx, bson.M{"grantReceiptDigest": grantDigest},
	).Decode(&grantAfter); err != nil || grantAfter["credentialRef"] != authorization.CredentialRef {
		t.Fatalf("grant credential escaped rollback: grant=%#v err=%v", grantAfter, err)
	}
	for collection, filter := range map[string]bson.M{
		"connector_connection_command_receipts": {"accountId": authorization.AccountID},
		"connector_connection_outbox":           {"accountId": authorization.AccountID},
		"connector_authorization_outbox":        {"accountId": authorization.AccountID},
		"connector_invocation_outbox":           {"accountId": authorization.AccountID},
	} {
		count, err := runtime.Database.Collection(collection).CountDocuments(startupCtx, filter)
		if err != nil || count != 0 {
			t.Fatalf("%s escaped rollback: count=%d err=%v", collection, count, err)
		}
	}
}

func TestConnectorConnectionMongoRevokeInvalidatesPreviouslyClaimedFence(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "integration_connector_connection_claim_fence")
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
	now := time.Date(2026, time.August, 6, 13, 0, 0, 0, time.UTC)
	definitionStore := definitionpersistence.NewMongoStore(runtime.Database)
	authorizationStore := authorizationpersistence.NewMongoStore(runtime.Database)
	invocationStore := invocationpersistence.NewMongoStore(runtime.Database)
	connectionStore := connectionpersistence.NewMongoStore(runtime.Database, authorizationStore, invocationStore)
	for name, ensure := range map[string]func(context.Context) error{
		"authorization": authorizationStore.EnsureIndexes,
		"connection":    connectionStore.EnsureIndexes,
		"definition":    definitionStore.EnsureIndexes,
		"invocation":    invocationStore.EnsureIndexes,
	} {
		if err := ensure(startupCtx); err != nil {
			t.Fatalf("ensure %s indexes: %v", name, err)
		}
	}
	definition := definitionmodel.Definition{
		ConnectorID: "system_calendar", DisplayName: "系统日历",
		Description: "用户确认后创建日历事项", Capabilities: []string{"calendar.event.create"},
		AuthorizationMode:  definitionmodel.AuthorizationDeviceNative,
		ConfirmationPolicy: definitionmodel.ConfirmationUser,
		DataClassification: "sensitive", SupportedSurfaceKinds: []string{"personal"},
		Status: definitionmodel.StatusActive, ReleaseDigest: digestForConnectionTest("claim-definition"),
	}
	if _, err := definitionapp.NewCommandFacade(definitionStore, func() time.Time { return now }).Publish(
		startupCtx, definitionmodel.PublishInput{Definition: definition, IdempotencyKey: "publish-claim-definition"},
	); err != nil {
		t.Fatal(err)
	}
	grantDigest := authorizationmodel.Hash("claim-fence-grant")
	authorization := authorizationmodel.Authorization{
		AuthorizationID: "claim-fence-authorization", AccountID: "account-claim",
		ConnectorID: "system_calendar", AuthorizationMode: authorizationmodel.ModeDeviceNative,
		RequestedCapabilities: []string{"calendar.event.create"},
		GrantedCapabilities:   []string{"calendar.event.create"},
		Status:                authorizationmodel.StatusConsumed, GrantReceiptDigest: grantDigest,
		CredentialRef: "protected://credential/claim", ExpiresAt: now.Add(time.Hour),
		Revision: 3, CreatedAt: now.Add(-time.Hour), UpdatedAt: now.Add(-time.Minute),
	}
	if _, err := runtime.Database.Collection("connector_authorizations").InsertOne(startupCtx, authorization); err != nil {
		t.Fatal(err)
	}
	if _, err := runtime.Database.Collection("connector_authorization_grant_receipts").InsertOne(startupCtx, authorizationmodel.GrantReceipt{
		AuthorizationID: authorization.AuthorizationID, AccountID: authorization.AccountID,
		ConnectorID: authorization.ConnectorID, AuthorizationMode: authorization.AuthorizationMode,
		GrantedCapabilities: authorization.GrantedCapabilities,
		CredentialRef:       authorization.CredentialRef, GrantReceiptDigest: grantDigest,
		ProofDigest: authorizationmodel.Hash("claim-proof"), ExpiresAt: now.Add(time.Hour),
		ConsumedByConnectionID: "claim-connection", CreatedAt: now.Add(-time.Hour),
	}); err != nil {
		t.Fatal(err)
	}
	connection := connectionmodel.Connection{
		ConnectionID: "claim-connection", AccountID: authorization.AccountID,
		ConnectorID: authorization.ConnectorID, GrantedCapabilities: authorization.GrantedCapabilities,
		Status: connectionmodel.StatusActive, CredentialRef: authorization.CredentialRef,
		GrantReceiptDigest: grantDigest, FreshnessAt: now.Add(-time.Minute),
		Revision: 4, CreatedAt: now.Add(-time.Hour), UpdatedAt: now.Add(-time.Minute),
	}
	if _, err := runtime.Database.Collection("connector_connections").InsertOne(startupCtx, connection); err != nil {
		t.Fatal(err)
	}
	grantStore, err := grantpersistence.NewRedisSessionStore(rtredis.NewMemoryClient())
	if err != nil {
		t.Fatal(err)
	}
	unavailable := grantcandidate.NewUnavailableSources("not used by claimed worker")
	grantSession := grantapp.NewCapabilityGrantSessionFacade(
		grantresolver.NewCandidateResolver(
			unavailable,
			grantcandidate.NewConnectorReaderSource(connectionStore, definitionStore, func() time.Time { return now }),
			unavailable, unavailable, func() time.Time { return now },
		),
		grantStore,
		func() time.Time { return now },
	)
	const (
		invocationID    = "claim-fence-invocation"
		resolutionID    = "claim-fence-resolution"
		confirmationRef = "claim-fence-confirmation"
		permitRef       = "claim-fence-permit"
		idempotencyKey  = "claim-fence-invoke"
	)
	inputDigest := digestForConnectionTest("claim-fence-input")
	trusted, err := grantapp.NewTrustedRuntimeAuthorization(
		authorization.AccountID, grantapp.AssistantServiceActorID,
	)
	if err != nil {
		t.Fatal(err)
	}
	resolved, err := grantSession.AuthorizeFinalInput(startupCtx, trusted, grantapp.FinalAuthorizationInput{
		ResolutionID: resolutionID, CapabilityKey: "calendar.event.create", SurfaceKind: "personal",
		ConnectionRefs: []string{connection.ConnectionID}, BindingKind: grantmodel.BindingUserConnector,
		InputDigest: inputDigest, ConfirmationRef: confirmationRef, PermitRef: permitRef,
		IdempotencyKey: idempotencyKey,
	})
	if err != nil {
		t.Fatal(err)
	}
	bindingDigest, err := grantmodel.BindingDigest(resolved)
	if err != nil {
		t.Fatal(err)
	}
	accept, err := invocationmodel.NewAcceptCommand(invocationmodel.AcceptInput{
		InvocationID: invocationID, AccountID: authorization.AccountID, ResolutionID: resolutionID,
		ConnectionID: connection.ConnectionID, AssistantRunID: "claim-fence-run",
		Capability: "calendar.event.create", SurfaceKind: "personal", BindingDigest: bindingDigest,
		InputDigest: inputDigest, PayloadRef: "protected://payload/claim-fence",
		ConfirmationRef: confirmationRef, PermitRef: permitRef, IdempotencyKey: idempotencyKey,
		OccurredAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := invocationStore.Accept(startupCtx, accept); err != nil {
		t.Fatal(err)
	}
	claim, found, err := invocationStore.ClaimNext(startupCtx, "claim-worker", now, time.Minute)
	if err != nil || !found {
		t.Fatalf("claim before revoke: claim=%+v found=%v err=%v", claim, found, err)
	}
	authority := &blockingExecutionAuthority{
		entered: make(chan struct{}), release: make(chan struct{}),
		permit: invocationapp.ExecutionPermit{
			PermitRef: permitRef, Digest: grantmodel.OpaqueDigest(permitRef), ExpiresAt: now.Add(time.Minute),
		},
	}
	executor := &recordingProviderExecutor{}
	worker := invocationapp.NewInvocationWorker(
		&preclaimedWorkerStore{delegate: invocationStore, claim: claim},
		grantSession, connectionStore, definitionStore, authority, executor,
		"claim-worker", time.Minute, func() time.Time { return now },
	)
	workerDone := make(chan error, 1)
	go func() {
		_, err := worker.RunOnce(startupCtx)
		workerDone <- err
	}()
	select {
	case <-authority.entered:
	case <-time.After(10 * time.Second):
		t.Fatal("worker did not reach execution authority before revoke")
	}
	if _, err := connectionStore.Revoke(startupCtx, connectionmodel.RevokeInput{
		AccountID: authorization.AccountID, ConnectionID: connection.ConnectionID,
		ExpectedRevision: connection.Revision, IdempotencyKey: "claim-fence-revoke",
		OccurredAt: now.Add(time.Second),
	}); err != nil {
		t.Fatal(err)
	}
	close(authority.release)
	if err := <-workerDone; !errors.Is(err, invocationmodel.ErrRevisionConflict) {
		t.Fatalf("stale worker fence error=%v want revision conflict", err)
	}
	if executor.called {
		t.Fatal("revoked connection reached Provider side effect")
	}
	_, err = invocationStore.Complete(startupCtx, invocationmodel.CompleteInput{
		InvocationID: claim.Invocation.InvocationID, AccountID: claim.Invocation.AccountID,
		LeaseOwner: "claim-worker", ExpectedRevision: claim.Invocation.Revision,
		Status: invocationmodel.StatusCompleted, ResultRef: "protected://result/stale",
		ResultDigest: digestForConnectionTest("stale-result"), RecoveryAction: "none",
		OccurredAt: now.Add(2 * time.Second),
	})
	if !errors.Is(err, invocationmodel.ErrRevisionConflict) {
		t.Fatalf("stale claim completion error=%v want revision conflict", err)
	}
	terminal, err := invocationStore.Get(startupCtx, authorization.AccountID, claim.Invocation.InvocationID)
	if err != nil || terminal.Status != invocationmodel.StatusFailed ||
		terminal.NormalizedFailureCode != "connection_inactive" ||
		terminal.Revision != claim.Invocation.Revision+1 || terminal.LeaseOwner != "" {
		t.Fatalf("revoke did not invalidate claim fence: terminal=%+v err=%v", terminal, err)
	}
}

func TestConnectorConnectionMongoConcurrentRevokeAndClaimLeavesNoClaimableInvocation(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "integration_connector_connection_revoke_claim_race")
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
	now := time.Date(2026, time.August, 6, 14, 0, 0, 0, time.UTC)
	authorizationStore := authorizationpersistence.NewMongoStore(runtime.Database)
	invocationStore := invocationpersistence.NewMongoStore(runtime.Database)
	connectionStore := connectionpersistence.NewMongoStore(runtime.Database, authorizationStore, invocationStore)
	for name, ensure := range map[string]func(context.Context) error{
		"authorization": authorizationStore.EnsureIndexes,
		"connection":    connectionStore.EnsureIndexes,
		"invocation":    invocationStore.EnsureIndexes,
	} {
		if err := ensure(startupCtx); err != nil {
			t.Fatalf("ensure %s indexes: %v", name, err)
		}
	}
	grantDigest := authorizationmodel.Hash("race-grant")
	authorization := authorizationmodel.Authorization{
		AuthorizationID: "race-authorization", AccountID: "account-race",
		ConnectorID: "system_calendar", AuthorizationMode: authorizationmodel.ModeDeviceNative,
		RequestedCapabilities: []string{"calendar.event.create"},
		GrantedCapabilities:   []string{"calendar.event.create"},
		Status:                authorizationmodel.StatusConsumed, GrantReceiptDigest: grantDigest,
		CredentialRef: "protected://credential/race", ExpiresAt: now.Add(time.Hour),
		Revision: 3, CreatedAt: now.Add(-time.Hour), UpdatedAt: now.Add(-time.Minute),
	}
	if _, err := runtime.Database.Collection("connector_authorizations").InsertOne(startupCtx, authorization); err != nil {
		t.Fatal(err)
	}
	if _, err := runtime.Database.Collection("connector_authorization_grant_receipts").InsertOne(startupCtx, authorizationmodel.GrantReceipt{
		AuthorizationID: authorization.AuthorizationID, AccountID: authorization.AccountID,
		ConnectorID: authorization.ConnectorID, AuthorizationMode: authorization.AuthorizationMode,
		GrantedCapabilities: authorization.GrantedCapabilities,
		CredentialRef:       authorization.CredentialRef, GrantReceiptDigest: grantDigest,
		ProofDigest: authorizationmodel.Hash("race-proof"), ExpiresAt: now.Add(time.Hour),
		ConsumedByConnectionID: "race-connection", CreatedAt: now.Add(-time.Hour),
	}); err != nil {
		t.Fatal(err)
	}
	connection := connectionmodel.Connection{
		ConnectionID: "race-connection", AccountID: authorization.AccountID,
		ConnectorID: authorization.ConnectorID, GrantedCapabilities: authorization.GrantedCapabilities,
		Status: connectionmodel.StatusActive, CredentialRef: authorization.CredentialRef,
		GrantReceiptDigest: grantDigest, FreshnessAt: now.Add(-time.Minute),
		Revision: 5, CreatedAt: now.Add(-time.Hour), UpdatedAt: now.Add(-time.Minute),
	}
	if _, err := runtime.Database.Collection("connector_connections").InsertOne(startupCtx, connection); err != nil {
		t.Fatal(err)
	}
	const writerCount = 16
	for index := 0; index < writerCount; index++ {
		seedOnePendingInvocation(
			t, startupCtx, runtime.Database, authorization.AccountID, connection.ConnectionID,
			fmt.Sprintf("race-invocation-%02d", index), invocationmodel.StatusAccepted, 1, now,
		)
	}
	start := make(chan struct{})
	type claimResult struct {
		claim invocationmodel.ExecutionClaim
		found bool
		err   error
	}
	claims := make(chan claimResult, writerCount)
	for index := 0; index < writerCount; index++ {
		workerID := fmt.Sprintf("race-worker-%02d", index)
		go func() {
			<-start
			claim, found, err := invocationStore.ClaimNext(startupCtx, workerID, now, time.Minute)
			claims <- claimResult{claim: claim, found: found, err: err}
		}()
	}
	revokeDone := make(chan error, 1)
	go func() {
		<-start
		_, err := connectionStore.Revoke(startupCtx, connectionmodel.RevokeInput{
			AccountID: connection.AccountID, ConnectionID: connection.ConnectionID,
			ExpectedRevision: connection.Revision, IdempotencyKey: "race-revoke",
			OccurredAt: now.Add(time.Second),
		})
		revokeDone <- err
	}()
	close(start)
	var claimed []invocationmodel.ExecutionClaim
	for index := 0; index < writerCount; index++ {
		result := <-claims
		if result.err != nil {
			t.Fatalf("concurrent claim %d: %v", index, result.err)
		}
		if result.found {
			claimed = append(claimed, result.claim)
		}
	}
	if err := <-revokeDone; err != nil {
		t.Fatalf("concurrent revoke: %v", err)
	}
	if claim, found, err := invocationStore.ClaimNext(
		startupCtx, "post-race-worker", now.Add(2*time.Second), time.Minute,
	); err != nil || found {
		t.Fatalf("post-revoke invocation remained claimable: claim=%+v found=%v err=%v", claim, found, err)
	}
	for _, claim := range claimed {
		_, err := invocationStore.Complete(startupCtx, invocationmodel.CompleteInput{
			InvocationID: claim.Invocation.InvocationID, AccountID: claim.Invocation.AccountID,
			LeaseOwner: claim.Invocation.LeaseOwner, ExpectedRevision: claim.Invocation.Revision,
			Status: invocationmodel.StatusCompleted, ResultRef: "protected://result/race-stale",
			ResultDigest: digestForConnectionTest("race-stale-result"), RecoveryAction: "none",
			OccurredAt: now.Add(3 * time.Second),
		})
		if !errors.Is(err, invocationmodel.ErrRevisionConflict) {
			t.Fatalf("old claim %s completed after revoke: %v", claim.Invocation.InvocationID, err)
		}
	}
	count, err := runtime.Database.Collection("connector_invocations").CountDocuments(startupCtx, bson.M{
		"accountId": authorization.AccountID, "connectionId": connection.ConnectionID,
		"status":                invocationmodel.StatusFailed,
		"normalizedFailureCode": "connection_inactive", "recoveryAction": "reconnect",
		"leaseOwner": bson.M{"$exists": false}, "leaseExpiresAt": bson.M{"$exists": false},
	})
	if err != nil || count != writerCount {
		t.Fatalf("terminalized invocation count=%d want=%d err=%v claimed_before=%d", count, writerCount, err, len(claimed))
	}
	// Provider execution is intentionally absent from this persistence race harness:
	// every pre-linearization claim is fenced by the revision check above, while the
	// worker local-contract test proves the final authority read blocks its executor.
}

func seedOnePendingInvocation(
	t *testing.T,
	ctx context.Context,
	database *mongo.Database,
	accountID string,
	connectionID string,
	invocationID string,
	status string,
	revision int64,
	now time.Time,
) {
	t.Helper()
	invocation := invocationmodel.Invocation{
		InvocationID: invocationID, AccountID: accountID,
		ResolutionID: "resolution-" + invocationID, ConnectionID: connectionID,
		AssistantRunID: "run-" + invocationID, Capability: "calendar.event.create",
		SurfaceKind: "personal", BindingDigest: digestForConnectionTest("binding-" + invocationID),
		InputDigest:        digestForConnectionTest("input-" + invocationID),
		ConfirmationDigest: digestForConnectionTest("confirmation-" + invocationID),
		PermitDigest:       digestForConnectionTest("permit-" + invocationID),
		IdempotencyDigest:  digestForConnectionTest("idempotency-" + invocationID),
		RequestDigest:      digestForConnectionTest("request-" + invocationID), Status: status,
		RecoveryAction: "none", Revision: revision, CreatedAt: now, UpdatedAt: now,
	}
	if _, err := database.Collection("connector_invocations").InsertOne(ctx, invocation); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("connector_invocation_payload_refs").InsertOne(ctx, bson.M{
		"_id": invocationID, "invocationId": invocationID,
		"payloadRef": "protected://payload/" + invocationID, "expiresAt": now.Add(24 * time.Hour),
	}); err != nil {
		t.Fatal(err)
	}
}

func seedConnectionInvocations(
	t *testing.T,
	ctx context.Context,
	database *mongo.Database,
	connectionID string,
	now time.Time,
) {
	t.Helper()
	statuses := []string{
		invocationmodel.StatusAccepted,
		invocationmodel.StatusAwaitingConfirmation,
		invocationmodel.StatusExecuting,
		invocationmodel.StatusCompleted,
	}
	for index, status := range statuses {
		invocation := invocationmodel.Invocation{
			InvocationID: fmt.Sprintf("revoke-invocation-%d", index+1),
			AccountID:    "account-1", ResolutionID: fmt.Sprintf("resolution-%d", index+1),
			ConnectionID: connectionID, AssistantRunID: fmt.Sprintf("run-%d", index+1),
			Capability: "calendar.event.create", SurfaceKind: "personal",
			BindingDigest:      digestForConnectionTest(fmt.Sprintf("binding-%d", index+1)),
			InputDigest:        digestForConnectionTest(fmt.Sprintf("input-%d", index+1)),
			ConfirmationDigest: digestForConnectionTest(fmt.Sprintf("confirmation-%d", index+1)),
			PermitDigest:       digestForConnectionTest(fmt.Sprintf("permit-%d", index+1)),
			IdempotencyDigest:  digestForConnectionTest(fmt.Sprintf("idempotency-%d", index+1)),
			RequestDigest:      digestForConnectionTest(fmt.Sprintf("request-%d", index+1)),
			Status:             status, RecoveryAction: "none", Revision: 1,
			CreatedAt: now.Add(time.Duration(index) * time.Second),
			UpdatedAt: now.Add(time.Duration(index) * time.Second),
		}
		if status == invocationmodel.StatusExecuting {
			leaseExpiry := now.Add(time.Minute)
			invocation.LeaseOwner = "pre-revoke-worker"
			invocation.LeaseExpiresAt = &leaseExpiry
		}
		if status == invocationmodel.StatusCompleted {
			completedAt := now.Add(time.Duration(index) * time.Second)
			invocation.CompletedAt = &completedAt
		}
		if _, err := database.Collection("connector_invocations").InsertOne(ctx, invocation); err != nil {
			t.Fatalf("seed invocation status %s: %v", status, err)
		}
		if status != invocationmodel.StatusCompleted {
			if _, err := database.Collection("connector_invocation_payload_refs").InsertOne(ctx, bson.M{
				"_id": invocation.InvocationID, "invocationId": invocation.InvocationID,
				"payloadRef": "protected://payload/" + invocation.InvocationID,
				"expiresAt":  now.Add(24 * time.Hour),
			}); err != nil {
				t.Fatalf("seed invocation payload status %s: %v", status, err)
			}
		}
	}
}

func assertConnectionInvocationsRevoked(
	t *testing.T,
	ctx context.Context,
	database *mongo.Database,
	connectionID string,
	now time.Time,
) {
	t.Helper()
	cursor, err := database.Collection("connector_invocations").Find(
		ctx, bson.M{"connectionId": connectionID}, options.Find().SetSort(bson.D{{Key: "invocationId", Value: 1}}),
	)
	if err != nil {
		t.Fatal(err)
	}
	defer cursor.Close(ctx)
	var invocations []invocationmodel.Invocation
	if err := cursor.All(ctx, &invocations); err != nil {
		t.Fatal(err)
	}
	if len(invocations) != 4 {
		t.Fatalf("invocation readback count=%d want=4", len(invocations))
	}
	for _, invocation := range invocations {
		if invocation.Status == invocationmodel.StatusCompleted {
			if invocation.Revision != 1 {
				t.Fatalf("provider-terminal invocation changed: %+v", invocation)
			}
			continue
		}
		if invocation.Status != invocationmodel.StatusFailed || invocation.Revision != 2 ||
			invocation.NormalizedFailureCode != "connection_inactive" ||
			invocation.RecoveryAction != "reconnect" || invocation.CompletedAt == nil ||
			!invocation.CompletedAt.Equal(now) || invocation.LeaseOwner != "" ||
			invocation.LeaseExpiresAt != nil {
			t.Fatalf("pending invocation was not atomically revoked: %+v", invocation)
		}
	}
}

func digestForConnectionTest(value string) string {
	sum := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(sum[:])
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
