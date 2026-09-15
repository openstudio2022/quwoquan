package owner

// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
import (
	"encoding/json"
	"github.com/vektah/gqlparser/v2"
	"github.com/vektah/gqlparser/v2/ast"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCollectionEdgeSpecEqualsRealPersistedSelection(t *testing.T) {
	dir, _ := os.Getwd()
	for {
		if _, e := os.Stat(filepath.Join(dir, "go.mod")); e == nil {
			break
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("module root missing")
		}
		dir = parent
	}
	schemaRaw, e := os.ReadFile(filepath.Join(dir, "services/api-edge/resources/policies/graphql_read/schema.graphqls"))
	if e != nil {
		t.Fatal(e)
	}
	schema, e := gqlparser.LoadSchema(&ast.Source{Input: string(schemaRaw)})
	if e != nil {
		t.Fatal(e)
	}
	for _, test := range []struct {
		file       string
		management bool
	}{{"post_collection.graphql", false}, {"post_collection_management.graphql", true}} {
		t.Run(test.file, func(t *testing.T) {
			raw, e := os.ReadFile(filepath.Join(dir, "services/content-service/contracts/content/post_collection/persisted_queries", test.file))
			if e != nil {
				t.Fatal(e)
			}
			q, qe := gqlparser.LoadQuery(schema, string(raw))
			if qe != nil {
				t.Fatal(qe)
			}
			root := q.Operations[0].SelectionSet[0].(*ast.Field)
			spec := collectionResponseSpec(test.management)
			compareEdgeSelection(t, root.SelectionSet, spec)
			value := selectionValue(root.SelectionSet)
			if e := validateObjectResponse(root.Name, value, spec); e != nil {
				t.Fatal(e)
			}
			for _, path := range [][]string{{"name"}, {"members", "title"}} {
				for _, mutation := range []string{"delete", "extra", "rename", "type"} {
					t.Run(strings.Join(path, ".")+mutation, func(t *testing.T) {
						v := selectionValue(root.SelectionSet)
						target := v
						if len(path) == 2 {
							target = v[path[0]].([]any)[0].(map[string]any)
						}
						name := path[len(path)-1]
						switch mutation {
						case "delete":
							delete(target, name)
						case "extra":
							target["unexpected"] = true
						case "rename":
							target["renamed"] = target[name]
							delete(target, name)
						case "type":
							target[name] = true
						}
						if validateObjectResponse(root.Name, v, spec) == nil {
							t.Fatal("response mutation accepted")
						}
					})
				}
			}
			nullable := selectionValue(root.SelectionSet)
			nullable["coverAssetId"] = nil
			if e := validateObjectResponse(root.Name, nullable, spec); e != nil {
				t.Fatal(e)
			}
			nullable["members"] = []any{nil}
			if validateObjectResponse(root.Name, nullable, spec) == nil {
				t.Fatal("null list item accepted")
			}
		})
	}
}
func compareEdgeSelection(t *testing.T, selection ast.SelectionSet, spec objectSpec) {
	t.Helper()
	if len(selection) != len(spec.fields) {
		t.Fatal("Edge field count differs from real document")
	}
	for _, node := range selection {
		field := node.(*ast.Field)
		expected, ok := spec.fields[field.Name]
		if !ok {
			t.Fatalf("Edge missing %s", field.Name)
		}
		typ := field.Definition.Type
		if expected.nullable == typ.NonNull {
			t.Fatalf("nullability %s", field.Name)
		}
		if typ.Elem != nil {
			if expected.kind != responseList || expected.item == nil || expected.item.nullable == typ.Elem.NonNull {
				t.Fatalf("list shape %s", field.Name)
			}
			expected = *expected.item
			typ = typ.Elem
		}
		if len(field.SelectionSet) > 0 {
			if expected.kind != responseObject || expected.object == nil {
				t.Fatal("object shape")
			}
			compareEdgeSelection(t, field.SelectionSet, *expected.object)
		} else {
			kind := responseString
			switch typ.Name() {
			case "Int":
				kind = responseInt
			case "Boolean":
				kind = responseBool
			}
			if expected.kind != kind {
				t.Fatalf("scalar type %s", field.Name)
			}
		}
	}
}
func selectionValue(selection ast.SelectionSet) map[string]any {
	out := map[string]any{}
	for _, node := range selection {
		field := node.(*ast.Field)
		typ := field.Definition.Type
		var value any
		if len(field.SelectionSet) > 0 {
			value = selectionValue(field.SelectionSet)
		} else {
			switch typ.Name() {
			case "Int":
				value = json.Number("1")
			case "Boolean":
				value = false
			default:
				value = "value"
			}
		}
		if typ.Elem != nil {
			value = []any{value}
		}
		out[field.Name] = value
	}
	return out
}
