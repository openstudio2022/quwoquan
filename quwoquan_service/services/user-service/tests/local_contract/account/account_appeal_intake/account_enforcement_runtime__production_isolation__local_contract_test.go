package local_contract

import (
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"

	operationsecurity "quwoquan_service/generated/operationsecurity"
)

const accountEnforcementTestSupportImport = "quwoquan_service/services/user-service/tests/support"

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-001
func TestAccountEnforcementProductionDescriptorsRemainCommerciallyBlocked(
	t *testing.T,
) {
	wanted := map[string]bool{
		"user.user_account.SuspendAccount": false,
		"user.user_account.RestoreAccount": false,
	}
	for _, descriptor := range operationsecurity.ForDomain("user") {
		if _, tracked := wanted[descriptor.CanonicalOperationID]; !tracked {
			continue
		}
		wanted[descriptor.CanonicalOperationID] = true
		if descriptor.CommercialStatus != "blocked" {
			t.Fatalf(
				"production %s commercialStatus=%q want=blocked until external evidence closes",
				descriptor.CanonicalOperationID,
				descriptor.CommercialStatus,
			)
		}
	}
	for operationID, found := range wanted {
		if !found {
			t.Fatalf("production AccountEnforcement descriptor is absent: %s", operationID)
		}
	}
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-001
func TestAccountEnforcementIntegrationRuntimeCannotEnterProductionComposition(
	t *testing.T,
) {
	serviceRoot := locateServiceModuleRoot(t)
	productionRoot := filepath.Join(serviceRoot, "services")
	err := filepath.WalkDir(productionRoot, func(
		path string,
		entry fs.DirEntry,
		walkErr error,
	) error {
		if walkErr != nil {
			return walkErr
		}
		relative, err := filepath.Rel(productionRoot, path)
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if path != productionRoot && containsPathSegment(relative, "tests") {
				return filepath.SkipDir
			}
			return nil
		}
		if entry.Type().IsRegular() && strings.HasSuffix(entry.Name(), ".go") {
			parsed, err := parser.ParseFile(
				token.NewFileSet(), path, nil, parser.ImportsOnly,
			)
			if err != nil {
				return err
			}
			for _, imported := range parsed.Imports {
				value, err := strconv.Unquote(imported.Path.Value)
				if err != nil {
					return err
				}
				if value == accountEnforcementTestSupportImport {
					t.Errorf(
						"test-only account enforcement runtime imported by production source: %s",
						relative,
					)
				}
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("scan production Go imports: %v", err)
	}
}

func locateServiceModuleRoot(t *testing.T) string {
	t.Helper()
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve account enforcement isolation test path")
	}
	current := filepath.Dir(currentFile)
	for {
		if info, err := os.Stat(filepath.Join(current, "go.mod")); err == nil && !info.IsDir() {
			return current
		}
		parent := filepath.Dir(current)
		if parent == current {
			t.Fatal("quwoquan_service go.mod was not found")
		}
		current = parent
	}
}

func containsPathSegment(path string, expected string) bool {
	for _, segment := range strings.Split(filepath.Clean(path), string(filepath.Separator)) {
		if segment == expected {
			return true
		}
	}
	return false
}
