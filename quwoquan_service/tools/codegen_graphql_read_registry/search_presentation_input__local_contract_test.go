// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-006
package main

import (
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"testing"

	"github.com/vektah/gqlparser/v2"
	"github.com/vektah/gqlparser/v2/ast"
	"quwoquan_service/internal/testsupport/contractsview"
	"quwoquan_service/tools/internal/presentationcontract"
)

func TestSearchPresentationInputMatchesSharedCanonicalType(t *testing.T) {
	root := filepath.Join("..", "..")
	shared, err := os.ReadFile(filepath.Join(root, "contracts/metadata/_shared/types.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	model, err := presentationcontract.Load(shared)
	if err != nil {
		t.Fatal(err)
	}
	sdl, err := os.ReadFile(filepath.Join(root, "services/api-edge/resources/policies/graphql_read/schema.graphqls"))
	if err != nil {
		t.Fatal(err)
	}
	schema, err := gqlparser.LoadSchema(&ast.Source{Name: "schema.graphqls", Input: string(sdl)})
	if err != nil {
		t.Fatal(err)
	}
	input := schema.Types["SearchPageInput"].Fields.ForName("clientPresentationContract")
	if input == nil || input.Type.String() != presentationcontract.TypeName || input.DefaultValue != nil {
		t.Fatal("SearchPage must use nullable canonical capability input without an Edge default")
	}
	capability := schema.Types[presentationcontract.TypeName]
	if capability == nil || capability.Kind != ast.InputObject || len(capability.Fields) != len(model.Fields)+1 {
		t.Fatal("capability input must contain exactly canonical four collections and digest")
	}
	for _, field := range model.Fields {
		got := capability.Fields.ForName(field.Name)
		if got == nil || got.Type.String() != "["+field.EnumRef+"!]!" || got.DefaultValue != nil {
			t.Fatalf("capability field %s is not a required canonical enum collection", field.Name)
		}
		enum := schema.Types[field.EnumRef]
		if enum == nil || enum.Kind != ast.Enum {
			t.Fatalf("canonical enum %s missing", field.EnumRef)
		}
		members := make([]string, 0, len(enum.EnumValues))
		for _, value := range enum.EnumValues {
			members = append(members, value.Name)
		}
		sort.Strings(members)
		if !reflect.DeepEqual(members, field.Values) {
			t.Fatalf("%s SDL values=%v canonical=%v", field.EnumRef, members, field.Values)
		}
	}
	digest := capability.Fields.ForName("contractDigest")
	if digest == nil || digest.Type.String() != "String!" || digest.DefaultValue != nil {
		t.Fatal("canonical digest must be explicitly supplied")
	}
	// 能力只用于内容列表项准入；搜索仍是跨对象结果，不能收窄为 Post 列表。
	for _, objectType := range []string{"CIRCLE", "CIRCLE_GROUP", "ENTITY_HOMEPAGE", "LOCATION_PLACE", "USER_PROFILE"} {
		if schema.Types["SearchPageObjectType"].EnumValues.ForName(objectType) == nil {
			t.Fatalf("Search lost non-content object type %s", objectType)
		}
	}
}

func TestSearchPresentationInputCompilesRegistry(t *testing.T) {
	root := filepath.Join("..", "..")
	policyRoot := filepath.Join(root, "services/api-edge/resources/policies/graphql_read")
	encoded, err := Generate(Options{
		SchemaPath:      filepath.Join(policyRoot, "schema.graphqls"),
		MetadataPath:    filepath.Join(policyRoot, "query_metadata.json"),
		MetadataDir:     contractsview.Build(t),
		CandidateDigest: testCandidateDigest,
	})
	if err != nil {
		t.Fatalf("compile canonical SearchPage registry in memory: %v", err)
	}
	registry := decodeRegistry(t, encoded)
	for _, entry := range registry.Entries {
		if entry.OperationName == "SearchPage" {
			return
		}
	}
	t.Fatal("compiled registry lost reachable SearchPage")
}
