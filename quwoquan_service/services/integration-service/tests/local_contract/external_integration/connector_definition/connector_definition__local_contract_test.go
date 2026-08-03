// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
package connector_definition_test

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
)

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
