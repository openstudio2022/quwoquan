package main

import (
	"encoding/json"
	"path/filepath"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/spec.md#req-001
func TestServiceResponseUsesScopedSharedTypes(t *testing.T) {
	t.Parallel()
	global := ast.TypeDefinition{Name: "SharedSnapshot", OwnerLevel: ast.EnumOwnerGlobal, SourcePath: "_shared/types.yaml"}
	service := ast.TypeDefinition{Name: "SharedSnapshot", OwnerLevel: ast.EnumOwnerService, Domain: "content", SourcePath: "content/_shared/types.yaml"}
	wrongService := service
	wrongService.Domain = "entity"
	wrongService.SourcePath = "entity/_shared/types.yaml"
	objectLocal := ast.TypeDefinition{Name: "SharedSnapshot", OwnerLevel: ast.EnumOwnerObject, Domain: "content", ObjectID: "content.other", SourcePath: "content/content/other/fields.yaml"}
	conflictingService := service
	conflictingService.SourcePath = "content/_shared/enums.yaml"

	for _, testCase := range []struct {
		name      string
		types     []ast.TypeDefinition
		wantIssue string
	}{
		{name: "global shared", types: []ast.TypeDefinition{global}},
		{name: "same service shared", types: []ast.TypeDefinition{service}},
		{name: "service takes precedence over global", types: []ast.TypeDefinition{global, service}},
		{name: "foreign service does not shadow global", types: []ast.TypeDefinition{wrongService, global}},
		{name: "missing", wantIssue: "not a known"},
		{name: "wrong service scope", types: []ast.TypeDefinition{wrongService}, wantIssue: "not a known"},
		{name: "object type is not shared", types: []ast.TypeDefinition{objectLocal}, wantIssue: "not a known"},
		{name: "duplicate global", types: []ast.TypeDefinition{global, global}, wantIssue: "ambiguous shared type"},
		{name: "duplicate service", types: []ast.TypeDefinition{service, conflictingService}, wantIssue: "ambiguous shared type"},
		{name: "duplicate service cannot fall through to global", types: []ast.TypeDefinition{global, service, conflictingService}, wantIssue: "ambiguous shared type"},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			for _, kind := range []string{"object", "page"} {
				for _, responseKey := range []string{"response_entity", "response_body"} {
					v, dir := sharedResponseValidator(t, testCase.types, kind, responseKey)
					v.validateServiceEntities(dir, "content/content/post", "Post", nil)
					if testCase.wantIssue != "" {
						if !containsIssue(v.errors, testCase.wantIssue) {
							t.Fatalf("%s/%s errors = %v, want %q", kind, responseKey, v.errors, testCase.wantIssue)
						}
					} else if len(v.errors) != 0 || len(v.warnings) != 0 {
						t.Fatalf("%s/%s errors = %v, warnings = %v", kind, responseKey, v.errors, v.warnings)
					}
				}
			}
		})
	}
}

func sharedResponseValidator(t *testing.T, types []ast.TypeDefinition, kind, responseKey string) (*validator, string) {
	t.Helper()
	root := t.TempDir()
	objectDir := "content/content/post"
	operations, err := json.Marshal(map[string]any{"api_routes": []map[string]string{{
		"operation": "ReadSnapshot", "response_body_kind": kind, responseKey: "SharedSnapshot",
	}}})
	if err != nil {
		t.Fatal(err)
	}
	contractGraph := &graph.ContractGraph{
		Governance: ast.MetadataGovernance{Types: types},
		Documents: []ast.SourceDocument{
			{Path: objectDir + "/operations.yaml", Content: operations},
			{Path: objectDir + "/fields.yaml", Content: json.RawMessage(`{"entity":"Post"}`)},
		},
	}
	return &validator{metadataDir: root, source: contractcodegen.NewSourceFromGraph(root, contractGraph)}, filepath.Join(root, filepath.FromSlash(objectDir))
}
