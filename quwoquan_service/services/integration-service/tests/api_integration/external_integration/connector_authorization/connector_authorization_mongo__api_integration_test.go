// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
package connector_authorization_test

import (
	"context"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
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

func (trustedProofVerifier) VerifyOAuth(
	context.Context,
	authorizationmodel.Authorization,
	string,
) (authorizationmodel.VerifiedProof, error) {
	return authorizationmodel.VerifiedProof{}, authorizationmodel.ErrOAuthCallbackInvalid
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
}
