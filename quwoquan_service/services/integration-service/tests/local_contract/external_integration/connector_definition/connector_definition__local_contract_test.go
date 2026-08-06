// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: publish-connector-definition-local
// readiness_case: list-connector-definitions-local
// readiness_case: get-connector-definition-local
package connector_definition_test

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/application"
	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
)

type definitionStore struct {
	definition    model.Definition
	commandDigest string
}

func (store *definitionStore) Get(_ context.Context, connectorID string) (model.Definition, error) {
	if store.definition.ConnectorID != connectorID {
		return model.Definition{}, model.ErrNotFound
	}
	return store.definition, nil
}

func (store *definitionStore) List(_ context.Context, capability string, _ int) ([]model.Definition, error) {
	if store.definition.ConnectorID == "" || (capability != "" && !store.definition.Grants(capability)) {
		return nil, nil
	}
	return []model.Definition{store.definition}, nil
}

func (store *definitionStore) Publish(_ context.Context, command model.PublishCommand) (model.MutationResult, error) {
	if store.commandDigest != "" {
		if store.commandDigest != command.CommandDigest {
			return model.MutationResult{}, model.ErrIdempotencyConflict
		}
		return model.MutationResult{Definition: store.definition, Replayed: true}, nil
	}
	store.definition = command.Definition
	store.commandDigest = command.CommandDigest
	return model.MutationResult{Definition: store.definition}, nil
}

func TestConnectorDefinitionFacadesPublishGetAndListCanonicalDefinition(t *testing.T) {
	now := time.Date(2026, time.August, 5, 8, 0, 0, 0, time.UTC)
	store := &definitionStore{}
	commands := application.NewCommandFacade(store, func() time.Time { return now })
	queries := application.NewQueryFacade(store)
	definition := model.Definition{
		ConnectorID: "system_calendar", DisplayName: "系统日历",
		Description:        "用户确认后创建日历事项",
		Capabilities:       []string{"calendar.event.create"},
		AuthorizationMode:  model.AuthorizationDeviceNative,
		ConfirmationPolicy: model.ConfirmationUser,
		DataClassification: "sensitive", SupportedSurfaceKinds: []string{"personal"},
		Status: model.StatusActive, ReleaseDigest: "sha256:" + strings.Repeat("f", 64),
	}
	published, err := commands.Publish(context.Background(), model.PublishInput{
		Definition: definition, IdempotencyKey: "publish-system-calendar",
	})
	if err != nil || published.Replayed || published.Definition.PublishedAt != now {
		t.Fatalf("publish failed: result=%+v err=%v", published, err)
	}
	readback, err := queries.Get(context.Background(), "system_calendar")
	if err != nil || readback.ReleaseDigest != definition.ReleaseDigest {
		t.Fatalf("get failed: definition=%+v err=%v", readback, err)
	}
	listed, err := queries.List(context.Background(), "calendar.event.create", 10)
	if err != nil || len(listed) != 1 || listed[0].ConnectorID != "system_calendar" {
		t.Fatalf("list failed: definitions=%+v err=%v", listed, err)
	}
}

func TestConnectorDefinitionCanonicalizesCapabilitiesAndNeverCarriesCredentials(t *testing.T) {
	definition, err := model.Normalize(model.Definition{
		ConnectorID:           "system_calendar",
		DisplayName:           "系统日历",
		Description:           "在用户确认后创建日历事项",
		Capabilities:          []string{"calendar.event.create", " calendar.event.create ", "calendar.event.read"},
		AuthorizationMode:     model.AuthorizationDeviceNative,
		ConfirmationPolicy:    model.ConfirmationUser,
		DataClassification:    "sensitive",
		SupportedSurfaceKinds: []string{"personal"},
		Status:                model.StatusActive,
		ReleaseDigest:         "sha256:" + strings.Repeat("a", 64),
	}, time.Date(2026, time.August, 2, 8, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	if len(definition.Capabilities) != 2 ||
		definition.Capabilities[0] != "calendar.event.create" {
		t.Fatalf("capabilities not canonicalized: %#v", definition.Capabilities)
	}
	encoded, err := json.Marshal(definition)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{"credential", "token", "endpoint", "secret"} {
		if strings.Contains(strings.ToLower(string(encoded)), forbidden) {
			t.Fatalf("definition leaked provider material %q: %s", forbidden, encoded)
		}
	}
}

func TestConnectorDefinitionRejectsNonCanonicalCapability(t *testing.T) {
	_, err := model.Normalize(model.Definition{
		ConnectorID: "bad", DisplayName: "bad", Description: "bad",
		Capabilities: []string{"calendar"}, AuthorizationMode: model.AuthorizationDeviceNative,
		ConfirmationPolicy: model.ConfirmationUser, DataClassification: "sensitive",
		SupportedSurfaceKinds: []string{"personal"}, Status: model.StatusActive,
		ReleaseDigest: "sha256:" + strings.Repeat("b", 64),
	}, time.Now())
	if err == nil {
		t.Fatal("non-canonical capability must fail closed")
	}
}
