package requestbinding

import (
	"encoding/json"
	"quwoquan_service/internal/metadata/ast"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md
func TestJSONQueryCanonicalSHA256Format(t *testing.T) {
	schema := &Schema{Type: "string"}
	if err := schema.applyFormat("canonical_sha256"); err != nil {
		t.Fatal(err)
	}
	if schema.Pattern != "^sha256:[0-9a-f]{64}$" || *schema.MinLength != 71 || *schema.MaxLength != 71 {
		t.Fatalf("digest schema=%+v", schema)
	}
	for _, test := range []struct{ kind, format string }{{"integer", "canonical_sha256"}, {"array", "canonical_sha256"}, {"string", "unknown"}} {
		if err := (&Schema{Type: test.kind}).applyFormat(test.format); err == nil {
			t.Fatalf("accepted %#v", test)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md
func TestJSONQueryAuthorityChecksOnlyReachableClosure(t *testing.T) {
	for _, test := range []struct {
		name, duplicate, typeName string
		reject                    bool
	}{
		{"unrelated-conflict", `{"fields":[{"name":"x","type":"bool"}]}`, "Unused", false},
		{"reachable-conflict", `{"fields":[{"name":"label","type":"string","constraints":["MAX_LENGTH_9"]}]}`, "Filter", true},
		{"reachable-equivalent", `{"fields":[{"name":"label","type":"string","constraints":["MAX_LENGTH_8"]}]}`, "Filter", false},
		{"request-root-conflict", `{"fields":[{"name":"filter","type":"Other"}]}`, "Request", true},
	} {
		t.Run(test.name, func(t *testing.T) {
			document := `{"types":{"Request":{"fields":[{"name":"filter","type":"Filter"}]},"Filter":{"fields":[{"name":"label","type":"string","constraints":["MAX_LENGTH_8"]}]},"Unused":{"fields":[{"name":"x","type":"int"}]}},"members":{"` + test.typeName + `":` + test.duplicate + `}}`
			sources := []ast.SourceDocument{{Path: "sample/context/item/fields.yaml", Content: json.RawMessage(document)}}
			_, err := Resolve(sources, ast.Operation{SourcePath: "sample/context/item/operations.yaml", RequestEntity: "Request"}, ast.RequestBinding{Name: "filter", Field: "filter", Encoding: "json", MaxBytes: 128})
			if test.reject {
				if err == nil || !strings.Contains(err.Error(), "ambiguous JSON query type "+test.typeName) {
					t.Fatalf("want reachable conflict, got %v", err)
				}
			} else if err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestJSONQueryEnumAuthorityChecksOnlyReachableClosure(t *testing.T) {
	for _, test := range []struct {
		name, enumName, values string
		reject                 bool
	}{
		{"unrelated-conflict", "Unused", `["other"]`, false},
		{"reachable-conflict", "Kind", `["other"]`, true},
		{"reachable-equivalent", "Kind", `["one"]`, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			sources := []ast.SourceDocument{
				{Path: "sample/context/item/fields.yaml", Content: json.RawMessage(`{"types":{"Request":{"fields":[{"name":"filter","type":"Filter"}]},"Filter":{"fields":[{"name":"nested","type":"Nested"}]},"Nested":{"fields":[{"name":"kind","type":"enum","enum_ref":"Kind"}]}},"enums":{"Kind":["one"],"Unused":["initial"]}}`)},
				{Path: "_shared/types.yaml", Content: json.RawMessage(`{"enums":{"` + test.enumName + `":` + test.values + `}}`)},
			}
			_, err := Resolve(sources, ast.Operation{SourcePath: "sample/context/item/operations.yaml", RequestEntity: "Request"}, ast.RequestBinding{Name: "filter", Field: "filter", Encoding: "json", MaxBytes: 128})
			if test.reject {
				if err == nil || !strings.Contains(err.Error(), "ambiguous JSON query enum Kind") {
					t.Fatalf("wanted reachable enum conflict: %v", err)
				}
			} else if err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestJSONQuerySchemaUsesTypedSourceAndBounds(t *testing.T) {
	documents := []ast.SourceDocument{{Path: "sample/context/item/fields.yaml", Content: json.RawMessage(`{"types":{"Request":{"fields":[{"name":"filter","type":"Filter"}]},"Filter":{"fields":[{"name":"label","type":"string","constraints":["MAX_LENGTH_8"]},{"name":"kinds","type":"[]Kind","constraints":["MAX_ITEMS_2"]}]}},"enums":{"Kind":{"values":["one","two"]}}}`)}}
	operation := ast.Operation{SourcePath: "sample/context/item/operations.yaml", RequestEntity: "Request"}
	binding := ast.RequestBinding{Name: "filter", Field: "filter", Encoding: "json", MaxBytes: 128}
	schema, err := Resolve(documents, operation, binding)
	if err != nil {
		t.Fatal(err)
	}
	if schema.Type != "object" || schema.AdditionalProperties == nil || *schema.AdditionalProperties || *schema.Properties["label"].MaxLength != 8 || len(schema.Properties["kinds"].Items.Enum) != 2 {
		t.Fatalf("wrong schema: %+v", schema)
	}
	for _, test := range []struct{ from, to, want string }{
		{`"MAX_LENGTH_8"`, `"NOT_NULL"`, "length boundary"},
		{`"MAX_ITEMS_2"`, `"NOT_NULL"`, "MAX_ITEMS"},
		{`"type":"Filter"`, `"type":"string","constraints":["MAX_LENGTH_8"]`, "typed object"},
		{`"MAX_LENGTH_8"`, `"FUTURE_CONSTRAINT"`, "unsupported JSON query constraint"},
	} {
		changed := append([]ast.SourceDocument(nil), documents...)
		changed[0].Content = json.RawMessage(strings.Replace(string(documents[0].Content), test.from, test.to, 1))
		if _, err := Resolve(changed, operation, binding); err == nil || !strings.Contains(err.Error(), test.want) {
			t.Errorf("%s: %v", test.want, err)
		}
	}
	wireBounds := append([]ast.SourceDocument(nil), documents...)
	wireBounds[0].Content = json.RawMessage(strings.Replace(string(documents[0].Content), `"constraints":["MAX_ITEMS_2"]`, `"constraints":["NOT_NULL"],"max_items":2`, 1))
	if _, err := Resolve(wireBounds, operation, binding); err != nil {
		t.Fatalf("canonical max_items not projected: %v", err)
	}
	binding.MaxBytes = 0
	if _, err := Resolve(documents, operation, binding); err == nil {
		t.Fatal("accepted absent max_bytes")
	}
}
