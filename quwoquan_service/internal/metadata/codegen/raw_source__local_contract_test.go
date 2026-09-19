// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
package codegen

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
)

func TestRawFileReadsLoaderSourceBytesWithoutJSONDocument(t *testing.T) {
	root := t.TempDir()
	content := []byte("query Detail($id: ID!) { detail(id: $id) { title } }\n")
	if err := os.WriteFile(filepath.Join(root, "detail.graphql"), content, 0o600); err != nil {
		t.Fatal(err)
	}
	catalog, err := load.Load(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(catalog.Sources) != 1 || len(catalog.Documents) != 0 {
		t.Fatalf("raw GraphQL must only enter Sources: sources=%v documents=%v", catalog.Sources, catalog.Documents)
	}
	source := NewSourceFromGraph(root, &graph.ContractGraph{Sources: catalog.Sources, Documents: catalog.Documents})
	actual, err := source.RawFile("detail.graphql")
	if err != nil || !bytes.Equal(actual, content) {
		t.Fatalf("raw source bytes=%q error=%v", actual, err)
	}
	if err := os.WriteFile(filepath.Join(root, "detail.graphql"), append(content, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := source.RawFile("detail.graphql"); err == nil || !strings.Contains(err.Error(), "SHA256 drift") {
		t.Fatalf("source drift error=%v", err)
	}
}

func TestRawFileRejectsUnboundMissingAndEscapingInputs(t *testing.T) {
	for _, test := range []string{"unbound", "duplicate", "missing", "symlink", "parent escape", "absolute", "digest drift"} {
		t.Run(test, func(t *testing.T) {
			root := t.TempDir()
			content := []byte("query Detail { detail }\n")
			path := "detail.graphql"
			fullPath := filepath.Join(root, path)
			if err := os.WriteFile(fullPath, content, 0o600); err != nil {
				t.Fatal(err)
			}
			digest := sha256.Sum256(content)
			binding := ast.SourceDigest{Path: path, SHA256: hex.EncodeToString(digest[:])}
			source := NewSourceFromGraph(root, &graph.ContractGraph{Sources: []ast.SourceDigest{binding}})
			switch test {
			case "unbound":
				source.Graph().Sources = nil
			case "duplicate":
				source.Graph().Sources = append(source.Graph().Sources, binding)
			case "missing", "symlink":
				if err := os.Remove(fullPath); err != nil {
					t.Fatal(err)
				}
				if test == "symlink" {
					outside := filepath.Join(t.TempDir(), "detail.graphql")
					if err := os.WriteFile(outside, content, 0o600); err != nil {
						t.Fatal(err)
					}
					if err := os.Symlink(outside, fullPath); err != nil {
						t.Fatal(err)
					}
				}
			case "parent escape":
				path = "../detail.graphql"
			case "absolute":
				path = fullPath
			case "digest drift":
				source.Graph().Sources[0].SHA256 = strings.Repeat("0", 64)
			}
			if _, err := source.RawFile(path); err == nil {
				t.Fatalf("accepted %s raw source", test)
			}
		})
	}
}
