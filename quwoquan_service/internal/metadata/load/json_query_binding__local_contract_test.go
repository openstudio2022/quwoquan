package load

import (
	"encoding/json"
	"github.com/santhosh-tekuri/jsonschema/v6"
	"gopkg.in/yaml.v3"
	"path/filepath"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md
func TestJSONQueryBindingSchemaAndGraphEncoding(t *testing.T) {
	var binding requestBindingDocument
	if err := yaml.Unmarshal([]byte("name: filter\nfield: filter\nencoding: json\nmax_bytes: 128\n"), &binding); err != nil {
		t.Fatal(err)
	}
	normalized := normalizeRequestBindings([]requestBindingDocument{binding})
	wire, err := json.Marshal(normalized[0])
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(wire), `"encoding":"json"`) || !strings.Contains(string(wire), `"maxBytes":128`) {
		t.Fatalf("lost graph encoding: %s", wire)
	}
	for _, filename := range []string{"operations.schema.json", "contract_graph.schema.json"} {
		schemaPath, err := filepath.Abs(filepath.Join("../../../contracts/metadata/_schemas", filename))
		if err != nil {
			t.Fatal(err)
		}
		schema, err := jsonschema.NewCompiler().Compile(schemaPath + "#/$defs/requestBinding")
		if err != nil {
			t.Fatal(err)
		}
		fragment := "#/properties/api_routes/items/properties/request_bindings"
		if filename == "contract_graph.schema.json" { fragment = "#/properties/operations/items/properties/requestBindings" }
		positions,err:=jsonschema.NewCompiler().Compile(schemaPath+fragment);if err!=nil{t.Fatal(err)}
		key := "max_bytes"
		if filename == "contract_graph.schema.json" {
			key = "maxBytes"
		}
		for _,location:=range []string{"path","query","header","injected"}{
		 value:=map[string]any{location:[]any{map[string]any{"name":"filter","field":"filter","encoding":"json",key:128}}}
		 err:=positions.Validate(value);if (err==nil)!=(location=="query"){t.Fatalf("%s position %s: %v",filename,location,err)}
		}
		for _, test := range []struct {
			encoding any
			maximum  any
			valid    bool
		}{{"json", 128, true}, {"json", 0, false}, {"json", -1, false}, {"json", nil, false}, {nil, 128, false}, {"csv", 128, false}} {
			value := map[string]any{"name": "filter", "field": "filter"}
			if test.encoding != nil {
				value["encoding"] = test.encoding
			}
			if test.maximum != nil {
				value[key] = test.maximum
			}
			err := schema.Validate(value)
			if (err == nil) != test.valid {
				t.Fatalf("%s %#v: %v", filename, value, err)
			}
		}
	}
}
