package load

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestObjectModelVersionIsInternalContractGraphMetadata(t *testing.T) {
	metadataDir := t.TempDir()
	objectPath := filepath.Join(
		metadataDir,
		"sample",
		"context",
		"widget",
		"object.yaml",
	)
	if err := os.MkdirAll(filepath.Dir(objectPath), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(
		objectPath,
		[]byte("kind: aggregate_root\nmodel_version: \"2.0\"\n"),
		0o600,
	); err != nil {
		t.Fatal(err)
	}

	object, err := loadObject(metadataDir, objectPath)
	if err != nil {
		t.Fatalf("load object model version: %v", err)
	}
	if object.ModelVersion != "2.0" {
		t.Fatalf("model version = %q, want 2.0", object.ModelVersion)
	}
}

func TestObjectModelVersionRejectsUnquotedYamlNumber(t *testing.T) {
	metadataDir := t.TempDir()
	objectPath := filepath.Join(
		metadataDir,
		"sample",
		"context",
		"widget",
		"object.yaml",
	)
	if err := os.MkdirAll(filepath.Dir(objectPath), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(
		objectPath,
		[]byte("kind: aggregate_root\nmodel_version: 2.0\n"),
		0o600,
	); err != nil {
		t.Fatal(err)
	}

	_, err := loadObject(metadataDir, objectPath)
	if err == nil || !strings.Contains(err.Error(), "quoted major.minor") {
		t.Fatalf("unquoted model version error = %v", err)
	}
}
