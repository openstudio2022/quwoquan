package local_contract

import (
	"reflect"
	"testing"

	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
)

func TestPersonaProfileChangeSetIsTypedValidatedAndStable(t *testing.T) {
	displayName := "山野记录者"
	isolation := "semi"
	change := personamodel.ProfileChangeSet{
		DisplayName:    &displayName,
		IsolationLevel: &isolation,
	}
	if err := change.Validate(); err != nil {
		t.Fatalf("valid Persona change rejected: %v", err)
	}
	if got, want := change.ChangedFields(), []string{"displayName", "isolationLevel"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("changed fields got=%v want=%v", got, want)
	}
	if err := (personamodel.ProfileChangeSet{}).Validate(); err == nil {
		t.Fatal("empty Persona change set must be rejected")
	}
}
