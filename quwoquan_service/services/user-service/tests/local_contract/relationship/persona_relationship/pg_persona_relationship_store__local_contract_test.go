package local_contract

import (
	"encoding/json"
	"gopkg.in/yaml.v3"
	"os"
	"path/filepath"
	"reflect"
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

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-006
// 仅证明协议 authoring，不能替代该 GWT 的真实命令终结与并发证据。
func TestRelationshipMutationEvidenceContractSeparatesIdentityAndHistory(t *testing.T) {
	var document struct {
		Enums map[string]struct {
			Values []string `yaml:"values"`
		} `yaml:"enums"`
		Types map[string]struct {
			Fields []struct {
				Name        string   `yaml:"name"`
				Type        string   `yaml:"type"`
				Constraints []string `yaml:"constraints"`
				LogPolicy   string   `yaml:"log_policy"`
				Exposure    string   `yaml:"api_exposure"`
				MaxBytes    int      `yaml:"max_utf8_bytes"`
			} `yaml:"fields"`
		} `yaml:"types"`
	}
	raw := readContract(t, filepath.Join(userServiceRoot(t), "contracts/relationship/persona_relationship/fields.yaml"))
	if err := yaml.Unmarshal([]byte(raw), &document); err != nil {
		t.Fatal(err)
	}
	if got := document.Enums["PersonaRelationshipReceiptOutcome"].Values; !reflect.DeepEqual(got, []string{"committed", "rejected", "expired", "history_unavailable"}) {
		t.Fatalf("receipt outcomes must preserve unknown history: %v", got)
	}
	for _, name := range []string{"actorPersonaId", "targetPersonaId", "targetKind", "pairId", "audience", "expectedVersion", "allowedActions", "issuedAt", "acceptUntil"} {
		found := false
		for _, field := range document.Types["PersonaRelationshipMutationBasisClaims"].Fields {
			if field.Name == name {
				found = true
				if field.Exposure != "drop" {
					t.Fatalf("internal basis claim %s must not be a public projection", name)
				}
			}
		}
		if !found {
			t.Fatalf("missing identity-bound basis claim %s", name)
		}
	}
	var evidenceNames []string
	for _, field := range document.Types["PersonaRelationshipMutationEvidence"].Fields {
		evidenceNames = append(evidenceNames, field.Name)
		if field.Name == "mutationBasis" && (field.LogPolicy != "drop" || field.MaxBytes != 4096) {
			t.Fatal("opaque basis must be bounded and excluded from logs")
		}
		if field.Name == "idempotencyKey" && (field.LogPolicy != "hash" || field.MaxBytes != 128) {
			t.Fatal("command identity must be bounded and hashed in logs")
		}
	}
	if !reflect.DeepEqual(evidenceNames, []string{"idempotencyKey", "mutationBasis", "expectedVersion"}) {
		t.Fatalf("mutation evidence has a second or missing identity: %v", evidenceNames)
	}
	for _, field := range document.Types["PersonaRelationshipCommandRecoverySlice"].Fields {
		if field.Name == "isFollowing" || field.Name == "relationState" {
			t.Fatal("current relationship cannot stand in for historical receipt")
		}
	}
}
