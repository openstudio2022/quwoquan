package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestStandaloneRequestPageIDArtifactIsRetired(t *testing.T) {
	checks := []struct {
		path      string
		forbidden string
	}{
		{path: "main.go", forbidden: "app_request_" + "page_ids.g.dart"},
		{path: "api_metadata_codegen.go", forbidden: "renderStandalone" + "RequestPageIDsDart"},
		{path: "metadata_types.go", forbidden: "Standalone" + "PageIDs"},
	}
	for _, check := range checks {
		source, err := os.ReadFile(check.path)
		if err != nil {
			t.Fatalf("read %s: %v", check.path, err)
		}
		if strings.Contains(string(source), check.forbidden) {
			t.Fatalf("%s still owns retired standalone page ID output %q", check.path, check.forbidden)
		}
	}

	artifact := filepath.Join(
		"..",
		"..",
		"..",
		"quwoquan_app",
		"lib",
		"cloud",
		"runtime",
		"generated",
		"app_request_"+"page_ids.g.dart",
	)
	if _, err := os.Stat(artifact); !os.IsNotExist(err) {
		t.Fatalf("retired standalone page ID artifact still exists at %s: %v", artifact, err)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestRequestContextRetainsDomainOperationPageIDs(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	requestContext, err := readRequestContext(
		filepath.Join(metadataDir, "_shared", "request_context.yaml"),
	)
	if err != nil {
		t.Fatalf("read shared request context: %v", err)
	}
	if got := requestContext.DomainOperationPageIDs["chat"]["SendMessage"]; got != "chat.message.send" {
		t.Fatalf("chat SendMessage page ID = %q, want chat.message.send", got)
	}
}
