// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: publish-connector-definition-api
// readiness_case: list-connector-definitions-api
// readiness_case: get-connector-definition-api
package connector_definition_test

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
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	definitionhttp "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/adapters/inbound/http"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/application"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/infrastructure/persistence"
)

func TestConnectorDefinitionMongoCommitsDefinitionReceiptAndEventLogAtomically(t *testing.T) {
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
	var auditEvent bson.M
	if err := runtime.Database.Collection("connector_definition_outbox").FindOne(
		startupCtx,
		bson.M{"eventType": "ConnectorDefinitionPublished"},
	).Decode(&auditEvent); err != nil {
		t.Fatalf("read definition audit event: %v", err)
	}
	if auditEvent["connectorId"] != definition.ConnectorID ||
		auditEvent["releaseDigest"] != definition.ReleaseDigest {
		t.Fatalf("definition audit event=%#v", auditEvent)
	}
	if _, stale := auditEvent["deliveredAt"]; stale {
		t.Fatalf("self-retained definition audit event has delivery checkpoint: %#v", auditEvent)
	}

	mux := http.NewServeMux()
	definitionhttp.NewHandler(commands, queries).RegisterRoutes(mux)
	httpDefinition := definition
	httpDefinition.ConnectorID = "map_navigation"
	httpDefinition.DisplayName = "地图导航"
	httpDefinition.Capabilities = []string{"map.route.open"}
	httpDefinition.ReleaseDigest = "sha256:" + strings.Repeat("a", 64)
	status, publishedBody := performConnectorDefinitionRequest(
		t, mux, http.MethodPut, "/internal/integrations/connectors/map_navigation",
		httpDefinition, false, "publish-map-navigation",
	)
	if status != http.StatusOK {
		t.Fatalf("publish route status=%d body=%#v", status, publishedBody)
	}
	status, listedBody := performConnectorDefinitionRequest(
		t, mux, http.MethodGet,
		"/integrations/connectors?capability=map.route.open&limit=10",
		nil, true, "",
	)
	listedItems, ok := listedBody["items"].([]any)
	if status != http.StatusOK || !ok || len(listedItems) != 1 {
		t.Fatalf("list route status=%d body=%#v", status, listedBody)
	}
	status, getBody := performConnectorDefinitionRequest(
		t, mux, http.MethodGet, "/integrations/connectors/map_navigation",
		nil, true, "",
	)
	if status != http.StatusOK || getBody["connectorId"] != "map_navigation" ||
		getBody["releaseDigest"] != httpDefinition.ReleaseDigest {
		t.Fatalf("get route status=%d body=%#v", status, getBody)
	}
}

func performConnectorDefinitionRequest(
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
			t.Fatalf("encode connector definition request: %v", err)
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
		t.Fatalf("decode connector definition response status=%d body=%q: %v", recorder.Code, recorder.Body.String(), err)
	}
	return recorder.Code, decoded
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
