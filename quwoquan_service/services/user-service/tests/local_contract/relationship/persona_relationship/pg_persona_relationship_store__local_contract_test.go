package local_contract

import (
	"encoding/json"
	"gopkg.in/yaml.v3"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestRelationshipPayloadContractMatchesActualOutboxSerializer(t *testing.T) {
	_, file, _, _ := runtime.Caller(0)
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "../../../.."))
	payload, err := os.ReadFile(filepath.Join(root, "contracts/relationship/persona_relationship/events.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Events []struct {
			Name          string   `yaml:"name"`
			PayloadEntity string   `yaml:"payload_entity"`
			PayloadFields []string `yaml:"payload_fields"`
		} `yaml:"events"`
	}
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatal(err)
	}
	wire, _ := json.Marshal(relmodel.OutboxPayload{PairID: "pair", SourcePersonaID: "a", TargetPersonaID: "b", Following: false, SourceFollowCleared: true, TargetFollowCleared: true, ClearedFollowDirections: 2, Version: 1, OccurredAt: time.Now()})
	var fields map[string]json.RawMessage
	_ = json.Unmarshal(wire, &fields)
	for _, event := range document.Events {
		if event.PayloadEntity != "PersonaRelationshipEventPayload" {
			t.Fatalf("%s must use explicit payload owner", event.Name)
		}
		for _, key := range event.PayloadFields {
			if _, ok := fields[key]; !ok {
				t.Fatalf("%s declares nonpayload field %s", event.Name, key)
			}
		}
		if len(event.PayloadFields) != len(fields) {
			t.Fatalf("%s omits producer fields", event.Name)
		}
	}
	if _, exists := fields["eventId"]; exists {
		t.Fatal("eventId belongs to envelope")
	}
}

// TestMigratedRelationshipStoreUsesCanonicalPair verifies the public relationship aggregate identity contract.
func TestMigratedRelationshipStoreUsesCanonicalPair(t *testing.T) {
	pair, err := relmodel.NewPair("persona-b", "persona-a")
	if err != nil {
		t.Fatalf("NewPair() error = %v", err)
	}
	if pair.LowerPersonaID != "persona-a" || pair.UpperPersonaID != "persona-b" || pair.ID == "" {
		t.Fatalf("canonical pair = %#v", pair)
	}
}
