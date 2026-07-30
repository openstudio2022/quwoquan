package local_contract

import (
	"encoding/json"
	"testing"

	personaseed "quwoquan_service/services/user-service/internal/persona_management/persona/application/environmentseed"
)

func TestPrimaryPersonaSeedIsDeterministicAndOwnedByProfile(t *testing.T) {
	input := personaseed.PrimaryPersonaInput{
		UserID:        "fixture_user_current",
		DisplayName:   "当前用户",
		AvatarURL:     "https://example.test/avatar.png",
		Bio:           "seed bio",
		AvatarVersion: 1,
	}
	first := personaseed.BuildPrimaryPersona(input)
	second := personaseed.BuildPrimaryPersona(input)
	firstJSON, err := json.Marshal(first)
	if err != nil {
		t.Fatalf("marshal first Persona: %v", err)
	}
	secondJSON, err := json.Marshal(second)
	if err != nil {
		t.Fatalf("marshal second Persona: %v", err)
	}
	if string(firstJSON) != string(secondJSON) {
		t.Fatalf("primary Persona seed must be deterministic")
	}
	if first.UserID != input.UserID ||
		first.PersonaID != input.UserID ||
		!first.IsPrimary ||
		!first.IsActive ||
		first.Status != "active" ||
		first.IsolationLevel != "open" {
		t.Fatalf("unexpected primary Persona seed: %+v", first)
	}
	var payload map[string]any
	if err := json.Unmarshal(firstJSON, &payload); err != nil {
		t.Fatalf("decode first Persona: %v", err)
	}
	if _, exists := payload["phone"]; exists {
		t.Fatal("Persona seed must not contain phone plaintext")
	}
	if _, exists := payload["email"]; exists {
		t.Fatal("Persona seed must not contain email plaintext")
	}
}
