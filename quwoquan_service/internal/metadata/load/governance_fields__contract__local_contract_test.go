package load

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-002
func TestFieldsGovernanceRejectsNestedEnumSecondTruth(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	path := filepath.Join(root, "user", "account", "user_account", "fields.yaml")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir fields owner: %v", err)
	}
	const source = `entities:
  LoginOneTapResult:
    fields:
      - name: state
        type: enum
        enum_ref: OneTapLoginHintState
    enums:
      OneTapLoginHintState:
        values: [registered, new_phone, unavailable]
`
	if err := os.WriteFile(path, []byte(source), 0o644); err != nil {
		t.Fatalf("write fields fixture: %v", err)
	}

	_, _, _, err := loadFieldsGovernance(
		root,
		path,
		ast.Object{
			ID:     "user.user_account",
			Domain: "user",
			Name:   "UserAccount",
		},
	)
	if err == nil || !strings.Contains(err.Error(), "nested enums declaration") {
		t.Fatalf("nested enum declaration error = %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-002
func TestFieldsGovernanceAllowsExplicitTopLevelObjectEnumOwner(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	path := filepath.Join(root, "user", "account", "user_account", "fields.yaml")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir fields owner: %v", err)
	}
	const source = `fields:
  - name: state
    type: enum
    enum_ref: AccountState
enums:
  AccountState:
    values: [active, suspended, closed]
`
	if err := os.WriteFile(path, []byte(source), 0o644); err != nil {
		t.Fatalf("write fields fixture: %v", err)
	}

	_, _, enums, err := loadFieldsGovernance(
		root,
		path,
		ast.Object{
			ID:     "user.user_account",
			Domain: "user",
			Name:   "UserAccount",
		},
	)
	if err != nil {
		t.Fatalf("load top-level object enum: %v", err)
	}
	if len(enums) != 1 || enums[0].Name != "AccountState" {
		t.Fatalf("object-owned enums = %+v", enums)
	}
}
