// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001

package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestRunEmitsDeterministicTypedStorageView(t *testing.T) {
	t.Parallel()
	path := writeStorageFixture(t, `backend: postgresql
role: aggregate_store
description: deterministic fixture
tables:
  zeta:
    entity: Zeta
    pk: [id]
    columns:
      - name: id
        type: text
        constraints: [PK, NOT_NULL]
  alpha:
    entity: Alpha
    pk: [id]
    columns:
      - name: id
        type: text
        constraints: [PK, NOT_NULL]
`)

	var firstStdout, firstStderr bytes.Buffer
	if code := run([]string{"--input", path}, &firstStdout, &firstStderr); code != 0 {
		t.Fatalf("first run code = %d, stderr = %q", code, firstStderr.String())
	}
	if firstStderr.Len() != 0 {
		t.Fatalf("first run stderr = %q", firstStderr.String())
	}
	if !bytes.HasSuffix(firstStdout.Bytes(), []byte("\n")) {
		t.Fatalf("stdout must end with one newline: %q", firstStdout.String())
	}
	if !json.Valid(firstStdout.Bytes()) {
		t.Fatalf("stdout is not JSON: %q", firstStdout.String())
	}
	var document ast.StorageDocument
	if err := json.Unmarshal(firstStdout.Bytes(), &document); err != nil {
		t.Fatal(err)
	}
	if document.Backend != "postgresql" || document.Role != "aggregate_store" {
		t.Fatalf("unexpected typed view: %#v", document)
	}
	if len(document.Tables) != 2 || document.Tables["alpha"].Entity != "Alpha" {
		t.Fatalf("unexpected tables: %#v", document.Tables)
	}

	var secondStdout, secondStderr bytes.Buffer
	if code := run([]string{"--input", path}, &secondStdout, &secondStderr); code != 0 {
		t.Fatalf("second run code = %d, stderr = %q", code, secondStderr.String())
	}
	if !bytes.Equal(firstStdout.Bytes(), secondStdout.Bytes()) {
		t.Fatalf("view is not byte deterministic\nfirst: %s\nsecond: %s", firstStdout.Bytes(), secondStdout.Bytes())
	}
}

func TestRunFailsClosed(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name       string
		args       func(t *testing.T) []string
		wantStderr string
	}{
		{
			name: "missing input flag",
			args: func(t *testing.T) []string {
				return nil
			},
			wantStderr: "--input is required",
		},
		{
			name: "missing file",
			args: func(t *testing.T) []string {
				return []string{"--input", filepath.Join(t.TempDir(), "storage.yaml")}
			},
			wantStderr: "read ",
		},
		{
			name: "unknown field",
			args: func(t *testing.T) []string {
				path := writeStorageFixture(t, "backend: postgresql\nrole: aggregate_store\nunknown_key: true\n")
				return []string{"--input", path}
			},
			wantStderr: "field unknown_key not found",
		},
		{
			name: "trailing document",
			args: func(t *testing.T) []string {
				path := writeStorageFixture(t, "backend: postgresql\nrole: aggregate_store\n---\nbackend: redis\nrole: cache\n")
				return []string{"--input", path}
			},
			wantStderr: "exactly one YAML document",
		},
		{
			name: "noncanonical filename",
			args: func(t *testing.T) []string {
				return []string{"--input", filepath.Join(t.TempDir(), "storage-copy.yaml")}
			},
			wantStderr: "must name storage.yaml",
		},
		{
			name: "positional argument",
			args: func(t *testing.T) []string {
				return []string{"--input", filepath.Join(t.TempDir(), "storage.yaml"), "extra"}
			},
			wantStderr: "positional arguments are forbidden",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			var stdout, stderr bytes.Buffer
			if code := run(test.args(t), &stdout, &stderr); code != 2 {
				t.Fatalf("code = %d, want 2; stderr = %q", code, stderr.String())
			}
			if stdout.Len() != 0 {
				t.Fatalf("stdout must remain empty on failure: %q", stdout.String())
			}
			if !strings.Contains(stderr.String(), test.wantStderr) {
				t.Fatalf("stderr = %q, want substring %q", stderr.String(), test.wantStderr)
			}
		})
	}
}

func writeStorageFixture(t *testing.T, source string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "storage.yaml")
	if err := os.WriteFile(path, []byte(source), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}
