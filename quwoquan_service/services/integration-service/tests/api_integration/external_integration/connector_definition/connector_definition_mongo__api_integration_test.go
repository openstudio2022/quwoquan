// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
package connector_definition_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/application"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/infrastructure/persistence"
)

func TestConnectorDefinitionMongoCommitsDefinitionReceiptAndOutboxAtomically(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "integration_connector_definition")
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

	store := persistence.NewMongoStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure indexes: %v", err)
	}
	now := time.Date(2026, time.August, 2, 11, 0, 0, 0, time.UTC)
	commands := application.NewCommandFacade(store, func() time.Time { return now })
	queries := application.NewQueryFacade(store)
	definition := model.Definition{
		ConnectorID: "system_calendar", DisplayName: "系统日历",
		Description:        "用户确认后创建日历事项",
		Capabilities:       []string{"calendar.event.create"},
		AuthorizationMode:  model.AuthorizationDeviceNative,
		ConfirmationPolicy: model.ConfirmationUser,
		DataClassification: "sensitive", SupportedSurfaceKinds: []string{"personal"},
		Status: model.StatusActive, ReleaseDigest: "sha256:" + strings.Repeat("d", 64),
	}
	first, err := commands.Publish(startupCtx, model.PublishInput{
		Definition: definition, IdempotencyKey: "publish-system-calendar",
	})
	if err != nil || first.Replayed {
		t.Fatalf("first publish failed: result=%+v err=%v", first, err)
	}
	replay, err := commands.Publish(startupCtx, model.PublishInput{
		Definition: definition, IdempotencyKey: "publish-system-calendar",
	})
	if err != nil || !replay.Replayed || replay.Definition.ReleaseDigest != definition.ReleaseDigest {
		t.Fatalf("publish replay drifted: result=%+v err=%v", replay, err)
	}
	conflicting := definition
	conflicting.ReleaseDigest = "sha256:" + strings.Repeat("e", 64)
	_, err = commands.Publish(startupCtx, model.PublishInput{
		Definition: conflicting, IdempotencyKey: "publish-system-calendar",
	})
	if !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("want idempotency conflict, got %v", err)
	}
	items, err := queries.List(startupCtx, "calendar.event.create", 10)
	if err != nil || len(items) != 1 || items[0].ConnectorID != "system_calendar" {
		t.Fatalf("catalog readback failed: items=%+v err=%v", items, err)
	}
	assertCount(t, startupCtx, runtime.Database.Collection("connector_definitions"), 1)
	assertCount(t, startupCtx, runtime.Database.Collection("connector_definition_command_receipts"), 1)
	assertCount(t, startupCtx, runtime.Database.Collection("connector_definition_outbox"), 1)
}

func assertCount(t *testing.T, ctx context.Context, collection *mongo.Collection, want int64) {
	t.Helper()
	count, err := collection.CountDocuments(ctx, bson.M{})
	if err != nil {
		t.Fatal(err)
	}
	if count != want {
		t.Fatalf("count=%d want=%d", count, want)
	}
}
