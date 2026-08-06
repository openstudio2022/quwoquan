// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: list-connector-invocations-api
// readiness_case: get-connector-invocation-api
// readiness_case: invoke-connector-capability-api
// readiness_case: continue-connector-invocation-api
package connector_invocation_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	authorizationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/application"
	authorizationmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
	connectorgrant "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/grantreceipt"
	authorizationpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/persistence"
	authorizationreference "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/infrastructure/reference"
	connectionapp "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/application"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	connectionpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/infrastructure/persistence"
	definitionapp "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/application"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	definitionpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/infrastructure/persistence"
	invocationhttp "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/adapters/inbound/http"
	invocationapp "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/application"
	invocationmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
	invocationpersistence "quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/infrastructure/persistence"
)

type invocationTrustedProofVerifier struct{ now time.Time }

func (verifier invocationTrustedProofVerifier) VerifyNative(
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

func (invocationTrustedProofVerifier) VerifyOAuth(
	context.Context,
	authorizationmodel.Authorization,
	string,
) (authorizationmodel.VerifiedProof, error) {
	return authorizationmodel.VerifiedProof{}, authorizationmodel.ErrOAuthCallbackInvalid
}

func TestConnectorInvocationMongoKeepsPayloadProtectedAndCommitsContinuationAtomically(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "integration_connector_invocation")
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

	store := invocationpersistence.NewMongoStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, time.August, 2, 13, 0, 0, 0, time.UTC)
	command, err := invocationmodel.NewAcceptCommand(invocationmodel.AcceptInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		ConnectionID: "connection-1", AssistantRunID: "run-1",
		Capability:      "calendar.event.create",
		PayloadRef:      "protected://artifact/calendar-payload-1",
		ContinuationRef: "continuation-1", IdempotencyKey: "invoke-calendar",
		ConfirmationRequired: true, OccurredAt: now,
	})
	if err != nil {
		t.Fatal(err)
	}
	accepted, err := store.Accept(startupCtx, command)
	if err != nil || accepted.Invocation.Status != invocationmodel.StatusAwaitingConfirmation {
		t.Fatalf("accept failed: result=%+v err=%v", accepted, err)
	}
	replay, err := store.Accept(startupCtx, command)
	if err != nil || !replay.Replayed || replay.Invocation.InvocationID != "invocation-1" {
		t.Fatalf("accept replay failed: result=%+v err=%v", replay, err)
	}
	var raw bson.M
	if err := runtime.Database.Collection("connector_invocations").FindOne(startupCtx, bson.M{"invocationId": "invocation-1"}).Decode(&raw); err != nil {
		t.Fatal(err)
	}
	if _, leaked := raw["payloadRef"]; leaked {
		t.Fatalf("payloadRef leaked into invocation aggregate: %#v", raw)
	}
	continued, err := store.Continue(startupCtx, invocationmodel.ContinueInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		ConfirmationRef: "protected://confirmation/1",
		ContinuationRef: "continuation-1", ExpectedRevision: 1,
		IdempotencyKey: "continue-calendar", OccurredAt: now.Add(time.Minute),
	})
	if err != nil || continued.Invocation.Status != invocationmodel.StatusAccepted ||
		continued.Invocation.Revision != 2 {
		t.Fatalf("continue failed: result=%+v err=%v", continued, err)
	}
	encoded, err := json.Marshal(continued.Invocation)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), "protected://") {
		t.Fatalf("invocation response leaked protected reference: %s", encoded)
	}
	_, err = store.Continue(startupCtx, invocationmodel.ContinueInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		ConfirmationRef:  "protected://confirmation/different",
		ExpectedRevision: 1, IdempotencyKey: "continue-calendar",
		OccurredAt: now.Add(2 * time.Minute),
	})
	if !errors.Is(err, invocationmodel.ErrIdempotencyConflict) {
		t.Fatalf("want continuation idempotency conflict, got %v", err)
	}
	claim, found, err := store.ClaimNext(startupCtx, "worker-1", now.Add(3*time.Minute), time.Minute)
	if err != nil || !found || claim.Invocation.Status != invocationmodel.StatusExecuting ||
		claim.Invocation.Revision != 3 || claim.Invocation.Attempt != 1 ||
		claim.PayloadRef != "protected://artifact/calendar-payload-1" {
		t.Fatalf("claim failed: claim=%+v found=%v err=%v", claim, found, err)
	}
	_, err = store.Complete(startupCtx, invocationmodel.CompleteInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		LeaseOwner: "wrong-worker", ExpectedRevision: 3,
		Status:         invocationmodel.StatusCompleted,
		ResultRef:      "protected://result/calendar-1",
		ResultDigest:   "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		RecoveryAction: "none", OccurredAt: now.Add(4 * time.Minute),
	})
	if !errors.Is(err, invocationmodel.ErrRevisionConflict) {
		t.Fatalf("wrong lease owner must fail CAS, got %v", err)
	}
	completed, err := store.Complete(startupCtx, invocationmodel.CompleteInput{
		InvocationID: "invocation-1", AccountID: "account-1",
		LeaseOwner: "worker-1", ExpectedRevision: 3,
		Status:         invocationmodel.StatusCompleted,
		ResultRef:      "protected://result/calendar-1",
		ResultDigest:   "sha256:1111111111111111111111111111111111111111111111111111111111111111",
		RecoveryAction: "none", OccurredAt: now.Add(4 * time.Minute),
	})
	if err != nil || completed.Invocation.Status != invocationmodel.StatusCompleted ||
		completed.Invocation.Revision != 4 || completed.Invocation.CompletedAt == nil {
		t.Fatalf("complete failed: result=%+v err=%v", completed, err)
	}
	encoded, err = json.Marshal(completed.Invocation)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), "protected://") || strings.Contains(string(encoded), "worker-1") {
		t.Fatalf("terminal response leaked protected/lease state: %s", encoded)
	}
	for collection, want := range map[string]int64{
		"connector_invocations":                 1,
		"connector_invocation_payload_refs":     0,
		"connector_invocation_command_receipts": 2,
		"connector_invocation_outbox":           4,
	} {
		count, countErr := runtime.Database.Collection(collection).CountDocuments(startupCtx, bson.M{})
		if countErr != nil || count != want {
			t.Fatalf("%s count=%d want=%d err=%v", collection, count, want, countErr)
		}
	}
	var auditEvents []bson.M
	cursor, err := runtime.Database.Collection("connector_invocation_outbox").Find(
		startupCtx,
		bson.M{},
	)
	if err != nil || cursor.All(startupCtx, &auditEvents) != nil || len(auditEvents) != 4 {
		t.Fatalf("invocation audit events=%#v err=%v", auditEvents, err)
	}
	for _, event := range auditEvents {
		if _, stale := event["publishedAt"]; stale {
			t.Fatalf("self-retained invocation audit event has delivery checkpoint: %#v", event)
		}
	}
}

func TestConnectorInvocationHTTPUsesRealMongoConnectionAndDefinition(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "integration_connector_invocation_http")
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

	now := time.Date(2026, time.August, 5, 13, 0, 0, 0, time.UTC)
	definitionStore := definitionpersistence.NewMongoStore(runtime.Database)
	authorizationStore := authorizationpersistence.NewMongoStore(runtime.Database)
	connectionStore := connectionpersistence.NewMongoStore(runtime.Database, authorizationStore)
	invocationStore := invocationpersistence.NewMongoStore(runtime.Database)
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
		invocationTrustedProofVerifier{now: now},
		func() time.Time { return now },
		func() string { return "authorization-invocation-http-1" },
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
	grantVerifier := connectorgrant.NewMongoVerifier(runtime.Database, func() time.Time { return now })
	created, err := connectionapp.NewCommandFacade(
		connectionStore,
		definitionStore,
		grantVerifier,
		func() time.Time { return now },
	).Create(startupCtx, connectionmodel.CreateInput{
		AccountID:             "account-1",
		ConnectorID:           "system_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		GrantReceiptRef:       verified.GrantReceiptRef,
		IdempotencyKey:        "connect-calendar",
	})
	if err != nil {
		t.Fatal(err)
	}

	commands := invocationapp.NewCommandFacade(
		invocationStore,
		connectionStore,
		definitionStore,
		func() time.Time { return now },
		func() string { return "invocation-http-1" },
	)
	queries := invocationapp.NewQueryFacade(invocationStore)
	mux := http.NewServeMux()
	invocationhttp.NewHandler(commands, queries).RegisterRoutes(mux)
	status, invokeBody := performConnectorInvocationRequest(
		t,
		mux,
		http.MethodPost,
		"/internal/integrations/invocations",
		map[string]any{
			"accountId":       "account-1",
			"connectionId":    created.Connection.ConnectionID,
			"assistantRunId":  "assistant-run-1",
			"capability":      "calendar.event.create",
			"payloadRef":      "protected://artifact/calendar-payload-http-1",
			"continuationRef": "continuation-http-1",
		},
		false,
		"invoke-calendar-http",
	)
	invocationBody, ok := invokeBody["invocation"].(map[string]any)
	if status != http.StatusAccepted || !ok || invocationBody["invocationId"] != "invocation-http-1" ||
		invocationBody["status"] != invocationmodel.StatusAwaitingConfirmation {
		t.Fatalf("invoke route status=%d body=%#v", status, invokeBody)
	}
	status, getBody := performConnectorInvocationRequest(
		t, mux, http.MethodGet, "/integrations/invocations/invocation-http-1",
		nil, true, "",
	)
	if status != http.StatusOK || getBody["invocationId"] != "invocation-http-1" {
		t.Fatalf("get route status=%d body=%#v", status, getBody)
	}
	status, listBody := performConnectorInvocationRequest(
		t,
		mux,
		http.MethodGet,
		"/integrations/invocations?connectionId="+created.Connection.ConnectionID+"&limit=10",
		nil,
		true,
		"",
	)
	items, ok := listBody["items"].([]any)
	if status != http.StatusOK || !ok || len(items) != 1 {
		t.Fatalf("list route status=%d body=%#v", status, listBody)
	}
	status, continueBody := performConnectorInvocationRequest(
		t,
		mux,
		http.MethodPost,
		"/internal/integrations/invocations/invocation-http-1/continue",
		map[string]any{
			"accountId":        "account-1",
			"confirmationRef":  "protected://confirmation/http-1",
			"continuationRef":  "continuation-http-1",
			"expectedRevision": 1,
		},
		false,
		"continue-calendar-http",
	)
	if status != http.StatusAccepted {
		t.Fatalf("continue route status=%d body=%#v", status, continueBody)
	}
	readback, err := invocationStore.Get(startupCtx, "account-1", "invocation-http-1")
	if err != nil || readback.Status != invocationmodel.StatusAccepted || readback.Revision != 2 {
		t.Fatalf("continued invocation readback=%+v err=%v", readback, err)
	}
}

func performConnectorInvocationRequest(
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
			t.Fatalf("encode connector invocation request: %v", err)
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
		t.Fatalf("decode connector invocation response status=%d body=%q: %v", recorder.Code, recorder.Body.String(), err)
	}
	return recorder.Code, decoded
}
