// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
package local_contract

import (
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strconv"
	"testing"

	"gopkg.in/yaml.v3"
)

type assetIndexShape struct {
	Name   string         `yaml:"name"`
	Keys   map[string]int `yaml:"keys"`
	Unique bool           `yaml:"unique"`
}

func TestRetiredReleaseMembershipContractAndProductionIndexes(t *testing.T) {
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(source), "../../../.."))
	contracts := filepath.Join(root, "contracts/media/media_asset")
	var fields struct {
		Fields []struct {
			Name        string `yaml:"name"`
			Source      string `yaml:"source"`
			Role        string `yaml:"role"`
			APIExposure string `yaml:"api_exposure"`
		} `yaml:"fields"`
	}
	readMediaContract(t, filepath.Join(contracts, "fields.yaml"), &fields)
	foundDiagnostic := false
	for _, field := range fields.Fields {
		if field.Name == "sourceReleaseIds" || field.Source == "sourceReleaseIds" {
			t.Fatal("retired research membership must not remain in MediaAsset fields")
		}
		if field.Name == "sourceReleaseId" {
			foundDiagnostic = field.Source == "sourceReleaseId" && field.Role == "projection" && field.APIExposure == "drop"
		}
	}
	if !foundDiagnostic {
		t.Fatal("singular release diagnostic projection must remain internal")
	}
	var object struct {
		Reasons map[string]string `yaml:"local_identity_reasons"`
	}
	readMediaContract(t, filepath.Join(contracts, "object.yaml"), &object)
	if _, exists := object.Reasons["sourceReleaseIds"]; exists || object.Reasons["sourceReleaseId"] == "" {
		t.Fatal("retire only plural membership identity reason, retaining singular diagnostic")
	}
	var storage struct {
		Collections map[string]struct {
			Indexes []assetIndexShape `yaml:"indexes"`
		} `yaml:"collections"`
	}
	readMediaContract(t, filepath.Join(contracts, "storage.yaml"), &storage)
	want := []assetIndexShape{
		{"idx_media_assets_owner_status", map[string]int{"ownerId": 1, "processingStatus": 1, "createdAt": -1}, false},
		{"idx_media_assets_source_session", map[string]int{"sourceSessionId": 1}, true},
		{"idx_media_assets_object_key", map[string]int{"objectKey": 1}, false},
		{"idx_media_assets_sha256", map[string]int{"sha256": 1}, false},
		{"idx_media_assets_version", map[string]int{"_id": 1, "version": 1}, true},
		{"idx_media_assets_manual_cover_status", map[string]int{"manualCoverAssetId": 1, "processingStatus": 1}, false},
	}
	if got := storage.Collections["media_assets"].Indexes; !reflect.DeepEqual(got, want) {
		t.Fatalf("MediaAsset storage indexes changed: got %+v, want %+v", got, want)
	}
	path := filepath.Join(root, "internal/media/media_asset/infrastructure/persistence/mongo_indexes.go")
	if got := readProductionAssetIndexes(t, path); !reflect.DeepEqual(got, want) {
		t.Fatalf("production MediaAsset indexes differ from live contract: got %+v, want %+v", got, want)
	}
}

func readMediaContract(t *testing.T, path string, target any) {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := yaml.Unmarshal(data, target); err != nil {
		t.Fatal(err)
	}
}

func readProductionAssetIndexes(t *testing.T, path string) []assetIndexShape {
	t.Helper()
	file, err := parser.ParseFile(token.NewFileSet(), path, nil, parser.SkipObjectResolution)
	if err != nil {
		t.Fatal(err)
	}
	var result []assetIndexShape
	for _, declaration := range file.Decls {
		function, ok := declaration.(*ast.FuncDecl)
		if !ok || function.Name.Name != "EnsureIndexes" {
			continue
		}
		ast.Inspect(function.Body, func(node ast.Node) bool {
			literal, ok := node.(*ast.CompositeLit)
			if !ok {
				return true
			}
			array, ok := literal.Type.(*ast.ArrayType)
			if !ok {
				return true
			}
			element, ok := array.Elt.(*ast.SelectorExpr)
			if !ok || element.Sel.Name != "IndexModel" {
				return true
			}
			for _, expression := range literal.Elts {
				result = append(result, readAssetIndexModel(t, expression.(*ast.CompositeLit)))
			}
			return false
		})
	}
	return result
}

func readAssetIndexModel(t *testing.T, model *ast.CompositeLit) assetIndexShape {
	t.Helper()
	result := assetIndexShape{Keys: map[string]int{}}
	for _, expression := range model.Elts {
		field := expression.(*ast.KeyValueExpr)
		switch field.Key.(*ast.Ident).Name {
		case "Keys":
			for _, key := range field.Value.(*ast.CompositeLit).Elts {
				var name string
				var direction int
				for _, expression := range key.(*ast.CompositeLit).Elts {
					pair := expression.(*ast.KeyValueExpr)
					if pair.Key.(*ast.Ident).Name == "Key" {
						name = assetASTString(t, pair.Value)
					} else {
						value, sign := pair.Value, 1
						if negative, ok := value.(*ast.UnaryExpr); ok && negative.Op == token.SUB {
							value, sign = negative.X, -1
						}
						parsed, err := strconv.Atoi(value.(*ast.BasicLit).Value)
						if err != nil {
							t.Fatal(err)
						}
						direction = sign * parsed
					}
				}
				result.Keys[name] = direction
			}
		case "Options":
			ast.Inspect(field.Value, func(node ast.Node) bool {
				call, ok := node.(*ast.CallExpr)
				if !ok {
					return true
				}
				selector, ok := call.Fun.(*ast.SelectorExpr)
				if ok && selector.Sel.Name == "SetName" {
					result.Name = assetASTString(t, call.Args[0])
				}
				if ok && selector.Sel.Name == "SetUnique" {
					result.Unique = call.Args[0].(*ast.Ident).Name == "true"
				}
				return true
			})
		}
	}
	return result
}

func assetASTString(t *testing.T, expression ast.Expr) string {
	t.Helper()
	value, err := strconv.Unquote(expression.(*ast.BasicLit).Value)
	if err != nil {
		t.Fatal(err)
	}
	return value
}
