package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
	circlemodel "quwoquan_service/services/circle-service/internal/circle_management/circle/domain/model"
	membershipports "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/ports"
)

func TestPersonaCircleSliceUsesCanonicalTypedCircleFields(t *testing.T) {
	t.Parallel()

	summary := membershipports.CircleSummary{
		ID:                 "circle-1",
		Status:             circlemodel.CircleStatusActive,
		Visibility:         circlemodel.CircleVisibilityPublic,
		JoinPolicy:         circlemodel.CircleJoinPolicyOpen,
		Kind:               circlemodel.CircleKindInterest,
		DisplaySubjectType: circlemodel.CircleDisplaySubjectTypeCircle,
		LinkedHomepageType: circlemodel.HomepageTypeSight,
	}
	raw, err := json.Marshal(summary)
	if err != nil {
		t.Fatalf("marshal PersonaCircleSlice item: %v", err)
	}
	var payload map[string]any
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatalf("decode PersonaCircleSlice item: %v", err)
	}
	if payload["status"] != "active" {
		t.Fatalf("status=%v, want active", payload["status"])
	}
	if _, exists := payload["state"]; exists {
		t.Fatalf("PersonaCircleSlice retains non-canonical state alias: %s", raw)
	}

	fieldsRaw := readCircleContract(t, filepath.Join(
		circleServiceRoot(t),
		"contracts", "circle_management", "circle_membership", "fields.yaml",
	))
	var fieldsContract struct {
		Types map[string]struct {
			Fields []struct {
				Name    string `yaml:"name"`
				Type    string `yaml:"type"`
				EnumRef string `yaml:"enum_ref"`
			} `yaml:"fields"`
		} `yaml:"types"`
	}
	if err := yaml.Unmarshal([]byte(fieldsRaw), &fieldsContract); err != nil {
		t.Fatalf("decode CircleMembership fields contract: %v", err)
	}
	personaCircle, found := fieldsContract.Types["PersonaCircleSlice"]
	if !found {
		t.Fatal("CircleMembership fields contract misses PersonaCircleSlice")
	}
	actualEnums := make(map[string]string, len(personaCircle.Fields))
	for _, field := range personaCircle.Fields {
		if field.Type == "enum" {
			actualEnums[field.Name] = field.EnumRef
		}
	}
	for fieldName, enumRef := range map[string]string{
		"status":             "CircleStatus",
		"visibility":         "CircleVisibility",
		"joinPolicy":         "CircleJoinPolicy",
		"kind":               "CircleKind",
		"displaySubjectType": "CircleDisplaySubjectType",
		"linkedHomepageType": "HomepageType",
	} {
		if actualEnums[fieldName] != enumRef {
			t.Fatalf(
				"PersonaCircleSlice field %s enum_ref=%q, want %q",
				fieldName,
				actualEnums[fieldName],
				enumRef,
			)
		}
	}
}

func TestCircleSourceContractHasNoRetiredConversationBinding(t *testing.T) {
	t.Parallel()

	root := circleServiceRoot(t)
	fields := readCircleContract(t, filepath.Join(
		root, "contracts", "circle_management", "circle", "fields.yaml",
	))
	object := readCircleContract(t, filepath.Join(
		root, "contracts", "circle_management", "circle", "object.yaml",
	))
	events := readCircleContract(t, filepath.Join(
		root, "contracts", "circle_management", "circle", "events.yaml",
	))
	if strings.Contains(fields, "- name: conversationId") {
		t.Fatal("Circle source fields retain retired conversationId")
	}
	if strings.Contains(object, "name: conversation\n") {
		t.Fatal("Circle source object retains direct Chat Conversation relationship")
	}
	if strings.Contains(events, "name: CircleConversationLinked") {
		t.Fatal("Circle source events retain retired CircleConversationLinked backfill")
	}
}

func circleServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test file path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
}

func readCircleContract(t *testing.T, path string) string {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(raw)
}
