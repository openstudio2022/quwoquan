package main

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestRemoveRetiredGeneratedOutputs_RemovesFixtureIdentityOutput(t *testing.T) {
	appDir := t.TempDir()
	retired := filepath.Join(
		appDir,
		"lib",
		"cloud",
		"user",
		"generated",
		"prefab_user_metadata.g.dart",
	)
	if err := os.MkdirAll(filepath.Dir(retired), 0o755); err != nil {
		t.Fatalf("create generated directory: %v", err)
	}
	if err := os.WriteFile(retired, []byte("retired fixture identity"), 0o600); err != nil {
		t.Fatalf("write retired generated output: %v", err)
	}

	removeRetiredGeneratedOutputs(appDir)

	if _, err := os.Stat(retired); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("retired fixture identity output must be removed, stat error: %v", err)
	}
}
