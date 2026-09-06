package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// This source-level boundary assertion is intentionally narrow: the executable
// import adapter must not regain any PostgreSQL/Persona write dependency.
func TestReleaseImportStageOnlyHasZeroPostgreSQLPersonaWrites(t *testing.T) {
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../../"))
	paths := []string{
		filepath.Join(root, "internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport/runtime.go"),
		filepath.Join(root, "cmd/release-import/main.go"),
	}
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		text := string(raw)
		for _, forbidden := range []string{"pgxpool", "INSERT INTO user_profiles", "INSERT INTO personas", "personas_outbox", "personas_command_receipts", "CreatorPersonaMaterializer"} {
			if strings.Contains(text, forbidden) {
				t.Fatalf("stage-only importer %s contains forbidden PostgreSQL/Persona write marker %q", path, forbidden)
			}
		}
	}
	if _, err := os.Stat(filepath.Join(root, "cmd/release-import/persona_materializer.go")); !os.IsNotExist(err) {
		t.Fatalf("Persona materializer must be absent, err=%v", err)
	}
}
