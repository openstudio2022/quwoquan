// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
package connector_connection_test

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
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
		CredentialRef:       "protected://native/calendar/account-1",
		ProofDigest:         authorizationmodel.Hash(proofRef),
		GrantedCapabilities: append([]string(nil), authorization.RequestedCapabilities...),
		CredentialExpiresAt: &expiresAt,
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
	create := connectionmodel.CreateInput{
		AccountID: "account-1", ConnectorID: "system_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		GrantReceiptRef:       verified.GrantReceiptRef, IdempotencyKey: "connect-calendar",
	}
	created, err := commands.Create(startupCtx, create)
	if err != nil || created.Replayed || created.Connection.Revision != 1 {
		t.Fatalf("create failed: result=%+v err=%v", created, err)
	}
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
	revoked, err := commands.Revoke(startupCtx, connectionmodel.RevokeInput{
		AccountID: "account-1", ConnectionID: created.Connection.ConnectionID,
		ExpectedRevision: 1, IdempotencyKey: "revoke-calendar",
	})
	if err != nil || revoked.Connection.Status != connectionmodel.StatusRevoked ||
		revoked.Connection.Revision != 2 || revoked.Connection.CredentialRef != "" {
		t.Fatalf("revoke failed closed incorrectly: result=%+v err=%v", revoked, err)
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
}
