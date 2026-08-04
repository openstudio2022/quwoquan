// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/spec.md#sit-001
package local_contract

import (
	"reflect"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/compiler"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

func TestUserAccountLifecycleUsesAccountStateAsItsOnlyRuntimeState(t *testing.T) {
	profileType := reflect.TypeOf(model.UserProfile{})
	if _, exists := profileType.FieldByName("AccountState"); !exists {
		t.Fatal("generated UserAccount must expose canonical AccountState")
	}
	if _, exists := profileType.FieldByName("Status"); exists {
		t.Fatal("generated UserAccount must not reintroduce retired Status")
	}
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/spec.md#sit-002
func TestUserAccountLifecycleAndPrivacyUseCanonicalContractVocabulary(t *testing.T) {
	t.Parallel()

	contractGraph, issues, err := compiler.Validate(
		contractsview.Build(t),
		validate.ProfileCommercial,
	)
	if err != nil {
		t.Fatalf("compile commercial ContractGraph: %v", err)
	}
	if len(issues) != 0 {
		t.Fatalf("commercial ContractGraph contains governance failures: %+v", issues)
	}

	account := requireObjectGovernance(t, contractGraph.Governance.Objects, "user.user_account")
	if account.Lifecycle == nil || account.Lifecycle.StateField != "accountState" {
		t.Fatalf("user account lifecycle = %+v, want accountState", account.Lifecycle)
	}
	if !reflect.DeepEqual(
		account.Lifecycle.States,
		[]string{"anonymous", "active", "suspended", "closed"},
	) {
		t.Fatalf("user account lifecycle states = %v", account.Lifecycle.States)
	}
	if account.Privacy == nil || account.Privacy.Aggregate != "UserAccount" {
		t.Fatalf("user account privacy owner = %+v", account.Privacy)
	}
	for _, field := range []string{"birthDate", "region"} {
		if !contains(account.Privacy.AppLogFields, field) {
			t.Fatalf("privacy app-log policy does not bind canonical field %q", field)
		}
	}
	for _, target := range []string{
		"Persona",
		"CredentialBinding",
		"DeviceRegistration",
		"UserSettings",
	} {
		if !contains(account.Privacy.DeletionTargets, target) {
			t.Fatalf("privacy deletion cascade does not bind canonical object %q", target)
		}
	}

	accountState := requireEnum(t, contractGraph.Governance.Enums, "AccountState")
	if !reflect.DeepEqual(
		accountState.Values,
		[]string{"anonymous", "active", "suspended", "closed"},
	) {
		t.Fatalf("AccountState values = %v", accountState.Values)
	}
	for _, definition := range contractGraph.Governance.Enums {
		if definition.Name == "UserStatus" {
			t.Fatalf("retired UserStatus enum returned from %s", definition.SourcePath)
		}
	}
}

func requireObjectGovernance(
	t *testing.T,
	objects []ast.ObjectGovernance,
	objectID string,
) ast.ObjectGovernance {
	t.Helper()
	for _, object := range objects {
		if object.ObjectID == objectID {
			return object
		}
	}
	t.Fatalf("ContractGraph governance object %q not found", objectID)
	return ast.ObjectGovernance{}
}

func requireEnum(
	t *testing.T,
	definitions []ast.EnumDefinition,
	name string,
) ast.EnumDefinition {
	t.Helper()
	for _, definition := range definitions {
		if definition.Name == name {
			return definition
		}
	}
	t.Fatalf("ContractGraph enum %q not found", name)
	return ast.EnumDefinition{}
}

func contains(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}
