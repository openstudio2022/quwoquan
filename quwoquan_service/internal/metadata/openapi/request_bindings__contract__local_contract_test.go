package openapi

import (
	"encoding/json"
	"quwoquan_service/internal/metadata/graph"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md
func TestJSONQueryOpenAPIProjectsObjectWithoutBody(t *testing.T) {
	operation := queryOperation("sample.item.Lookup", "Lookup", "sample", "sample.item", "/sample/items", "Result", "object")
	operation.SourcePath = "sample/context/item/operations.yaml"
	operation.RequestEntity = "Request"
	operation.RequestBodyKind = "none"
	operation.RequestBindings = &ast.RequestBindings{Query: []ast.RequestBinding{{Name: "filter", Field: "filter", Encoding: "json", MaxBytes: 80}}}
	documents := []ast.SourceDocument{{Path: "sample/context/item/fields.yaml", Content: json.RawMessage(`{"types":{"Request":{"fields":[{"name":"filter","type":"Filter"}]},"Filter":{"fields":[{"name":"label","type":"string","constraints":["MAX_LENGTH_8"]}]}}}`)}}
	snapshots, err := Generate(&graph.ContractGraph{Operations: []ast.Operation{operation}, Documents: documents})
	if err != nil {
		t.Fatal(err)
	}
	output := string(snapshots[0].Content)
	for _, fragment := range []string{"application/json:", "maxLength: 8", "additionalProperties: false", "x-max-bytes: 80"} {
		if !strings.Contains(output, fragment) {
			t.Fatalf("missing %s: %s", fragment, output)
		}
	}
	if strings.Contains(output, "requestBody:") {
		t.Fatal("JSON query added an HTTP body")
	}
	decoded := decodeSnapshot(t, snapshots[0])
	parameter := operationAt(t, decoded, "/sample/items", "get")["parameters"].([]any)[0].(map[string]any)
	if _, exists := parameter["schema"]; exists {
		t.Fatal("parameter content and schema must be mutually exclusive")
	}
}

func TestRequestBindingsGeneratePathAndQueryButNeverInjectedParameters(t *testing.T) {
	required := true
	parameters := requestBindingParameters(ast.Operation{
		PathTemplate: "/content/posts/{postId}",
		RequestBindings: &ast.RequestBindings{
			Path:     []ast.RequestBinding{{Name: "postId", Field: "postId"}},
			Query:    []ast.RequestBinding{{Name: "limit", Field: "limit", Required: &required}},
			Injected: []ast.RequestBinding{{Name: "actorId", Field: "actorId"}},
		},
	})
	if len(parameters) != 2 {
		t.Fatalf("parameters=%+v", parameters)
	}
	if parameters[0].Name != "postId" || parameters[0].In != "path" || !parameters[0].Required {
		t.Fatalf("path parameter=%+v", parameters[0])
	}
	if parameters[1].Name != "limit" || parameters[1].In != "query" || !parameters[1].Required {
		t.Fatalf("query parameter=%+v", parameters[1])
	}
}
