// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/spec.md#sit-002
package local_contract

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

type profileBoundaryFieldsDocument struct {
	Fields []struct {
		Name string `yaml:"name"`
		Role string `yaml:"role"`
	} `yaml:"fields"`
}

type profileBoundaryOperationsDocument struct {
	APIRoutes []struct {
		Operation   string `yaml:"operation"`
		Application struct {
			Kind            string `yaml:"kind"`
			AggregateOwner  string `yaml:"aggregate_owner"`
			MutationTarget  string `yaml:"mutation_target"`
			InvariantTarget string `yaml:"invariant_target"`
		} `yaml:"application"`
	} `yaml:"api_routes"`
}

func TestProfileWriteAuthorityAndAccountProjectionStaySingleTrack(t *testing.T) {
	contractsRoot := filepath.Join(userServiceRoot(t), "contracts")
	accountFields := readProfileBoundaryFields(
		t,
		filepath.Join(contractsRoot, "account", "user_account", "fields.yaml"),
	)
	personaFields := readProfileBoundaryFields(
		t,
		filepath.Join(contractsRoot, "persona_management", "persona", "fields.yaml"),
	)

	// These pairs intentionally compare semantic counterparts rather than wire
	// aliases. Persona owns the writable public profile; UserAccount may only
	// materialize the active Persona snapshot for account-scoped readers.
	profileFieldPairs := map[string]string{
		"displayName":            "nickname",
		"nicknameCustomized":     "nicknameCustomized",
		"avatarMediaAssetId":     "avatarAssetId",
		"avatarUrl":              "avatarUrl",
		"avatarVersion":          "avatarVersion",
		"backgroundMediaAssetId": "backgroundAssetId",
		"backgroundUrl":          "backgroundUrl",
		"bio":                    "bio",
		"identityTags":           "identityTags",
		"gender":                 "gender",
		"birthDate":              "birthDate",
		"region":                 "region",
		"regionTagRef":           "regionTagRef",
	}
	for personaField, accountProjection := range profileFieldPairs {
		if role := personaFields[personaField]; role != "authoritative_state" {
			t.Errorf(
				"Persona profile field %s role = %q, want authoritative_state",
				personaField,
				role,
			)
		}
		if role := accountFields[accountProjection]; role != "projection" {
			t.Errorf(
				"UserAccount profile field %s role = %q, want projection",
				accountProjection,
				role,
			)
		}
	}

	accountOperations := readProfileBoundaryOperations(
		t,
		filepath.Join(contractsRoot, "account", "user_account", "operations.yaml"),
	)
	personaOperations := readProfileBoundaryOperations(
		t,
		filepath.Join(contractsRoot, "persona_management", "persona", "operations.yaml"),
	)

	for _, route := range accountOperations.APIRoutes {
		if route.Operation == "UpdateUserProfile" {
			t.Error("UserAccount must not redeclare the Persona-owned UpdateUserProfile command")
		}
	}

	updateProfileDeclarations := 0
	for _, route := range personaOperations.APIRoutes {
		if route.Operation != "UpdateUserProfile" {
			continue
		}
		updateProfileDeclarations++
		if route.Application.Kind != "command" ||
			route.Application.AggregateOwner != "Persona" ||
			route.Application.MutationTarget != "Persona" ||
			route.Application.InvariantTarget != "Persona" {
			t.Errorf(
				"UpdateUserProfile application binding = %+v, want Persona command owner",
				route.Application,
			)
		}
	}
	if updateProfileDeclarations != 1 {
		t.Fatalf(
			"UpdateUserProfile declarations = %d, want exactly one Persona-owned route",
			updateProfileDeclarations,
		)
	}
}

func readProfileBoundaryFields(t *testing.T, path string) map[string]string {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	var document profileBoundaryFieldsDocument
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
	roles := make(map[string]string, len(document.Fields))
	for _, field := range document.Fields {
		roles[field.Name] = field.Role
	}
	return roles
}

func readProfileBoundaryOperations(
	t *testing.T,
	path string,
) profileBoundaryOperationsDocument {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	var document profileBoundaryOperationsDocument
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
	return document
}
