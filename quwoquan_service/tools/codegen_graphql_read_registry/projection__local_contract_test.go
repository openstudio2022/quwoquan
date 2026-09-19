// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

func projectionFixture(t *testing.T) (Options, *contractcodegen.Source, string) {
	t.Helper()
	root := t.TempDir()
	queryPath := writeFixture(t, root, "persisted_queries/detail.graphql", detailQuery)
	options := Options{
		SchemaPath:      writeFixture(t, root, "schema.graphqls", detailSchema),
		MetadataPath:    writeMetadata(t, root, collectionMetadata("persisted_queries/detail.graphql")),
		CandidateDigest: testCandidateDigest,
	}
	source, err := sourceForTest(t, options)
	if err != nil {
		t.Fatal(err)
	}
	return options, source, queryPath
}

func TestGenerateUsesOwnerDocumentWithoutReadingDeploymentCopy(t *testing.T) {
	t.Parallel()
	for _, state := range []string{"stale", "missing"} {
		t.Run(state, func(t *testing.T) {
			options, source, queryPath := projectionFixture(t)
			if state == "missing" {
				if err := os.Remove(queryPath); err != nil {
					t.Fatal(err)
				}
			} else {
				writeFixture(t, filepath.Dir(options.MetadataPath), "persisted_queries/detail.graphql", "invalid old deployment copy")
			}
			outputs, err := generateWithSource(options, source)
			if err != nil {
				t.Fatalf("canonical source generation: %v", err)
			}
			entry := decodeRegistry(t, outputs.registry).Entries[0]
			if entry.SHA256Hash != strings.TrimPrefix(digestBytes([]byte(detailQuery)), "sha256:") || entry.Cost.Complexity != 13 {
				t.Fatalf("registry not derived from owner bytes: %+v", entry)
			}
		})
	}
}

func TestGenerateRejectsMissingOwnerDocumentDespiteDeploymentCopy(t *testing.T) {
	t.Parallel()
	options, source, _ := projectionFixture(t)
	ownerPath := filepath.Join(filepath.Dir(options.MetadataPath), "owner-metadata", filepath.FromSlash(source.Graph().Sources[0].Path))
	if err := os.Remove(ownerPath); err != nil {
		t.Fatal(err)
	}
	_, err := generateWithSource(options, source)
	if err == nil || !strings.Contains(err.Error(), "object-owned persisted document") {
		t.Fatalf("missing canonical document error=%v", err)
	}
}

func TestGenerateRejectsOwnerHashDriftDespiteMatchingDeploymentCopy(t *testing.T) {
	t.Parallel()
	options, source, _ := projectionFixture(t)
	source.Graph().Documents[0].Content = bytes.ReplaceAll(
		source.Graph().Documents[0].Content,
		[]byte(source.Graph().Sources[0].SHA256), []byte(strings.Repeat("0", 64)),
	)
	_, err := generateWithSource(options, source)
	if err == nil || !strings.Contains(err.Error(), "sha256Hash drift") {
		t.Fatalf("owner hash drift error=%v", err)
	}
}

func TestWriteOutputsProjectsAndChecksExactOwnerBytes(t *testing.T) {
	t.Parallel()
	options, source, queryPath := projectionFixture(t)
	outputs, err := generateWithSource(options, source)
	if err != nil {
		t.Fatal(err)
	}
	registryPath := filepath.Join(t.TempDir(), "registry.json")
	if err := writeOutputs(registryPath, outputs, false); err != nil {
		t.Fatal(err)
	}
	if err := writeOutputs(registryPath, outputs, true); err != nil {
		t.Fatalf("current outputs: %v", err)
	}
	for _, state := range []string{"stale", "missing"} {
		t.Run(state, func(t *testing.T) {
			if state == "missing" {
				if err := os.Remove(queryPath); err != nil {
					t.Fatal(err)
				}
			} else {
				if err := os.WriteFile(queryPath, []byte("stale deployment copy"), 0o600); err != nil {
					t.Fatal(err)
				}
			}
			if err := writeOutputs(registryPath, outputs, true); err == nil || !strings.Contains(err.Error(), queryPath) {
				t.Fatalf("check must reject %s document: %v", state, err)
			}
			if current, err := os.ReadFile(queryPath); state == "missing" && !os.IsNotExist(err) || state == "stale" && string(current) != "stale deployment copy" {
				t.Fatal("check mode mutated deployment copy")
			}
			if err := writeOutputs(registryPath, outputs, false); err != nil {
				t.Fatal(err)
			}
			current, err := os.ReadFile(queryPath)
			if err != nil || !bytes.Equal(current, []byte(detailQuery)) {
				t.Fatalf("projected owner bytes differ: %v", err)
			}
			if err := writeOutputs(registryPath, outputs, true); err != nil {
				t.Fatal(err)
			}
		})
	}
}
